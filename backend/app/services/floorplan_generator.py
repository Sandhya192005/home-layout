"""Dynamic 2D floor-plan generation engine.

Given a customer `RequirementCreate`, this module procedurally derives a full
room-by-room layout (with walls, doors, windows, furniture, parking and
staircase) that reacts to plot size, room program, floor count, Vastu
preference and parking needs. Nothing here is a fixed/static template — every
dimension is computed from the input.

High-level pipeline:
  1. Compute the buildable rectangle from plot size + setbacks (per facing).
  2. Reserve a staircase strip (multi-floor only) so it stacks identically on
     every floor.
  3. Build a room "program" (list of room instances) split across floors.
  4. For each floor: assign rooms to Vastu compass zones (or a functional
     fallback order), derive a weighted 3x3 grid from the buildable rect, and
     slice it into room rectangles.
  5. Carve ground-floor parking from the front setback (+ a little extra
     footprint depth if vehicles don't fit in the setback alone).
  6. Derive walls (exterior outline + shared interior edges), doors (entrance
     + one per room on its longest shared wall), windows (exterior-facing
     habitable rooms) and furniture (simple wall-anchored placement).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from app.schemas.requirement import RequirementCreate
from app.services import geometry as geo
from app.utils.constants import (
    CAR_PARKING_SIZE,
    DOOR_WIDTH_INTERNAL,
    DOOR_WIDTH_MAIN,
    MAIN_GATE_WIDTH,
    RAMP_LENGTH,
    RAMP_WIDTH,
    ROOM_LIBRARY,
    SETBACK_RULES,
    TWO_WHEELER_PARKING_SIZE,
    WALL_THICKNESS_EXTERIOR,
    WALL_THICKNESS_INTERIOR,
    WINDOW_WIDTH_DEFAULT,
    ZONE_CELL,
    ZONE_GRID,
)

FALLBACK_ZONE_ORDER = ["C", "N", "S", "E", "W", "NE", "NW", "SE", "SW"]
STAIRCASE_WIDTH = 5.0
VERANDA_DEPTH = 6.0
ENTRANCE_ROOM_TYPES = ("veranda", "foyer")

# whichever compass edge the plot faces is where the street (and therefore
# the entrance room) has to sit, regardless of Vastu preference
FRONT_ZONES_BY_FACING = {
    "north": ["N", "NE", "NW"],
    "south": ["S", "SE", "SW"],
    "east": ["E", "NE", "SE"],
    "west": ["W", "NW", "SW"],
}
FRONT_ZONE_LABEL = {"north": "N", "south": "S", "east": "E", "west": "W"}


@dataclass
class RoomInstance:
    room_id: str
    room_type: str
    label: str
    weight: float
    priority: int
    zones: list[str]
    habitable: bool
    min_w: float
    min_l: float
    furniture: list[dict]
    floor_index: int
    zone: str | None = None
    rect: dict | None = None
    below_min: bool = False


def _setback(dimension: float, kind: str) -> float:
    rule = SETBACK_RULES[kind]
    return min(max(dimension * rule["fraction"], rule["min"]), rule["max"])


def compute_buildable_rect(plot_length: float, plot_width: float, facing: str) -> dict:
    """Buildable rectangle (feet) after mandatory setbacks, in plot coordinates
    (x: 0=West..plot_width=East, y: 0=North..plot_length=South)."""
    if facing in ("north", "south"):
        front_sb = _setback(plot_length, "front")
        rear_sb = _setback(plot_length, "rear")
        side_sb = _setback(plot_width, "side")
        y0 = front_sb if facing == "north" else rear_sb
        y1 = plot_length - (rear_sb if facing == "north" else front_sb)
        x0, x1 = side_sb, plot_width - side_sb
    else:
        front_sb = _setback(plot_width, "front")
        rear_sb = _setback(plot_width, "rear")
        side_sb = _setback(plot_length, "side")
        x0 = front_sb if facing == "west" else rear_sb
        x1 = plot_width - (rear_sb if facing == "west" else front_sb)
        y0, y1 = side_sb, plot_length - side_sb
    return {"x": x0, "y": y0, "w": max(x1 - x0, 0), "l": max(y1 - y0, 0)}


def _front_edge(facing: str) -> str:
    return {"north": "north", "south": "south", "east": "east", "west": "west"}[facing]


# ---------------------------------------------------------------------------
# Room program: turn the requirement into a flat list of RoomInstance objects
# distributed across floors.
# ---------------------------------------------------------------------------

def _make_room(room_type: str, floor_index: int, seq: int, label_suffix: str = "") -> RoomInstance:
    meta = ROOM_LIBRARY[room_type]
    return RoomInstance(
        room_id=f"{room_type}_{seq}",
        room_type=room_type,
        label=meta["label"] + (f" {label_suffix}" if label_suffix else ""),
        weight=meta["weight"],
        priority=meta["priority"],
        zones=list(meta["zones"]),
        habitable=meta["habitable"],
        min_w=meta["min_w"],
        min_l=meta["min_l"],
        furniture=[dict(item) for item in meta["furniture"]],
        floor_index=floor_index,
    )


def _split_evenly(total: int, n: int) -> list[int]:
    """Divide `total` into `n` buckets as evenly as possible, remainder to the front."""
    base, rem = divmod(total, n)
    return [base + (1 if i < rem else 0) for i in range(n)]


def is_independent_floors(req: RequirementCreate) -> bool:
    return req.floors > 1 and req.floor_type == "independent"


def build_room_program(req: RequirementCreate) -> list[RoomInstance]:
    if is_independent_floors(req):
        return _build_independent_room_program(req)
    return _build_duplex_room_program(req)


def _build_independent_room_program(req: RequirementCreate) -> list[RoomInstance]:
    """Each floor is a fully self-contained house (own kitchen, living/dining,
    bedrooms, bathrooms) reached off a shared internal staircase -- unlike the
    duplex program below, which spreads ONE household's rooms across floors."""
    rooms: list[RoomInstance] = []
    seq = 0
    floors = req.floors

    def nxt() -> int:
        nonlocal seq
        seq += 1
        return seq

    bedrooms_per_floor = _split_evenly(req.bedrooms, floors)
    bathrooms_per_floor = _split_evenly(req.bathrooms, floors)
    balconies_per_floor = _split_evenly(req.balconies, floors)
    additional_per_floor: list[list[str]] = [[] for _ in range(floors)]
    for i, extra in enumerate(req.additional_rooms):
        additional_per_floor[i % floors].append(extra)

    for floor_idx in range(floors):
        # Only the ground floor touches grade, so only it can have an outdoor
        # veranda porch; a foyer (indoor entrance hall) is fair game on every
        # floor since each is its own unit off the shared staircase landing.
        if floor_idx == 0 and req.has_veranda:
            veranda = _make_room("veranda", floor_idx, nxt())
            veranda.zones = FRONT_ZONES_BY_FACING[req.facing]
            rooms.append(veranda)
        if req.has_foyer:
            foyer = _make_room("foyer", floor_idx, nxt())
            foyer.zones = FRONT_ZONES_BY_FACING[req.facing]
            rooms.append(foyer)

        if req.has_living_room:
            rooms.append(_make_room("living_room", floor_idx, nxt()))
        if req.has_dining_room:
            rooms.append(_make_room("dining_room", floor_idx, nxt()))
        rooms.append(_make_room("kitchen", floor_idx, nxt()))
        if req.has_utility_room:
            rooms.append(_make_room("utility", floor_idx, nxt()))
        if req.has_pooja_room:
            rooms.append(_make_room("pooja_room", floor_idx, nxt()))
        if req.has_study_room:
            rooms.append(_make_room("study_room", floor_idx, nxt()))

        floor_bedrooms = max(bedrooms_per_floor[floor_idx], 1)
        bedroom_types = ["master_bedroom"] + ["bedroom"] * max(floor_bedrooms - 1, 0)
        for btype in bedroom_types:
            rooms.append(_make_room(btype, floor_idx, nxt()))

        floor_bathrooms = max(bathrooms_per_floor[floor_idx], 1)
        for i in range(floor_bathrooms):
            bath_type = "accessible_bathroom" if (req.wheelchair_accessible and floor_idx == 0 and i == 0) else "bathroom"
            rooms.append(_make_room(bath_type, floor_idx, nxt()))

        for extra in additional_per_floor[floor_idx]:
            rooms.append(_make_room(extra, floor_idx, nxt()))
        for _ in range(balconies_per_floor[floor_idx]):
            rooms.append(_make_room("balcony", floor_idx, nxt()))

        rooms.append(_make_room("staircase", floor_idx, nxt()))

    return rooms


