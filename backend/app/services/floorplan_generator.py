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


def build_room_program(req: RequirementCreate) -> list[RoomInstance]:
    rooms: list[RoomInstance] = []
    seq = 0
    floors = req.floors

    def nxt() -> int:
        nonlocal seq
        seq += 1
        return seq

    # Ground floor common rooms
    rooms.append(_make_room("foyer", 0, nxt()))
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
        for _ in range(total_bathrooms):
            rooms.append(_make_room("bathroom", 0, nxt()))
        if req.has_study_room:
            rooms.append(_make_room("study_room", 0, nxt()))
        for extra in extra_upper:
            rooms.append(_make_room(extra, 0, nxt()))
        for _ in range(req.balconies):
            rooms.append(_make_room("balcony", 0, nxt()))
    else:
        upper_floor_count = floors - 1
        # one common bathroom stays on the ground floor
        rooms.append(_make_room("bathroom", 0, nxt()))
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
        preference = room.zones if vastu else FALLBACK_ZONE_ORDER
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

def compute_parking(base_rect: dict, facing: str, front_sb: float, cars: int, two_wheelers: int):
    if cars <= 0 and two_wheelers <= 0:
        return None, base_rect, base_rect

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
    return parking, outline, room_rect


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
    for i, a in enumerate(rects):
        best = None
        best_len = 0.0
        for b in rects:
            if a is b:
                continue
            shared = geo.shared_segment(a.rect, b.rect)
            if not shared:
                continue
            _, _, seg = shared
            length = geo.segment_length(seg)
            if length > best_len:
                best_len = length
                best = (b, seg)
        if best and best_len >= DOOR_WIDTH_INTERNAL:
            b, seg = best
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
        floor_rooms = [r for r in rooms if r.floor_index == floor_idx and r.room_type != "staircase"]
        stair_room = next((r for r in rooms if r.floor_index == floor_idx and r.room_type == "staircase"), None)

        if floor_idx == 0:
            parking, outline, room_area_rect = compute_parking(
                rooms_base_rect, req.facing, front_sb, req.cars, req.two_wheelers
            )
        else:
            parking, outline, room_area_rect = None, rooms_base_rect, rooms_base_rect

        if stair_room is not None and stair_strip is not None:
            stair_room.rect = dict(stair_strip)
            stair_room.zone = "SW" if stair_side == "west" else "SE"

        layout_floor(floor_rooms, room_area_rect, req.vastu_compliant)

        all_placed = [r for r in floor_rooms if r.rect] + ([stair_room] if stair_room and stair_room.rect else [])
        floor_outline = outline if floor_idx == 0 else base_rect

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
        if floor_idx == 0:
            entrance_candidates = [r for r in all_placed if r.room_type == "foyer"] or \
                [r for r in all_placed if r.room_type == "living_room"] or all_placed
            entrance_id = entrance_candidates[0].room_id if entrance_candidates else None
        doors = _build_doors(all_placed, floor_outline, req.facing, entrance_id)
        walls = _build_walls(floor_outline, room_dicts)

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
            "total_built_up_area": round(total_built_up_area, 2),
            "buildable_footprint": {"x": round(base_rect["x"], 2), "y": round(base_rect["y"], 2),
                                     "width": round(base_rect["w"], 2), "length": round(base_rect["l"], 2)},
        },
        "floors": floors_data,
    }
    return plan, round(total_built_up_area, 2)
