# AI Home Layout — Project Status

Last updated: 2026-08-19

## What this project is

A system that takes a customer's home-building requirements (plot size,
family size, room program, parking, floors, budget, Vastu preference) and
generates a **customized 2D floor plan** — rooms, walls, doors, windows,
furniture, parking and staircase — sized and positioned specifically for
that input. Nothing is a fixed template: change the plot or the room count
and the generated plan changes with it.

## Scope

- **Backend: built and verified.** See `backend/README.md` for setup,
  architecture, and API details.
- **Frontend: not built yet.** Out of scope so far — this has been a
  backend-only effort. The plan JSON (`x`/`y`/`width`/`length` per room, in
  feet, plus walls/doors/windows/furniture/parking) is designed to be
  rendered directly onto an SVG or canvas by a future React frontend.

## Stack

Python · FastAPI · PostgreSQL · SQLAlchemy 2.0 · Alembic · JWT auth
(python-jose + bcrypt). No LLM/external AI API is used anywhere — floor-plan
generation is procedural geometry, and the "AI suggestions" feature is a
rule-based engine (isolated in its own module so it can be swapped for a
real LLM call later without touching anything else).

## How generation works (short version)

1. Compute a buildable rectangle from plot size, facing, and setback rules.
2. Build a room list from the customer's bedroom/bathroom/room-type inputs,
   split across floors.
3. Assign each room to a Vastu compass zone (or a functional fallback order
   if Vastu isn't requested).
4. Slice the buildable rectangle into room rectangles — weighted by room
   importance, but **guaranteeing each room's minimum size** whenever the
   floor has enough total space for the whole program.
5. Carve parking from the front setback (extra depth if vehicles don't fit).
6. Reserve a staircase strip (multi-floor only), aligned across floors.
7. Derive walls, doors, windows, and furniture placement from the final
   room rectangles.

This was verified to be genuinely **dynamic**: resubmitting a requirement
with a different plot width and car count produces a new, different plan
version with a different built-up area — not a static template.

## Verification

Two smoke tests live in `backend/scripts/` (no live database touched):

- `smoke_test_generator.py` — runs the generation engine directly across 4
  scenarios (small Vastu home, large multi-floor home, a very narrow
  3-floor plot, and a deliberately-too-small stress test).
- `smoke_test_api.py` — exercises the full HTTP API against an isolated
  in-memory SQLite database: register → login → create project → submit
  requirement → generate → fetch plan/suggestions → change requirement →
  regenerate (confirms version bumps and the plan actually changes) →
  cross-user access is correctly rejected (403).

Both pass as of this update.

## Recent work: layout-algorithm quality pass

The room-layout heuristic (in `backend/app/services/floorplan_generator.py`)
was reworked to reduce undersized/sliver rooms:

- Room-rectangle splits are now **minimum-size aware** — a room only gets
  squeezed below its recommended minimum when the floor genuinely doesn't
  have enough space for the whole program, not because a plain weight-based
  split happened to shortchange it.
- Rows of the 3×3 Vastu grid that end up with 3 occupied cells (which
  internally split into two stacked sub-rows) now get sized for *both*
  sub-rows' space needs up front, instead of being sized as if they were a
  single row and then halved again.
- Zone assignment is now biased to avoid tripling up a row's column count
  when Vastu compliance doesn't specifically require it, since that
  tripling is what forces the costly sub-row split in the first place.

Net effect, measured against the smoke-test scenarios: a large 2-floor
non-Vastu home went from 8/18 rooms flagged below minimum size to **0/18**;
a tight 22ft-wide 3-floor Vastu scenario improved from 10/20 to 9/20 (this
one remains genuinely space-constrained — no layout algorithm can fit
5 bedrooms' worth of minimums into an 11–16ft-wide buildable strip, and the
system correctly flags that via `below_min_size` rather than hiding it).

## Known limitations (by design, not overlooked)

- Setback and cost figures in `app/utils/constants.py` are illustrative
  defaults, not a specific municipal code.
- Every floor shares the same footprint (no upper-floor step-backs).
- The layout engine is a heuristic partitioner, not a full constraint
  solver — on very tight or oddly-shaped plots it can still be unable to
  satisfy every room's minimum size, and says so via `below_min_size`.

## Open items

- React frontend to render the generated plan (not started).
- Running against a real PostgreSQL instance requires the user's own DB
  credentials — only isolated SQLite has been used for testing so far, to
  avoid touching (or guessing credentials for) any live database found in
  the environment.