def _build_duplex_room_program(req: RequirementCreate) -> list[RoomInstance]:
    rooms: list[RoomInstance] = []
    seq = 0
    floors = req.floors

    def nxt() -> int:
        nonlocal seq
        seq += 1
        return seq

    # Ground floor common rooms -- veranda (covered porch) and foyer (enclosed
    # hall) are independent opt-ins, not alternatives: a plot can have either,
    # both (porch leading into a hall), or neither (front door opens straight
    # into the living room).
    for entrance_type, wanted in (("veranda", req.has_veranda), ("foyer", req.has_foyer)):
        if not wanted:
            continue
        entrance_room = _make_room(entrance_type, 0, nxt())
        entrance_room.zones = FRONT_ZONES_BY_FACING[req.facing]
        rooms.append(entrance_room)
    if req.has_living_room:
        rooms.append(_make_room("living_room", 0, nxt()))
    if req.has_dining_room:
        rooms.append(_make_room("dining_room", 0, nxt()))
    rooms.append(_make_room("kitchen", 0, nxt()))
    if req.has_utility_room:
        rooms.append(_make_room("utility", 0, nxt()))
    if req.has_pooja_room:
        rooms.append(_make_room("pooja_room", 0, nxt()))

    ground_extra_types = {"servant_room", "store_room"}
    upper_extra_types = {"home_office", "guest_room", "gym", "library"}
    extra_upper: list[str] = []
    for extra in req.additional_rooms:
        if extra in ground_extra_types:
            rooms.append(_make_room(extra, 0, nxt()))
        else:
            extra_upper.append(extra)

    # Bedrooms + bathrooms distribution
    bedroom_types = ["master_bedroom"] + ["bedroom"] * max(req.bedrooms - 1, 0)
    total_bathrooms = req.bathrooms

    if floors == 1:
        for i, btype in enumerate(bedroom_types):
            rooms.append(_make_room(btype, 0, nxt()))
        for i in range(total_bathrooms):
            bath_type = "accessible_bathroom" if (req.wheelchair_accessible and i == 0) else "bathroom"
            rooms.append(_make_room(bath_type, 0, nxt()))
        if req.has_study_room:
            rooms.append(_make_room("study_room", 0, nxt()))
        for extra in extra_upper:
            rooms.append(_make_room(extra, 0, nxt()))
        for _ in range(req.balconies):
            rooms.append(_make_room("balcony", 0, nxt()))
    else:
        upper_floor_count = floors - 1
        # one common bathroom stays on the ground floor
        ground_bath_type = "accessible_bathroom" if req.wheelchair_accessible else "bathroom"
        rooms.append(_make_room(ground_bath_type, 0, nxt()))
        remaining_baths = max(total_bathrooms - 1, 0)

        # distribute bedrooms round-robin across upper floors (1..floors-1)
        per_floor_bedrooms: list[list[str]] = [[] for _ in range(upper_floor_count)]
        for i, btype in enumerate(bedroom_types):
            per_floor_bedrooms[i % upper_floor_count].append(btype)

        for i in range(upper_floor_count):
            floor_idx = i + 1
            for btype in per_floor_bedrooms[i]:
                rooms.append(_make_room(btype, floor_idx, nxt()))
            baths_here = math.ceil(remaining_baths / upper_floor_count) if i == 0 else remaining_baths // upper_floor_count
            for _ in range(min(baths_here, remaining_baths)):
                rooms.append(_make_room("bathroom", floor_idx, nxt()))
                remaining_baths -= 1

        if req.has_study_room:
            rooms.append(_make_room("study_room", 1, nxt()))
        for i, extra in enumerate(extra_upper):
            rooms.append(_make_room(extra, 1 + (i % upper_floor_count), nxt()))
        for i in range(req.balconies):
            rooms.append(_make_room("balcony", 1 + (i % upper_floor_count), nxt()))

    if floors > 1:
        for floor_idx in range(floors):
            rooms.append(_make_room("staircase", floor_idx, nxt()))

    return rooms


