---
name: add-geometry-endpoint
description: Checklist and reference pattern for adding a new backend endpoint that mutates room/floor geometry after generation (e.g. attach/remove a feature on a room, merge rooms, add a new carved-out space). Use whenever the task is "add a way to change the layout of an already-generated floor plan" in this home-layout project.
user-invocable: true
---

# Add a geometry-mutating endpoint

This project already has three endpoints that edit an existing
`FloorPlan.plan_data` in place: `PUT .../rooms` (drag-resize), `PUT
.../parking` (drag-resize parking), and `POST/DELETE
.../rooms/{room_id}/attached-bathroom` (carve/restore a bathroom). They all
follow the same shape. Reuse it rather than inventing a new one — see
`app/services/floorplan_generator.py`'s `add_attached_bathroom` /
`remove_attached_bathroom` for the fullest reference implementation, and
`.claude/rules/room-geometry.md` for the geometry invariants this pattern
exists to protect.

## Before writing code

1. Read `.claude/rules/room-geometry.md`. Confirm your feature can be
   expressed as one or more full-edge `geo.split_strip` cuts (or a plain
   move/resize of existing rects) — not a corner notch or any other
   non-rectangular shape.
2. Confirm what should happen to furniture, doors, and windows on any room
   whose rect changes. The existing convention: geometry-changing edits
   clear that room's `furniture` (stale positions would otherwise land
   outside the new bounds); doors/windows are always fully rebuilt, never
   patched incrementally.

## The pattern

1. **Validate eligibility up front**, before any geometry math: does the
   target room/pair exist on this floor, is its type/state actually
   eligible (e.g. `ATTACHED_BATHROOM_INELIGIBLE_TYPES`), is the requested
   change already applied or clearly nonsensical? Raise `ValueError` with a
   message written for the end user (it becomes the HTTP 400 `detail`
   directly) — see the existing messages in `floorplan_generator.py` for
   tone (plain language, names the actual room label, says what to try
   instead).

2. **Generate candidate geometries**, not just one. For attached-bathroom
   this means every edge (N/S/E/W) that could host the cut; score
   candidates (exterior-wall access for a window, Vastu-direction
   preference) and try best-first. Filter out any candidate that:
   - drops either resulting rect below its `ROOM_LIBRARY[...]["min_w"/"min_l"]`,
   - overlaps another room (`geo.rects_overlap(..., tolerance=0.05)`),
   - falls outside the floor outline.

3. **Trial each surviving candidate on a scratch copy, not the live `floor`
   dict.** Deep-enough-copy the room list (`[dict(r) for r in floor["rooms"]]`),
   apply the candidate's geometry to the copy, append/remove rooms as
   needed, then call `recompute_floor_geometry(trial_floor, facing)`
   followed by `rooms_are_connected(...)` on the trial. Only assign the
   trial's `rooms`/`doors`/`windows`/`walls` back onto the real `floor` once
   a candidate passes — never mutate `floor` speculatively. This is the
   only way to safely guarantee "every room still reachable" before
   committing, since `_build_doors` rebuilds the *entire* spanning tree from
   scratch each time (unrelated rooms' doors can change as a side effect).

4. **If every candidate fails**, raise a `ValueError` explaining why in
   plain language (too small / would disconnect the house) rather than
   picking the "least bad" invalid option.

5. **In the API route**: catch `ValueError` → `HTTPException(400,
   detail=str(exc))`. On success, call the shared `_recalculate_estimates`
   helper in `api/v1/floorplans.py` (recomputes `total_built_up_area` and
   the `cost_estimate`/`boq`/`construction_timeline`/`far` meta from the
   requirement's budget) before `flag_modified(plan, "plan_data")` +
   `db.commit()`. Every endpoint that changes room geometry must call this
   — it's easy to forget since the geometry mutation itself doesn't touch
   cost/area at all.

## Testing

Write tests (see `tests/test_attached_bathroom.py` for the fullest
example), covering at minimum:
- the happy path, asserting the affected rooms' new geometry, that a real
  door connects any new room to its neighbor, `rooms_are_connected(...)`
  passes, and `total_built_up_area`/cost/BOQ/FAR were recalculated;
- each rejection reason (too small, ineligible, already-applied, unknown
  room id) returns 400 with a message a user could act on;
- a deterministic unit-level test of the geometry function itself (hand-built
  minimal `floor` dict) for the "no valid candidate" path — don't rely
  solely on the generator's heuristics to reliably reproduce a failure case;
- a sweep across a few different plot sizes / room programs, since
  connectivity bugs from the rounding-tolerance issue (rule #2 in
  `.claude/rules/room-geometry.md`) are geometry-dependent and won't show
  up in every layout.

Run the full backend suite afterward (not just your new file) —
`recompute_floor_geometry`/`geo.shared_segment` are shared by every
existing geometry-editing endpoint, so a change there can regress
`test_room_layout.py` or `test_parking_layout.py` even if your new tests
pass.
