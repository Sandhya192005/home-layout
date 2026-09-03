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


def _target_aspect(occupants: list[RoomInstance]) -> float:
    """Desired length:width ratio to aim for when a shared dimension is being
    divided among sibling groups: a lone room's own min_l/min_w, or a neutral
    1.0 (aim square) once there's more than one occupant — multiple occupants
    get their actual proportions sorted out by the width-wise column split
    that follows, so the group itself only needs to end up roughly square."""
    if len(occupants) == 1 and occupants[0].min_w > 0:
        return occupants[0].min_l / occupants[0].min_w
    return 1.0


def _squarify_blend(occupant_count: int) -> float:
    """How strongly to bias a shared dimension's split toward each group's
    aspect-ratio target instead of pure weight share. A lone occupant that
    must span the same full width as its (possibly much heavier) siblings
    needs the strongest correction — pure weight share would starve it down
    to a sliver of height, however wide it ends up. Multi-occupant groups
    already get to fix their own shape via the width-wise split that
    follows, so they need less (but still some) nudging."""
    return {1: 0.75, 2: 0.55}.get(occupant_count, 0.35)


def _squarified_shares(
    weights: list[float], aspects: list[float], occupant_counts: list[int], total_area: float
) -> list[float]:
    """Weight-like shares for `subdivide_min_aware`'s shared dimension,
    biased toward each item's own roughly-`aspect` (length:width) shape
    rather than pure weight share. Pure weight share starves a
    lightly-weighted item that must span the same full width as its
    siblings into a thin sliver: it gets only a tiny fraction of the shared
    height to go with that full width, regardless of what shape it actually
    needs. This trades away *exact* weight-proportional area — some area
    shifts between siblings — for saner shapes; `subdivide_min_aware`
    re-normalizes whatever is returned here by its own sum, and its `min`
    floor still applies on top, so total space used and minimum-size
    guarantees are unaffected either way."""
    total_weight = sum(weights) or 1.0
    total_area = max(total_area, 1e-6)
    ideal = [math.sqrt(max(total_area * (w / total_weight) * a, 1e-6)) for w, a in zip(weights, aspects)]
    ideal_total = sum(ideal) or 1.0
    blends = [_squarify_blend(n) for n in occupant_counts]
    return [
        blends[i] * (ideal[i] / ideal_total) + (1 - blends[i]) * (weights[i] / total_weight)
        for i in range(len(weights))
    ]


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
    plain weight split happened to shortchange them.

    Row heights (and, within a 3-column row, its two sub-row depths) are then
    picked with `_squarified_shares` rather than pure weight share, so a
    lightly-weighted room that ends up alone in a row doesn't get stretched
    into a wide, shallow sliver just because it must span the same width as
    everything else on the floor."""
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

    row_occupants = [[rm for col in range(3) for rm in cells[(row, col)]] for row in range(3)]
    row_shares = _squarified_shares(
        row_weight,
        [_target_aspect(row_occupants[row]) for row in range(3)],
        [len(row_occupants[row]) for row in range(3)],
        geo.rect_area(buildable),
    )
    row_items = [{"weight": row_shares[row], "min": row_min[row]} for row in range(3)]
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
            group_a_occupants = [rm for c in group_a for rm in cells[(row, c)]]
            group_b_occupants = [rm for c in group_b for rm in cells[(row, c)]]
            weight_a = sum(rm.weight for rm in group_a_occupants) or 0.1
            weight_b = sum(rm.weight for rm in group_b_occupants) or 0.1
            shares = _squarified_shares(
                [weight_a, weight_b],
                [_target_aspect(group_a_occupants), _target_aspect(group_b_occupants)],
                [len(group_a_occupants), len(group_b_occupants)],
                geo.rect_area(row_rect),
            )
            sub_rows = geo.subdivide_min_aware(
                row_rect,
                "y",
                [{"weight": shares[0], "min": depth_a}, {"weight": shares[1], "min": depth_b}],
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

    # Parking rect sits in the reclaimed strip nearest the West/North corner
    # of the front edge -- anchored to the *true plot boundary*, not
    # `base_rect`'s edge, since open parking is allowed within the mandatory
    # front setback itself. `base_rect`'s front edge already sits `front_sb`
    # inside the plot boundary, so parking's depth (always exactly
    # `depth_needed`, since front_sb + extra_depth == max(front_sb,
    # depth_needed) >= depth_needed) has to start `front_sb` further out to
    # end up flush with the receded `outline`/`full_outline` above, instead
    # of overlapping the first `front_sb` feet of room space.
    if facing == "north":
        parking = {"x": base_rect["x"], "y": base_rect["y"] - front_sb, "w": width_needed, "l": depth_needed}
    elif facing == "south":
        parking = {
            "x": base_rect["x"], "y": geo.rect_y2(base_rect) + front_sb - depth_needed, "w": width_needed, "l": depth_needed,
        }
    elif facing == "west":
        parking = {"x": base_rect["x"] - front_sb, "y": base_rect["y"], "w": depth_needed, "l": width_needed}
    else:  # east
        parking = {
            "x": geo.rect_x2(base_rect) + front_sb - depth_needed, "y": base_rect["y"], "w": depth_needed, "l": width_needed,
        }

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

def _build_walls(outline: dict, room_rects: list[dict], tolerance: float = geo.EPS) -> list[dict]:
    walls = []
    for side, seg in geo.edges_of(outline).items():
        walls.append({"x1": seg[0], "y1": seg[1], "x2": seg[2], "y2": seg[3],
                       "thickness": WALL_THICKNESS_EXTERIOR, "type": "exterior", "side": side})
    seen = set()
    for i, a in enumerate(room_rects):
        for b in room_rects[i + 1:]:
            shared = geo.shared_segment(a["rect"], b["rect"], tolerance=tolerance)
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


def _build_doors(
    rooms: list[RoomInstance], outline: dict, facing: str, entrance_room_id: str | None, tolerance: float = geo.EPS
) -> list[dict]:
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
            shared = geo.shared_segment(a.rect, b.rect, tolerance=tolerance)
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


# ---------------------------------------------------------------------------
# Manual room editing: re-derive walls/doors/windows/area for one floor after
# a user hand-edits room rectangles (drag-to-move/resize in the frontend),
# reusing the exact same derivation the initial generation pipeline uses so a
# hand-edited layout keeps the same guarantees (real shared-wall doors, every
# room reachable) as a freshly generated one.
# ---------------------------------------------------------------------------

def recompute_floor_geometry(floor: dict, facing: str) -> None:
    """Mutates `floor` (one entry of plan_data["floors"]) in place: recomputes
    each room's area/below_min_size from its current x/y/width/length, then
    rebuilds windows, doors and walls from scratch. The floor's outline and
    parking/ramp/main_gate are untouched -- only the room grid inside the
    fixed exterior envelope is re-derived."""
    outline = {"x": floor["outline"]["x"], "y": floor["outline"]["y"],
               "w": floor["outline"]["width"], "l": floor["outline"]["length"]}

    room_instances: list[RoomInstance] = []
    for rd in floor["rooms"]:
        rect = {"x": rd["x"], "y": rd["y"], "w": rd["width"], "l": rd["length"]}
        meta = ROOM_LIBRARY[rd["type"]]
        instance = RoomInstance(
            room_id=rd["id"], room_type=rd["type"], label=rd["label"], weight=0, priority=0,
            zones=[], habitable=meta["habitable"], min_w=meta["min_w"], min_l=meta["min_l"],
            furniture=[], floor_index=0, zone=rd.get("zone"), rect=rect,
        )
        instance.below_min = rect["w"] < instance.min_w - 0.5 or rect["l"] < instance.min_l - 0.5
        room_instances.append(instance)
        rd["area"] = round(geo.rect_area(rect), 2)
        rd["below_min_size"] = instance.below_min

    existing_entrance_door = next((d for d in floor["doors"] if d["type"] == "main_entrance"), None)
    entrance_id = existing_entrance_door["room_id"] if existing_entrance_door else None

    room_dicts_for_walls = [{"id": ri.room_id, "rect": ri.rect} for ri in room_instances]

    # Room rects here are already 2-decimal-rounded (each stored independently
    # since generation, or just carved by an attached-bathroom cut), so two
    # rooms meant to touch exactly can be a ~0.01ft rounding sliver apart --
    # a larger tolerance than the initial (unrounded) generation pass keeps
    # that from silently dropping a doorway/wall between them. Matches the
    # overlap tolerance the room-layout-edit endpoint already uses for the
    # same reason.
    tolerance = 0.05
    floor["windows"] = _build_windows(room_instances, outline)
    floor["doors"] = _build_doors(room_instances, outline, facing, entrance_id, tolerance=tolerance)
    floor["walls"] = _build_walls(outline, room_dicts_for_walls, tolerance=tolerance)


def rooms_are_connected(room_ids: list[str], doors: list[dict]) -> bool:
    """True if every room in `room_ids` is reachable from every other one via
    the floor's internal doors (union-find over the door graph) -- the same
    connectivity `_build_doors`'s spanning tree normally guarantees, checked
    here after a manual edit since hand-moved rects might no longer share a
    wall wide enough for a doorway."""
    parent = {rid: rid for rid in room_ids}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for d in doors:
        if d["type"] == "internal":
            root_a, root_b = find(d["room_id"]), find(d["connects_to"])
            if root_a != root_b:
                parent[root_a] = root_b

    roots = {find(rid) for rid in room_ids}
    return len(roots) <= 1


# ---------------------------------------------------------------------------
# Attached bathroom: add/remove a bathroom carved from an existing room,
# reusing the exact same strip-cut (`geo.split_strip`) already used for the
# staircase/veranda strips above, and the same recompute/connectivity checks
# manual room edits use -- so an attached bathroom gets real doors/walls and
# the same "every room reachable" guarantee as everything else on the floor.
# ---------------------------------------------------------------------------

ATTACHED_BATHROOM_INELIGIBLE_TYPES = {
    "bathroom", "accessible_bathroom", "staircase", "veranda", "foyer",
    "balcony", "utility", "pooja_room", "kitchen",
}


def _cardinal_letters(zones: list[str]) -> set[str]:
    letters: set[str] = set()
    for zone in zones:
        letters.update(zone)
    return letters


def _merge_adjacent_rects(a: dict, b: dict) -> dict | None:
    """Union of two rects into one exact rectangle, if they share a full
    common edge -- the inverse of `geo.split_strip`. Returns None if they no
    longer tile cleanly (e.g. one side was manually resized afterward)."""
    tol = 0.05
    if abs(a["l"] - b["l"]) < tol and abs(a["y"] - b["y"]) < tol:
        if abs((a["x"] + a["w"]) - b["x"]) < tol:
            return {"x": a["x"], "y": a["y"], "w": a["w"] + b["w"], "l": a["l"]}
        if abs((b["x"] + b["w"]) - a["x"]) < tol:
            return {"x": b["x"], "y": a["y"], "w": a["w"] + b["w"], "l": a["l"]}
    if abs(a["w"] - b["w"]) < tol and abs(a["x"] - b["x"]) < tol:
        if abs((a["y"] + a["l"]) - b["y"]) < tol:
            return {"x": a["x"], "y": a["y"], "w": a["w"], "l": a["l"] + b["l"]}
        if abs((b["y"] + b["l"]) - a["y"]) < tol:
            return {"x": a["x"], "y": b["y"], "w": a["w"], "l": a["l"] + b["l"]}
    return None


def add_attached_bathroom(floor: dict, room_id: str, facing: str, vastu: bool) -> tuple[dict, list[str]]:
    """Carves a rectangular attached-bathroom strip off one edge of the given
    room (in place on `floor`), picking whichever edge scores best (an
    exterior wall for ventilation, a Vastu-preferred direction when enabled)
    among every edge that leaves both the bathroom and the remaining room at
    or above their minimum usable size, doesn't overlap another room, and
    keeps every room on the floor reachable. Returns (new_room_dict,
    warnings). Raises ValueError -- the caller turns this into a 400 -- if no
    edge works, with a message explaining why."""
    rooms_by_id = {r["id"]: r for r in floor["rooms"]}
    room = rooms_by_id.get(room_id)
    if room is None:
        raise ValueError(f"Room '{room_id}' was not found on this floor.")
    if room["type"] in ATTACHED_BATHROOM_INELIGIBLE_TYPES:
        raise ValueError(f"A {room['label']} isn't a suitable room for an attached bathroom.")
    if room.get("attached_bathroom_id"):
        raise ValueError(f"{room['label']} already has an attached bathroom.")

    bath_meta = ROOM_LIBRARY["bathroom"]
    parent_meta = ROOM_LIBRARY[room["type"]]
    outline = {"x": floor["outline"]["x"], "y": floor["outline"]["y"],
               "w": floor["outline"]["width"], "l": floor["outline"]["length"]}
    room_rect = {"x": room["x"], "y": room["y"], "w": room["width"], "l": room["length"]}
    room_boundary_sides = geo.on_boundary(room_rect, outline)
    other_rects = [
        {"x": o["x"], "y": o["y"], "w": o["width"], "l": o["length"]}
        for o in floor["rooms"] if o["id"] != room_id
    ]
    vastu_letters = _cardinal_letters(bath_meta["zones"]) if vastu else set()

    # Every edge that leaves both pieces at/above their minimum usable size
    # and doesn't overlap another room, scored by exterior-wall access (for a
    # window) and Vastu direction preference.
    candidates: list[tuple[float, str, dict, dict]] = []
    for side in ("south", "east", "north", "west"):
        depth_axis_size = room_rect["l"] if side in ("north", "south") else room_rect["w"]
        default_depth = bath_meta["min_l"] if side in ("north", "south") else bath_meta["min_w"]
        depth = min(default_depth, depth_axis_size * 0.45)
        if depth <= 0.1:
            continue
        bath_rect, rest_rect = geo.split_strip(room_rect, side, depth)
        if bath_rect["w"] < bath_meta["min_w"] - 0.25 or bath_rect["l"] < bath_meta["min_l"] - 0.25:
            continue
        if rest_rect["w"] < parent_meta["min_w"] - 0.25 or rest_rect["l"] < parent_meta["min_l"] - 0.25:
            continue
        if any(geo.rects_overlap(bath_rect, o, tolerance=0.05) for o in other_rects):
            continue
        score = 0.0
        if side in room_boundary_sides:
            score += 2.0
        if vastu and side in vastu_letters:
            score += 1.5
        candidates.append((score, side, bath_rect, rest_rect))

    if not candidates:
        raise ValueError(
            f"{room['label']} is too small to fit an attached bathroom without shrinking either room below its "
            f"minimum usable size."
        )
    candidates.sort(key=lambda c: -c[0])

    new_id = f"bathroom_attached_{room_id}"
    for _score, side, bath_rect, rest_rect in candidates:
        # Try the cut on a scratch copy first -- only commit it to the real
        # floor once we've confirmed (via the same recompute + connectivity
        # check a manual room edit gets) that it doesn't strand any room.
        trial_rooms = [dict(r) for r in floor["rooms"]]
        trial_room = next(r for r in trial_rooms if r["id"] == room_id)
        trial_room["x"], trial_room["y"] = round(rest_rect["x"], 2), round(rest_rect["y"], 2)
        trial_room["width"], trial_room["length"] = round(rest_rect["w"], 2), round(rest_rect["l"], 2)
        trial_room["furniture"] = []
        trial_room["attached_bathroom_id"] = new_id

        bath_instance = RoomInstance(
            room_id=new_id, room_type="bathroom", label="Attached Bathroom", weight=0, priority=0,
            zones=[], habitable=False, min_w=bath_meta["min_w"], min_l=bath_meta["min_l"],
            furniture=[dict(item) for item in bath_meta["furniture"]], floor_index=0, rect=bath_rect,
        )
        new_room = {
            "id": new_id, "type": "bathroom", "label": "Attached Bathroom", "zone": room.get("zone"),
            "x": round(bath_rect["x"], 2), "y": round(bath_rect["y"], 2),
            "width": round(bath_rect["w"], 2), "length": round(bath_rect["l"], 2),
            "area": round(geo.rect_area(bath_rect), 2), "below_min_size": False,
            "furniture": _place_furniture(bath_instance), "attached_to": room_id,
        }
        trial_rooms.append(new_room)
        trial_floor = {"outline": floor["outline"], "rooms": trial_rooms, "doors": floor["doors"]}
        recompute_floor_geometry(trial_floor, facing)
        if not rooms_are_connected([r["id"] for r in trial_rooms], trial_floor["doors"]):
            continue

        floor["rooms"] = trial_rooms
        floor["doors"] = trial_floor["doors"]
        floor["windows"] = trial_floor["windows"]
        floor["walls"] = trial_floor["walls"]

        warnings: list[str] = []
        if side in geo.on_boundary(bath_rect, outline):
            seg = geo.edges_of(bath_rect)[side]
            vent_width = round(min(WINDOW_WIDTH_DEFAULT, max(geo.segment_length(seg) * 0.4, 1.5)), 2)
            cx, cy = geo.midpoint(seg)
            floor["windows"].append({
                "room_id": new_id, "wall": side, "width": vent_width,
                "center_x": round(cx, 2), "center_y": round(cy, 2),
            })
            new_room["has_window"] = True
        else:
            new_room["has_window"] = False
            warnings.append(
                f"Attached Bathroom for {room['label']} doesn't reach an exterior wall, so it has no window -- "
                f"plan for a mechanical exhaust fan for ventilation instead."
            )
        return new_room, warnings

    raise ValueError(
        f"Adding an attached bathroom to {room['label']} would cut off part of the house from the rest -- try a "
        f"different room."
    )


def remove_attached_bathroom(floor: dict, room_id: str, facing: str) -> list[str]:
    """Removes `room_id`'s attached bathroom (in place on `floor`) and, where
    the two rects still tile cleanly, merges its space back into the room --
    the exact inverse of `add_attached_bathroom`'s strip cut. Raises
    ValueError if the room doesn't have an attached bathroom."""
    rooms_by_id = {r["id"]: r for r in floor["rooms"]}
    room = rooms_by_id.get(room_id)
    if room is None:
        raise ValueError(f"Room '{room_id}' was not found on this floor.")
    bath_id = room.get("attached_bathroom_id")
    bath = rooms_by_id.get(bath_id) if bath_id else None
    if not bath:
        raise ValueError(f"{room['label']} does not have an attached bathroom.")

    room_rect = {"x": room["x"], "y": room["y"], "w": room["width"], "l": room["length"]}
    bath_rect = {"x": bath["x"], "y": bath["y"], "w": bath["width"], "l": bath["length"]}
    merged = _merge_adjacent_rects(room_rect, bath_rect)

    warnings: list[str] = []
    if merged is not None:
        room["x"], room["y"] = round(merged["x"], 2), round(merged["y"], 2)
        room["width"], room["length"] = round(merged["w"], 2), round(merged["l"], 2)
        room["furniture"] = []
    else:
        warnings.append(
            f"Removed the attached bathroom, but its space couldn't be automatically returned to {room['label']} "
            f"because the rooms had been resized since it was added -- drag {room['label']}'s edge in the room "
            f"layout editor to reclaim the space."
        )
    room.pop("attached_bathroom_id", None)
    floor["rooms"] = [r for r in floor["rooms"] if r["id"] != bath_id]
    recompute_floor_geometry(floor, facing)
    if not rooms_are_connected([r["id"] for r in floor["rooms"]], floor["doors"]):
        warnings.append(
            "Removing this bathroom left one or more rooms unreachable -- you may need to adjust the layout."
        )
    return warnings