# ---------------------------------------------------------------------------
# Zone assignment + grid layout for a single floor
# ---------------------------------------------------------------------------

def _assign_zones(rooms: list[RoomInstance], vastu: bool) -> dict[tuple[int, int], list[RoomInstance]]:
    cells: dict[tuple[int, int], list[RoomInstance]] = {(r, c): [] for r in range(3) for c in range(3)}
    cell_weight: dict[tuple[int, int], float] = {(r, c): 0.0 for r in range(3) for c in range(3)}
    cell_count: dict[tuple[int, int], int] = {(r, c): 0 for r in range(3) for c in range(3)}
    row_occupied_cols: dict[int, set[int]] = {0: set(), 1: set(), 2: set()}
    # cap how many rooms can pile into one Vastu cell so a popular zone (e.g.
    # every bedroom preferring SW) doesn't force that single cell to be
    # sliced into more slivers than the other 8 cells combined.
    max_per_cell = max(2, math.ceil(len(rooms) / 9) + 1)
    avg_room_weight = (sum(r.weight for r in rooms) / len(rooms)) if rooms else 1.0

    def score(c: tuple[int, int]) -> float:
        row, col = c
        # a 3rd distinct occupied column in a row forces that whole row to be
        # halved into two stacked sub-rows later (see `_layout_grid`), which
        # roughly doubles how cramped every room in it gets. Discourage that
        # unless Vastu compliance specifically requires this exact cell.
        penalty = 0.0
        if not vastu and col not in row_occupied_cols[row] and len(row_occupied_cols[row]) >= 2:
            penalty = avg_room_weight * 1.5
        return cell_weight[c] + penalty

    ordered = sorted(rooms, key=lambda r: (-r.priority, -r.weight))
    for room in ordered:
        # the entrance room (veranda/foyer) must sit on the street-facing side
        # regardless of Vastu preference -- everything else keeps the existing
        # functional fallback order when Vastu isn't requested
        is_entrance = room.room_type in ENTRANCE_ROOM_TYPES
        preference = room.zones if (vastu or is_entrance) else FALLBACK_ZONE_ORDER
        candidates = [ZONE_CELL[z] for z in preference if z in ZONE_CELL]
        if not candidates:
            candidates = list(cell_weight.keys())
        under_cap = [c for c in candidates if cell_count[c] < max_per_cell]
        pool = under_cap or candidates
        best_cell = min(pool, key=score)
        # if every preferred cell is already loaded (by weight or by count), fall
        # back to the globally lightest under-cap cell so rooms spread across
        # more of the 9 cells instead of stacking into a few
        avg = sum(cell_weight.values()) / 9 or 1.0
        if cell_weight[best_cell] > avg * 1.6 or cell_count[best_cell] >= max_per_cell:
            fallback_pool = [c for c in cell_weight if cell_count[c] < max_per_cell] or list(cell_weight.keys())
            best_cell = min(fallback_pool, key=score)
        cells[best_cell].append(room)
        cell_weight[best_cell] += room.weight
        cell_count[best_cell] += 1
        row_occupied_cols[best_cell[0]].add(best_cell[1])
        room.zone = ZONE_GRID[best_cell[0]][best_cell[1]]
    return cells


