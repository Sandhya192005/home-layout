# Room geometry rules

Always-applicable invariants for anything that touches room rects, walls,
doors, or windows in the backend (`services/floorplan_generator.py`,
`services/geometry.py`) or reads/writes `plan_data` directly. Referenced
from `CLAUDE.md` — read that first for the surrounding architecture.

## 1. Rooms are always axis-aligned rectangles — never propose an L-shape

The room model (`{"x", "y", "width", "length"}` per room, everywhere in
`plan_data`) has no polygon support. A rectangle can only be split into two
*rectangles* by cutting a full-width or full-length strip off one edge
(`geo.split_strip` — used for the staircase strip, the veranda strip, and
the attached-bathroom cut). Cutting a corner notch out of a rectangle always
leaves an L-shaped (6-sided) remainder, which cannot be represented.

**Before implementing any feature that subdivides or reshapes a room**
(a new attached space, a partition wall, merging two rooms), check whether
it can be expressed as one or more full-edge strip cuts. If it can't without
producing an L-shape, that is a real modeling limit — do not work around it
by inventing a polygon field or silently approximating with a rectangle
that doesn't match the visual intent. Say so and ask, or scope the feature
down to what strip cuts can actually express (see `add_attached_bathroom`
in `floorplan_generator.py` for the reference implementation of this
trade-off).

## 2. Rebuilding doors/walls from *stored* (already-rounded) rects needs a larger touch tolerance

`geo.shared_segment(rect_a, rect_b, tolerance=...)` decides whether two
rects "touch" (share a wall long enough for a door). Its default tolerance
is exact-geometry `EPS` (~1e-6), which is correct for the *initial*
generation pass (`generate_floor_plan`) — every room rect there comes from
one shared full-precision layout computation, so two rooms meant to touch
align exactly before they're rounded for output.

Any other code path works from rects that are **already independently
rounded to 2 decimals** (persisted `plan_data`, before or after a manual
edit). Two such rooms that were meant to touch exactly can differ by a
~0.01ft rounding sliver. At the strict default tolerance, `shared_segment`
treats that sliver as a gap and drops what should still be a valid doorway
or wall — and since `_build_doors` builds a spanning **tree** (not a
general graph), losing one edge can disconnect an entire branch of rooms
even though nothing about the actual layout changed.

**Rule**: any function that calls `_build_doors` / `_build_walls` (or
`geo.shared_segment` directly) using rects read back from stored
`plan_data` must pass an explicit larger `tolerance` — `0.05` is the
existing convention, matching the overlap-check tolerance already used in
`api/v1/floorplans.py`'s room-layout endpoint. `recompute_floor_geometry`
already does this; follow its example rather than the strict default used
by `generate_floor_plan`.

**When adding a new geometry-mutating feature**, verify this concretely,
don't just trust the code: generate a plan, call your new function, and
assert `rooms_are_connected(...)` — ideally across a few different plot
sizes/room programs, since whether a rounding sliver actually bites depends
on the specific coordinates involved (see `test_attached_bathroom.py`'s
`test_add_attached_bathroom_across_room_sizes` for the pattern).