# ---------------------------------------------------------------------------
# Replace room: change one room's type in place (e.g. Bathroom -> Kitchen),
# reusing its existing rect exactly as-is rather than re-slicing the grid --
# a pure relabel-plus-refurnish, not a resize. Only structural/entrance-role
# room types (staircase/veranda/foyer) are off limits, since those carry
# generation-time meaning (staircase stacks across floors at a fixed strip;
# veranda/foyer are pinned to the street-facing edge) that a type swap alone
# can't preserve.
# ---------------------------------------------------------------------------

ROOM_REPLACE_INELIGIBLE_TYPES = {"staircase", "veranda", "foyer"}
WET_ROOM_TYPES = {"bathroom", "accessible_bathroom", "kitchen", "utility"}


def replace_room(floor: dict, room_id: str, new_type: str, facing: str, vastu: bool) -> tuple[dict, list[str]]:
    """Converts `room_id` (in place on `floor`) to `new_type`, keeping its
    current x/y/width/length exactly as-is. Rebuilds that room's furniture
    for the new type and re-derives windows/doors/walls (only this room's
    own window can actually change, since doors/walls depend only on rects,
    which are untouched). Returns (updated_room_dict, warnings). Raises
    ValueError -- the caller turns this into a 400 -- if the replacement
    isn't feasible, with a message explaining why."""
    rooms_by_id = {r["id"]: r for r in floor["rooms"]}
    room = rooms_by_id.get(room_id)
    if room is None:
        raise ValueError(f"Room '{room_id}' was not found on this floor.")
    if new_type not in ROOM_LIBRARY:
        raise ValueError(f"'{new_type}' isn't a recognized room type.")
    if room["type"] == new_type:
        raise ValueError(f"{room['label']} is already a {ROOM_LIBRARY[new_type]['label']}.")
    if room["type"] in ROOM_REPLACE_INELIGIBLE_TYPES:
        raise ValueError(f"A {room['label']} can't be replaced with another room type.")
    if new_type in ROOM_REPLACE_INELIGIBLE_TYPES:
        raise ValueError(
            f"Can't replace {room['label']} with a {ROOM_LIBRARY[new_type]['label']} -- that room type is "
            f"placed automatically by the generator and can't be created here."
        )

    new_meta = ROOM_LIBRARY[new_type]
    rect = {"x": room["x"], "y": room["y"], "w": room["width"], "l": room["length"]}
    tol = 0.25
    if rect["w"] < new_meta["min_w"] - tol or rect["l"] < new_meta["min_l"] - tol:
        raise ValueError(
            f"A {new_meta['label']} needs at least {new_meta['min_w']:g}x{new_meta['min_l']:g} ft -- "
            f"{room['label']} is only {rect['w']:g}x{rect['l']:g} ft, too small to convert."
        )
    min_area = new_meta["min_w"] * new_meta["min_l"]
    if geo.rect_area(rect) < min_area - tol:
        raise ValueError(
            f"A {new_meta['label']} needs at least {min_area:g} sq ft -- {room['label']} is only "
            f"{geo.rect_area(rect):g} sq ft, too small to convert."
        )

    outline = {"x": floor["outline"]["x"], "y": floor["outline"]["y"],
               "w": floor["outline"]["width"], "l": floor["outline"]["length"]}
    other_rects = [
        {"x": o["x"], "y": o["y"], "w": o["width"], "l": o["length"]}
        for o in floor["rooms"] if o["id"] != room_id
    ]
    if geo.rect_x2(rect) > outline["x"] + outline["w"] + 0.05 or geo.rect_y2(rect) > outline["y"] + outline["l"] + 0.05:
        raise ValueError(f"{room['label']}'s footprint falls outside the buildable area -- this shouldn't happen.")
    if any(geo.rects_overlap(rect, o, tolerance=0.05) for o in other_rects):
        raise ValueError(f"{room['label']} overlaps another room -- this shouldn't happen.")

    new_instance = RoomInstance(
        room_id=room_id, room_type=new_type, label=new_meta["label"], weight=0, priority=0,
        zones=[], habitable=new_meta["habitable"], min_w=new_meta["min_w"], min_l=new_meta["min_l"],
        furniture=[dict(item) for item in new_meta["furniture"]], floor_index=0,
        zone=room.get("zone"), rect=rect,
    )

    # Trial on a scratch copy first -- same safety net every other
    # geometry-mutating endpoint uses, even though a type-only swap can't
    # actually change the door/wall graph (both depend only on rects, which
    # are unchanged here): it's what recomputes this room's window entry.
    trial_rooms = [dict(r) for r in floor["rooms"]]
    trial_room = next(r for r in trial_rooms if r["id"] == room_id)
    trial_room["type"] = new_type
    trial_room["label"] = new_meta["label"]
    trial_room["furniture"] = _place_furniture(new_instance)
    trial_floor = {"outline": floor["outline"], "rooms": trial_rooms, "doors": floor["doors"]}
    recompute_floor_geometry(trial_floor, facing)
    if not rooms_are_connected([r["id"] for r in trial_rooms], trial_floor["doors"]):
        raise ValueError(f"Replacing {room['label']} would leave part of the house unreachable -- try a different room.")

    floor["rooms"] = trial_rooms
    floor["doors"] = trial_floor["doors"]
    floor["windows"] = trial_floor["windows"]
    floor["walls"] = trial_floor["walls"]

    warnings: list[str] = []
    has_window = any(w["room_id"] == room_id for w in floor["windows"])
    on_exterior_wall = bool(geo.on_boundary(rect, outline))
    if new_meta["habitable"] and not has_window:
        warnings.append(
            f"{new_meta['label']} doesn't reach an exterior wall, so it has no window -- plan for a mechanical "
            f"exhaust fan or extra lighting instead."
        )
    if new_type in WET_ROOM_TYPES and not on_exterior_wall:
        warnings.append(
            f"{new_meta['label']} doesn't reach an exterior wall -- drainage/plumbing lines for it will need to "
            f"route through an adjacent wet area, so confirm feasibility with a plumber before building."
        )
    if vastu:
        zone = room.get("zone")
        if zone and zone not in new_meta["zones"]:
            warnings.append(
                f"Vastu traditionally places a {new_meta['label']} in the "
                f"{'/'.join(new_meta['zones'])} zone -- this room is in the {zone} zone."
            )

    room_dict = trial_room
    return room_dict, warnings