def _cell_depth_estimate(cells, axis_of, row: int, col: int) -> float:
    """Minimum depth (y-extent) this cell needs, given how its occupants will
    be split: stacked (axis 'y') needs the sum of their min lengths; placed
    side by side (axis 'x') only needs the tallest one's min length."""
    occupants = cells[(row, col)]
    if not occupants:
        return 0.0
    axis = axis_of.get((row, col), "y")
    return sum(rm.min_l for rm in occupants) if axis == "y" else max(rm.min_l for rm in occupants)


def _cell_width_estimate(cells, axis_of, row: int, col: int) -> float:
    """Minimum width (x-extent) this cell needs, mirroring `_cell_depth_estimate`."""
    occupants = cells[(row, col)]
    if not occupants:
        return 0.0
    axis = axis_of.get((row, col), "y")
    return max(rm.min_w for rm in occupants) if axis == "y" else sum(rm.min_w for rm in occupants)


def _layout_grid(buildable: dict, cells: dict[tuple[int, int], list[RoomInstance]]) -> None:
    """Hierarchical (guillotine-style) slice: rows are sized by their total room
    weight, then each row is independently sliced into only the columns that
    actually have rooms in it. Columns need not line up between rows — real
    floor plans don't force that either — which avoids the degenerate slivers
    a naive uniform 3x3 grid produces when a row/column is sparsely occupied.

    This runs in two passes. Pass A does a rough weight-only split just to see
    each cell's approximate aspect ratio, which decides whether its occupants
    will end up stacked or side-by-side. Pass B redoes the split using that
    axis choice to compute a real minimum-size floor per row/column, so rooms
    only get squeezed below their `min_w`/`min_l` when the buildable rect
    genuinely doesn't have enough space for the whole program — not because a
    plain weight split happened to shortchange them."""
    row_weight = [sum(sum(rm.weight for rm in cells[(row, col)]) for col in range(3)) for row in range(3)]
    total = sum(row_weight) or 1.0
    min_share = 0.02
    row_weight = [w if w > 0 else total * min_share for w in row_weight]

    rough_rows = geo.subdivide(buildable, "y", row_weight)
    axis_of: dict[tuple[int, int], str] = {}
    for row in range(3):
        occupied_cols = [c for c in range(3) if cells[(row, c)]]
        if not occupied_cols:
            continue
        col_weights = [sum(rm.weight for rm in cells[(row, c)]) or 0.1 for c in occupied_cols]
        rough_cols = geo.subdivide(rough_rows[row], "x", col_weights)
        for col, rect in zip(occupied_cols, rough_cols):
            axis_of[(row, col)] = "y" if rect["l"] >= rect["w"] else "x"

    # Decide up front, per row, whether its occupied columns sit side-by-side
    # (<=2 columns) or split into two stacked sub-rows (3 columns) — and size
    # the row's minimum depth to match. A 3-column row needs the SUM of both
    # sub-rows' depths since they stack vertically inside it; a <=2-column row
    # only needs the deepest single column since those sit side by side.
    # Getting this right up front (instead of only discovering it once we're
    # already inside the row) is what stops a 3-occupant row from being
    # under-allocated and then halved again into two even-narrower slivers.
    row_groups: dict[int, tuple[list[int], list[int]]] = {}
    row_min: list[float] = []
    for row in range(3):
        occupied_cols = [c for c in range(3) if cells[(row, c)]]
        if not occupied_cols:
            row_groups[row] = ([], [])
            row_min.append(0.0)
            continue
        if len(occupied_cols) <= 2:
            row_groups[row] = (occupied_cols, [])
            row_min.append(max(_cell_depth_estimate(cells, axis_of, row, c) for c in occupied_cols))
            continue
        weighted = sorted(occupied_cols, key=lambda c: sum(rm.weight for rm in cells[(row, c)]), reverse=True)
        group_a, group_b = [weighted[0]], []
        sum_a = sum(rm.weight for rm in cells[(row, weighted[0])])
        sum_b = 0.0
        for col in weighted[1:]:
            w = sum(rm.weight for rm in cells[(row, col)])
            if sum_a <= sum_b:
                group_a.append(col)
                sum_a += w
            else:
                group_b.append(col)
                sum_b += w
        row_groups[row] = (sorted(group_a), sorted(group_b))
        depth_a = max(_cell_depth_estimate(cells, axis_of, row, c) for c in group_a)
        depth_b = max((_cell_depth_estimate(cells, axis_of, row, c) for c in group_b), default=0.0)
        row_min.append(depth_a + depth_b)

    row_items = [{"weight": row_weight[row], "min": row_min[row]} for row in range(3)]
    row_rects = geo.subdivide_min_aware(buildable, "y", row_items)

    for row in range(3):
        group_a, group_b = row_groups[row]
        if not group_a and not group_b:
            continue
        row_rect = row_rects[row]
        if not group_b:
            _slice_columns(row_rect, group_a, cells, row, axis_of)
        else:
            depth_a = max(_cell_depth_estimate(cells, axis_of, row, c) for c in group_a)
            depth_b = max(_cell_depth_estimate(cells, axis_of, row, c) for c in group_b)
            weight_a = sum(rm.weight for c in group_a for rm in cells[(row, c)]) or 0.1
            weight_b = sum(rm.weight for c in group_b for rm in cells[(row, c)]) or 0.1
            sub_rows = geo.subdivide_min_aware(
                row_rect,
                "y",
                [{"weight": weight_a, "min": depth_a}, {"weight": weight_b, "min": depth_b}],
            )
            _slice_columns(sub_rows[0], group_a, cells, row, axis_of)
            _slice_columns(sub_rows[1], group_b, cells, row, axis_of)


def _slice_columns(
    row_rect: dict,
    cols: list[int],
    cells: dict[tuple[int, int], list[RoomInstance]],
    row: int,
    axis_of: dict[tuple[int, int], str],
) -> None:
    col_items = [
        {
            "weight": sum(rm.weight for rm in cells[(row, col)]) or 0.1,
            "min": _cell_width_estimate(cells, axis_of, row, col),
        }
        for col in cols
    ]
    col_rects = geo.subdivide_min_aware(row_rect, "x", col_items)
    for col, cell_rect in zip(cols, col_rects):
        occupants = cells[(row, col)]
        # split the taller dimension so sub-rooms stay closer to square
        axis = axis_of.get((row, col)) or ("y" if cell_rect["l"] >= cell_rect["w"] else "x")
        items = [
            {"weight": rm.weight or 0.1, "min": rm.min_l if axis == "y" else rm.min_w}
            for rm in occupants
        ]
        sub_rects = geo.subdivide_min_aware(cell_rect, axis, items)
        for room, rect in zip(occupants, sub_rects):
            room.rect = rect
            room.below_min = rect["w"] < room.min_w - 0.5 or rect["l"] < room.min_l - 0.5


def layout_floor(rooms: list[RoomInstance], buildable: dict, vastu: bool) -> None:
    cells = _assign_zones(rooms, vastu)
    _layout_grid(buildable, cells)


# ---------------------------------------------------------------------------
# Parking
# ---------------------------------------------------------------------------

def compute_parking(
    base_rect: dict, facing: str, front_sb: float, cars: int, two_wheelers: int, full_rect: dict | None = None
):
    """`base_rect` is the room-layout area (already excludes any staircase
    strip); `full_rect` is the true exterior building footprint (includes it).
    The parking depth carve recedes the whole front facade equally, so it's
    applied to both -- `full_outline` is what exterior walls should be drawn
    from, so the staircase ends up enclosed inside the house rather than
    appearing as a detached block outside the ground-floor walls."""
    full_rect = full_rect if full_rect is not None else base_rect
    if cars <= 0 and two_wheelers <= 0:
        return None, base_rect, base_rect, full_rect

    lateral_axis = "w" if facing in ("north", "south") else "l"
    depth_needed = CAR_PARKING_SIZE["l"] if cars > 0 else TWO_WHEELER_PARKING_SIZE["l"]
    width_needed = cars * CAR_PARKING_SIZE["w"] + two_wheelers * TWO_WHEELER_PARKING_SIZE["w"]
    width_needed += max(cars + two_wheelers - 1, 0) * 1.0  # gaps between vehicles
    width_available = base_rect[lateral_axis]
    width_needed = min(width_needed, width_available * 0.7)

    extra_depth = max(0.0, depth_needed - front_sb)
    front_edge = _front_edge(facing)
    outline = geo.shrink_edge(base_rect, front_edge, extra_depth)
    room_rect = outline
    full_outline = geo.shrink_edge(full_rect, front_edge, extra_depth)

    # Parking rect sits in the reclaimed strip nearest the West/North corner of the front edge.
    if facing == "north":
        parking = {"x": base_rect["x"], "y": base_rect["y"], "w": width_needed, "l": min(depth_needed, front_sb + extra_depth)}
    elif facing == "south":
        total_depth = min(depth_needed, front_sb + extra_depth)
        parking = {"x": base_rect["x"], "y": geo.rect_y2(base_rect) - total_depth, "w": width_needed, "l": total_depth}
    elif facing == "west":
        parking = {"x": base_rect["x"], "y": base_rect["y"], "w": min(depth_needed, front_sb + extra_depth), "l": width_needed}
    else:  # east
        total_depth = min(depth_needed, front_sb + extra_depth)
        parking = {"x": geo.rect_x2(base_rect) - total_depth, "y": base_rect["y"], "w": total_depth, "l": width_needed}

    parking["capacity_cars"] = cars
    parking["capacity_two_wheelers"] = two_wheelers
    return parking, outline, room_rect, full_outline


# ---------------------------------------------------------------------------
# Wheelchair ramp + main gate
# ---------------------------------------------------------------------------

_OUTWARD_SHIFT_AXIS = {"north": "x", "south": "x", "west": "y", "east": "y"}


def compute_ramp(entrance_door: dict | None, plot: dict, parking: dict | None) -> dict | None:
    """A ramp running outward from the entrance door, clipped to the plot and
    nudged sideways (a few tries) if it would overlap the parking rect."""
    if not entrance_door:
        return None
    side = entrance_door["wall"]
    cx, cy = entrance_door["center_x"], entrance_door["center_y"]

    def rect_for(shift: float) -> dict:
        if side == "north":
            length = min(RAMP_LENGTH, cy - plot["y"])
            return {"x": cx - RAMP_WIDTH / 2 + shift, "y": cy - length, "w": RAMP_WIDTH, "l": length}
        if side == "south":
            length = min(RAMP_LENGTH, geo.rect_y2(plot) - cy)
            return {"x": cx - RAMP_WIDTH / 2 + shift, "y": cy, "w": RAMP_WIDTH, "l": length}
        if side == "west":
            length = min(RAMP_LENGTH, cx - plot["x"])
            return {"x": cx - length, "y": cy - RAMP_WIDTH / 2 + shift, "w": length, "l": RAMP_WIDTH}
        length = min(RAMP_LENGTH, geo.rect_x2(plot) - cx)
        return {"x": cx, "y": cy - RAMP_WIDTH / 2 + shift, "w": length, "l": RAMP_WIDTH}

    for shift in (0.0, RAMP_WIDTH + 2, -(RAMP_WIDTH + 2), 2 * (RAMP_WIDTH + 2), -2 * (RAMP_WIDTH + 2)):
        rect = rect_for(shift)
        if rect["w"] <= 0.5 or rect["l"] <= 0.5:
            continue
        if not (0 <= rect["x"] and geo.rect_x2(rect) <= geo.rect_x2(plot)):
            continue
        if not (0 <= rect["y"] and geo.rect_y2(rect) <= geo.rect_y2(plot)):
            continue
        if parking and geo.rects_overlap(rect, parking):
            continue
        rect["side"] = side
        return rect
    return None


def compute_main_gate(plot: dict, facing: str, parking: dict | None, entrance_door: dict | None) -> dict:
    """A driveway gate opening centered on the parking (or the entrance, if
    there's no parking) along the plot's front boundary."""
    front_side = _front_edge(facing)
    axis = _OUTWARD_SHIFT_AXIS[front_side]
    if parking:
        center = parking["x"] + parking["w"] / 2 if axis == "x" else parking["y"] + parking["l"] / 2
    elif entrance_door:
        center = entrance_door["center_x"] if axis == "x" else entrance_door["center_y"]
    else:
        center = plot["w"] / 2 if axis == "x" else plot["l"] / 2

    span = plot["w"] if axis == "x" else plot["l"]
    width = min(MAIN_GATE_WIDTH, span)
    start = min(max(center - width / 2, 0.0), span - width)

    if front_side == "north":
        return {"x": start, "y": plot["y"], "width": width, "side": "north"}
    if front_side == "south":
        return {"x": start, "y": geo.rect_y2(plot), "width": width, "side": "south"}
    if front_side == "west":
        return {"x": plot["x"], "y": start, "width": width, "side": "west"}
    return {"x": geo.rect_x2(plot), "y": start, "width": width, "side": "east"}


# ---------------------------------------------------------------------------
# Walls, doors, windows, furniture
# ---------------------------------------------------------------------------

def _build_walls(outline: dict, room_rects: list[dict]) -> list[dict]:
    walls = []
    for side, seg in geo.edges_of(outline).items():
        walls.append({"x1": seg[0], "y1": seg[1], "x2": seg[2], "y2": seg[3],
                       "thickness": WALL_THICKNESS_EXTERIOR, "type": "exterior", "side": side})
    seen = set()
    for i, a in enumerate(room_rects):
        for b in room_rects[i + 1:]:
            shared = geo.shared_segment(a["rect"], b["rect"])
            if not shared:
                continue
            _, _, seg = shared
            key = tuple(round(v, 3) for v in seg)
            if key in seen or geo.segment_length(seg) < 0.5:
                continue
            seen.add(key)
            walls.append({"x1": seg[0], "y1": seg[1], "x2": seg[2], "y2": seg[3],
                          "thickness": WALL_THICKNESS_INTERIOR, "type": "interior",
                          "between": [a["id"], b["id"]]})
    return walls


def _build_windows(rooms: list[RoomInstance], outline: dict) -> list[dict]:
    windows = []
    for room in rooms:
        if not room.habitable or room.room_type == "staircase" or not room.rect:
            continue
        sides = geo.on_boundary(room.rect, outline)
        if not sides:
            continue
        edges = geo.edges_of(room.rect)
        best_side = max(sides, key=lambda s: geo.segment_length(edges[s]))
        seg = edges[best_side]
        length = geo.segment_length(seg)
        width = min(WINDOW_WIDTH_DEFAULT, max(length * 0.5, 2.0))
        cx, cy = geo.midpoint(seg)
        windows.append({"room_id": room.room_id, "wall": best_side, "width": round(width, 2),
                         "center_x": round(cx, 2), "center_y": round(cy, 2)})
    return windows


def _build_doors(rooms: list[RoomInstance], outline: dict, facing: str, entrance_room_id: str | None) -> list[dict]:
    doors = []
    entrance_room = next((r for r in rooms if r.room_id == entrance_room_id), None) if entrance_room_id else None
    if entrance_room and entrance_room.rect:
        sides = geo.on_boundary(entrance_room.rect, outline)
        front_side = _front_edge(facing)
        side = front_side if front_side in sides else (sides[0] if sides else front_side)
        seg = geo.edges_of(entrance_room.rect)[side]
        cx, cy = geo.midpoint(seg)
        doors.append({"type": "main_entrance", "room_id": entrance_room.room_id, "wall": side,
                      "width": DOOR_WIDTH_MAIN, "center_x": round(cx, 2), "center_y": round(cy, 2)})

    rects = [r for r in rooms if r.rect]

    # Every candidate wall shared by two rooms, wide enough for a doorway.
    candidates: list[tuple[float, tuple[float, float, float, float], RoomInstance, RoomInstance]] = []
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            shared = geo.shared_segment(a.rect, b.rect)
            if not shared:
                continue
            _, _, seg = shared
            length = geo.segment_length(seg)
            if length >= DOOR_WIDTH_INTERNAL:
                candidates.append((length, seg, a, b))

    # Connect every room into a single spanning tree (Kruskal's, widest wall
    # first) instead of letting each room pick only its own single best
    # neighbor -- that greedy approach could silently leave a whole cluster of
    # rooms (e.g. a bedroom wing) with doors only to each other and no route
    # at all back to the living room / rest of the house.
    parent = {r.room_id: r.room_id for r in rects}

    def find(room_id: str) -> str:
        while parent[room_id] != room_id:
            parent[room_id] = parent[parent[room_id]]
            room_id = parent[room_id]
        return room_id

    for length, seg, a, b in sorted(candidates, key=lambda c: -c[0]):
        root_a, root_b = find(a.room_id), find(b.room_id)
        if root_a == root_b:
            continue
        parent[root_a] = root_b
        cx, cy = geo.midpoint(seg)
        doors.append({"type": "internal", "room_id": a.room_id, "connects_to": b.room_id,
                      "width": DOOR_WIDTH_INTERNAL, "center_x": round(cx, 2), "center_y": round(cy, 2)})
    return doors


def _place_furniture(room: RoomInstance) -> list[dict]:
    if not room.rect or not room.furniture:
        return []
    r = room.rect
    placed = []
    margin = 0.5
    cursor_x, cursor_y = r["x"] + margin, r["y"] + margin
    along_x = r["w"] >= r["l"]
    used = 0.0
    limit = (r["w"] if along_x else r["l"]) - margin
    for item in room.furniture:
        size_along = item["w"] if along_x else item["l"]
        if used + size_along > limit:
            continue
        x = cursor_x if along_x else r["x"] + margin
        y = r["y"] + margin if along_x else cursor_y
        placed.append({"type": item["type"], "x": round(x, 2), "y": round(y, 2),
                       "w": item["w"], "l": item["l"], "rotation": 0})
        used += size_along + 0.3
        if along_x:
            cursor_x += size_along + 0.3
        else:
            cursor_y += size_along + 0.3
    return placed


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def generate_floor_plan(req: RequirementCreate) -> dict:
    base_rect = compute_buildable_rect(req.plot_length, req.plot_width, req.facing)
    rooms = build_room_program(req)

    stair_side = "west"
    if req.facing == "west":
        stair_side = "east"
    elif req.facing == "east":
        stair_side = "west"

    if req.floors > 1:
        stair_strip, rooms_base_rect = geo.split_strip(base_rect, stair_side, STAIRCASE_WIDTH)
    else:
        stair_strip, rooms_base_rect = None, base_rect

    front_sb = _setback(
        req.plot_length if req.facing in ("north", "south") else req.plot_width, "front"
    )

    floors_data = []
    total_built_up_area = 0.0

    for floor_idx in range(req.floors):
        floor_rooms = [
            r for r in rooms if r.floor_index == floor_idx and r.room_type not in ("staircase", "veranda")
        ]
        stair_room = next((r for r in rooms if r.floor_index == floor_idx and r.room_type == "staircase"), None)
        veranda_room = next((r for r in rooms if r.floor_index == floor_idx and r.room_type == "veranda"), None)

        if floor_idx == 0:
            parking, outline, room_area_rect, full_outline = compute_parking(
                rooms_base_rect, req.facing, front_sb, req.cars, req.two_wheelers, full_rect=base_rect
            )
        else:
            parking, outline, room_area_rect, full_outline = None, rooms_base_rect, rooms_base_rect, base_rect

        if stair_room is not None and stair_strip is not None:
            # `stair_strip` is cut once from the unrecessed base_rect so it
            # stacks at an identical x/y position on every floor; on the
            # ground floor, trim it to the parking-receded footprint so it
            # stays fully inside that floor's exterior walls too.
            stair_room.rect = geo.rect_intersect(stair_strip, full_outline) if floor_idx == 0 else dict(stair_strip)
            stair_room.zone = "SW" if stair_side == "west" else "SE"

        # A veranda is a covered porch in front of the door, not just another
        # interior room -- carve it as a full-width strip off the front edge
        # (same technique as the staircase strip) so it always spans the
        # facade and sits between the entrance and every other room, rather
        # than landing as a single Vastu-grid cell that might only be a
        # corner sliver of the front wall.
        layout_rect = room_area_rect
        if veranda_room is not None and floor_idx == 0:
            veranda_strip, layout_rect = geo.split_strip(room_area_rect, _front_edge(req.facing), VERANDA_DEPTH)
            veranda_room.rect = veranda_strip
            veranda_room.zone = FRONT_ZONE_LABEL[req.facing]

        layout_floor(floor_rooms, layout_rect, req.vastu_compliant)

        all_placed = (
            [r for r in floor_rooms if r.rect]
            + ([stair_room] if stair_room and stair_room.rect else [])
            + ([veranda_room] if veranda_room and veranda_room.rect else [])
        )
        # The exterior wall envelope is always the true building footprint
        # (including the staircase strip), so the staircase reads as part of
        # the house's interior on every floor instead of a detached side block.
        floor_outline = full_outline

        room_dicts = []
        for room in all_placed:
            room_dicts.append({
                "id": room.room_id,
                "type": room.room_type,
                "label": room.label,
                "zone": room.zone,
                "x": round(room.rect["x"], 2),
                "y": round(room.rect["y"], 2),
                "width": round(room.rect["w"], 2),
                "length": round(room.rect["l"], 2),
                "area": round(geo.rect_area(room.rect), 2),
                "below_min_size": room.below_min,
                "furniture": _place_furniture(room),
                "rect": room.rect,  # kept for internal wall/door computation, harmless to expose
            })
            total_built_up_area += geo.rect_area(room.rect)

        windows = _build_windows(all_placed, floor_outline)
        entrance_id = None
        # Duplex: only the ground floor gets a "front door" -- upper floors
        # are the same household, reached via the internal staircase.
        # Independent floors: every floor is its own unit off the shared
        # staircase landing, so every floor gets its own front door.
        if floor_idx == 0 or is_independent_floors(req):
            # if both a veranda and a foyer are present, the main door sits on
            # the veranda -- it's the outermost, street-facing room
            entrance_candidates = (
                [r for r in all_placed if r.room_type == "veranda"]
                or [r for r in all_placed if r.room_type == "foyer"]
                or [r for r in all_placed if r.room_type == "living_room"]
                or all_placed
            )
            entrance_id = entrance_candidates[0].room_id if entrance_candidates else None
        doors = _build_doors(all_placed, floor_outline, req.facing, entrance_id)
        walls = _build_walls(floor_outline, room_dicts)

        ramp = None
        main_gate = None
        if floor_idx == 0:
            entrance_door = next((d for d in doors if d["type"] == "main_entrance"), None)
            plot_rect = {"x": 0.0, "y": 0.0, "w": req.plot_width, "l": req.plot_length}
            if req.wheelchair_accessible:
                ramp = compute_ramp(entrance_door, plot_rect, parking)
            main_gate = compute_main_gate(plot_rect, req.facing, parking, entrance_door)

        for rd in room_dicts:
            rd.pop("rect", None)

        floors_data.append({
            "floor_number": floor_idx,
            "label": "Ground Floor" if floor_idx == 0 else f"Floor {floor_idx}",
            "outline": {"x": round(floor_outline["x"], 2), "y": round(floor_outline["y"], 2),
                       "width": round(floor_outline["w"], 2), "length": round(floor_outline["l"], 2)},
            "rooms": room_dicts,
            "walls": walls,
            "doors": doors,
            "windows": windows,
            "parking": {
                "x": round(parking["x"], 2), "y": round(parking["y"], 2),
                "width": round(parking["w"], 2), "length": round(parking["l"], 2),
                "capacity_cars": parking["capacity_cars"], "capacity_two_wheelers": parking["capacity_two_wheelers"],
            } if parking else None,
            "ramp": {
                "x": round(ramp["x"], 2), "y": round(ramp["y"], 2),
                "width": round(ramp["w"], 2), "length": round(ramp["l"], 2), "side": ramp["side"],
            } if ramp else None,
            "main_gate": {
                "x": round(main_gate["x"], 2), "y": round(main_gate["y"], 2),
                "width": round(main_gate["width"], 2), "side": main_gate["side"],
            } if main_gate else None,
            "has_staircase": stair_room is not None,
        })

    plan = {
        "meta": {
            "plot_length": req.plot_length,
            "plot_width": req.plot_width,
            "unit": "feet",
            "facing": req.facing,
            "floors": req.floors,
            "vastu_compliant": req.vastu_compliant,
            "compound_wall_style": req.compound_wall_style,
            "gate_style": req.gate_style,
            "total_built_up_area": round(total_built_up_area, 2),
            "buildable_footprint": {"x": round(base_rect["x"], 2), "y": round(base_rect["y"], 2),
                                     "width": round(base_rect["w"], 2), "length": round(base_rect["l"], 2)},
        },
        "floors": floors_data,
    }
    return plan, round(total_built_up_area, 2)
