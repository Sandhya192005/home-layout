# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

Takes a customer's home-building requirements (plot size, family size, room
program, parking, floors, budget, Vastu preference) and procedurally
generates a customized 2D (and now 3D) floor plan (rooms, walls, doors,
windows, furniture, parking, staircase) — sized and positioned specifically
for that input, not a fixed template. Floor-plan generation, cost/BOQ
estimation, and manual post-generation edits (drag-resize, attaching a
bathroom to a room) are all pure geometry/rule-based logic — no LLM
involved. The one place an external AI API *is* used is the house Q&A chat
assistant (`services/chat_assistant.py`, `POST /api/v1/chat`), which calls
an NVIDIA NIM-hosted LLM (OpenAI-compatible chat completions) — see below.
(An earlier "AI suggestions" feature was removed early on — `alembic/
versions/0003_drop_ai_suggestions.py` — don't resurrect references to it.)

Two independent apps in one repo: `backend/` (FastAPI + PostgreSQL) and
`frontend/` (React 19 + Vite + TypeScript), talking over a REST API.

Note: `PROJECT_STATUS.md` says the frontend is "not built yet" — that is
stale. The frontend under `frontend/src/` is fully implemented (auth,
project/requirement flow, SVG floor-plan viewer plus a Three.js 3D view,
furniture editor, manual room-layout editor with undo/redo, room-type
replacement, PNG/PDF export, shareable public links, version compare).

`ARCHITECTURE.md` is the visual companion to this file — Mermaid diagrams
of the request flow, the generation pipeline, and the plan-editing loop.
Read it alongside this file's prose when you need the shape of the system
rather than the details.

## Commands

### Backend (`backend/`)

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install -r requirements.txt
cp .env.example .env        # edit DATABASE_URL / SECRET_KEY
alembic upgrade head         # apply migrations (Postgres must be running)
uvicorn app.main:app --reload   # serves on :8000, docs at /docs
```

Creating a new migration after changing a model:
```bash
alembic revision -m "description"   # write it by hand under alembic/versions/ — no autogenerate setup
```

Automated tests (`backend/tests/`, pytest, isolated in-memory SQLite per test
via a `client` fixture in `conftest.py` — never touches the configured
Postgres):
```bash
cd backend
.venv\Scripts\python.exe -m pytest         # run the full suite
.venv\Scripts\python.exe -m pytest -k test_regenerate_bumps_version_and_changes_plan   # run a single test
.venv\Scripts\python.exe -m pytest tests/test_replace_room.py -x -q   # one file, stop on first failure
```

`conftest.py` provides a **fixture ladder** — depend on the highest rung
you need and everything below it is built for you, rather than re-posting
the setup requests by hand:

| fixture | gives you |
| --- | --- |
| `client` | `TestClient` on a fresh in-memory SQLite DB (also resets `public_share_limiter`) |
| `auth_headers` | a registered+logged-in user's `Authorization` header |
| `project` | that user's created project (dict) |
| `requirement` | a saved requirement on it (3BHK, 55x40 north-facing, 2 floors) |
| `floor_plan` | the generated `FloorPlan` for that requirement |

Plus two helpers: `requirement_payload(**overrides)` builds a valid
requirement body with per-test tweaks (`requirement_payload(floors=1,
vastu_compliant=False)`), and `register_and_login(client, email, password)`
creates a *second* user — both are plain functions, imported inside the
test (`from tests.conftest import register_and_login`), and the second-user
helper is how every cross-user 403 test is written.

The two original standalone smoke-test scripts still work and cover the same
ground end-to-end (useful for a quick manual sanity check without pytest):
```bash
python backend/scripts/smoke_test_generator.py   # exercises the layout engine directly across 4 scenarios
python backend/scripts/smoke_test_api.py          # full HTTP flow: register -> project -> requirement -> generate -> regenerate -> cross-user 403 check
```

On Windows, `uvicorn --reload`'s file watcher can occasionally stop picking
up further changes after the first reload (silently keeps serving stale
code with no error in the log). If edits don't seem to take effect, check
for more than one process listening on port 8000 (`netstat -ano | grep
:8000` in Bash, `Get-NetTCPConnection -LocalPort 8000` in PowerShell).
Before killing anything, confirm via the process's command line (`Get-
CimInstance Win32_Process -Filter "Name='python.exe'" | Select
ProcessId,CommandLine`) that it's actually a `uvicorn`/`multiprocessing.spawn`
worker for *this* app, not an unrelated python process on the machine —
then kill all of them and start one fresh instance. Verify the fix by
confirming the route you expect is in `curl
http://127.0.0.1:8000/api/v1/openapi.json`, not just that the server responds.

### Frontend (`frontend/`)

```bash
cd frontend
npm install
cp .env.example .env        # VITE_API_BASE_URL, e.g. http://localhost:8000/api/v1
npm run dev                  # Vite dev server
npm run build                 # tsc -b && vite build
npm run lint                   # oxlint
```

No frontend test runner is configured.

## Safety and quality gates

The automated backend test suite (above) is fully isolated (in-memory
SQLite) and safe to run freely. Manually verifying a change against a
*running* backend (browser, curl, a scratch Python script) talks to
whatever `DATABASE_URL` points at — typically a real local Postgres with
real project data in it. Use a throwaway project (and delete it or its
extra floor-plan versions afterward) rather than generating test versions
inside the user's actual projects.

- **Backend has no static analysis** — no ruff/black/mypy/flake8 configured
  (check `requirements.txt` if that ever changes). `pytest` is the only
  automated gate. There is also no CI pipeline in this repo at all; running
  the suite locally before calling backend work done is the only check that
  happens.
- Any change to `services/floorplan_generator.py` or `services/geometry.py`
  is shared by every layout/editing feature — run the **full** backend
  suite afterward (`pytest`), not just a test file for the feature you
  touched. `test_generation.py`, `test_room_layout.py`,
  `test_parking_layout.py`, `test_attached_bathroom.py`,
  `test_replace_room.py`, and `test_plan_data_restore.py` all exercise this
  shared code from different angles and have each independently caught
  regressions here.
- `npm run lint` (oxlint, config in `.oxlintrc.json`) only enables
  `react/rules-of-hooks` and `react/only-export-components` beyond the
  defaults, and is **not** type-aware — it will not catch type errors.
  `npm run build` (`tsc -b && vite build`) is the real type-checking gate
  for the frontend.

## Backend architecture

```
app/
  core/       config (env-driven Settings), DB session, JWT/password security,
              rate_limit.py (in-process per-IP limiter, applied to the public
              share endpoint)
  models/     SQLAlchemy ORM (User, Project, Requirement, FloorPlan, FloorPlanShare, RefreshToken)
  schemas/    Pydantic request/response models
  crud/       DB access functions
  api/v1/     FastAPI routers (auth, projects, requirements, floorplans, public, chat)
  services/
    floorplan_generator.py  the dynamic layout engine (see below) — 1200+ lines, the core of the project
    geometry.py               rectangle/wall/door math helpers
    validation.py              requirement sanity checks
    cost_estimator.py          budget/BOQ/timeline/FAR estimation
    chat_assistant.py          house Q&A chat -- the one LLM/external-API call in the app (NVIDIA NIM)
  utils/constants.py    room library (sizes, Vastu zones, furniture), setback rules — swap these for a real locality's code
alembic/versions/   hand-written migrations (no autogenerate configured — write revisions manually)
```

All settings are env-driven through one `Settings` class
(`core/config.py`, `.env` via pydantic-settings) and every field has a
working default, so the app boots with no `.env` at all. Beyond
`DATABASE_URL`/`SECRET_KEY`: `ACCESS_TOKEN_EXPIRE_MINUTES` (60) /
`REFRESH_TOKEN_EXPIRE_DAYS` (30), `BACKEND_CORS_ORIGINS` (defaults cover
Vite's :5173 and :3000 — a frontend served from any other port gets
CORS-blocked until this is set), `PUBLIC_SHARE_RATE_LIMIT_MAX` /
`_WINDOW_SECONDS` (30 per 60s), and the three `NVIDIA_NIM_*` chat vars.
Read settings via the module-level `settings` singleton; don't re-read
`os.environ`.

Every model mixes in `AuditMixin` (`app/models/mixins.py`): `created_at` /
`updated_at` / `deleted_at` / `deleted_by` / `is_active`. **Soft delete
only** — rows are flagged, never physically removed; read queries must
filter on `is_active` / `deleted_at`.

Auth issues a rotating refresh-token pair (`POST /auth/login` returns both an
access and a refresh token; `POST /auth/refresh` revokes the presented
refresh token and issues a fresh pair — single-use rotation, not a
long-lived reusable token). Only a sha256 hash of the refresh token is
stored (`RefreshToken.token_hash`); `FloorPlanShare`, by contrast, stores its
token in the clear since that one is a link meant to be shared, not a bearer
secret.

### Floor-plan generation pipeline (`services/floorplan_generator.py`)

Every dimension in the output is derived from the input; there is no fixed
template. Changing plot size, room counts, floor count, parking, or Vastu
preference changes the plan.

1. **Buildable rectangle**: plot length/width/facing minus mandatory
   setbacks (`compute_buildable_rect`, rules in `utils/constants.py`).
2. **Room program**: flat list of `RoomInstance`s built from
   bedroom/bathroom counts + optional/additional rooms, split across floors
   by `_build_duplex_room_program` or `_build_independent_room_program`
   depending on `floor_type` (see below). `additional_rooms` is a validated
   allowlist in `schemas/requirement.py` (`home_office`, `servant_room`,
   `store_room`, `guest_room`, `gym`, `library`) — adding a new one means
   updating that validator *and* `ROOM_LIBRARY` in `utils/constants.py`.
3. **Vastu zone assignment**: each room greedily assigned to a preferred
   compass zone (N/NE/E/SE/S/SW/W/NW/C) in a 3x3 grid, load-balanced; a
   functional fallback order (`FALLBACK_ZONE_ORDER`) is used if Vastu is
   off. The room housing the entrance (veranda/foyer) is pinned to
   whichever compass edge the plot's `facing` puts on the street
   (`FRONT_ZONES_BY_FACING`), regardless of Vastu.
4. **Grid slicing**: the buildable rect becomes a weighted 3x3 grid, sized
   proportional to each cell's total room weight, but every room's
   `min_w`/`min_l` is guaranteed first whenever the floor has enough total
   area for the whole program — leftover space is then handed out by
   weight. Rows with 3 occupied Vastu cells internally split into two
   stacked sub-rows and get their minimum depth sized for *both* sub-rows
   up front (this and biasing zone assignment away from unnecessary
   3-cell rows are what prevent sliver/undersized rooms). Rooms that still
   can't fit their minimum are flagged `below_min_size` in the output
   rather than silently shrunk further. Within a row/column, shares are not
   pure weight share but a squarified blend (`_squarified_shares`) biased
   toward each room's target aspect ratio — a lightly-weighted room forced
   to span the full width of its siblings would otherwise get a sliver of
   height to go with it. This trades exact weight-proportional area for
   saner shapes; the `min` floor still applies on top, so total area used
   and minimum-size guarantees are unaffected.
5. **Parking**: carved from the ground-floor front setback, extending into
   the footprint if vehicles don't fit within the setback alone.
6. **Staircase and veranda strips**: both are carved with
   `geo.split_strip` *before* grid slicing, not placed as Vastu grid cells.
   The staircase is a fixed-width strip at a consistent west/east edge
   (multi-floor only) so it stacks identically across floors, enclosed
   inside the house footprint rather than tacked onto the exterior; on the
   ground floor it is intersected with the parking-receded outline so it
   stays inside that floor's walls. The veranda is a full-width strip off
   the front edge, so it always spans the facade and sits between the
   entrance and every other room instead of landing as a corner sliver.
7. **Walls, doors, windows, furniture** derived from final room rects:
   exterior outline + shared interior walls, an entrance door plus one
   internal door per room on its largest shared wall, windows on
   exterior-facing habitable rooms, simple wall-anchored furniture. Doors
   are built as a Kruskal's-style spanning **tree** over every pair of rooms
   sharing a wall wide enough for a doorway (widest wall first) — a tree,
   not a general graph, so every room has exactly the doors it needs and no
   redundant ones; this matters when editing geometry later (see below).
8. **Site elements (ground floor only)**: these work in **plot**
   coordinates, outside the building footprint. `compute_main_gate` opens a
   driveway gate in the front boundary centered on the parking (falling
   back to the entrance door, then the plot center); `compute_ramp` runs a
   ramp outward from the entrance door *only* when `wheelchair_accessible`
   is set, retrying a few sideways shifts to clear the parking rect and
   returning `None` if it can't fit inside the plot. Neither is a room —
   they live at `floor.main_gate` / `floor.ramp`, with
   `meta.compound_wall_style` and `meta.gate_style` telling the frontend how
   to draw the boundary (`siteIcons.ts` holds those glyphs, separate from
   `furnitureIcons.ts`).

Note the signature: `generate_floor_plan(req)` is annotated `-> dict` but
actually returns the tuple `(plan_data, total_built_up_area)`.

**`floor_type` (`duplex` | `independent`)** changes the room program, not
just the styling. `duplex` = one household across floors: shared
living/kitchen downstairs, and only the ground floor gets a front door
(upper floors are reached by the internal staircase). `independent` =
every floor is its own self-contained unit off a shared staircase landing,
so each floor gets its own living room, kitchen *and* its own
`main_entrance` door. `is_independent_floors(req)` is the predicate — check
it rather than reading `floor_type` directly, because it is also False for
a single-floor plan regardless of the field's value.

`wheelchair_accessible` likewise reaches further than the ramp: it also
swaps the first ground-floor bathroom's type to `accessible_bathroom` in
the room program, so it changes room sizing too.

Known simplification: every floor otherwise shares the same footprint (no
upper-floor step-backs).

### `plan_data` shape

The single JSON contract between the generator, every plan-editing
endpoint, the SVG viewer, the 3D view, and undo/redo. Everything is in **feet**, in
plot coordinates: `x` runs 0 (West) → `plot_width` (East), `y` runs
0 (North) → `plot_length` (South), so `y` grows *southward*.

```
{ "meta": { plot_length, plot_width, unit, facing, floors, vastu_compliant,
            compound_wall_style, gate_style, total_built_up_area,
            buildable_footprint: {x,y,width,length},
            # attached by the API layer, NOT by generate_floor_plan:
            cost_estimate, boq, construction_timeline, far },
  "floors": [ { floor_number, label, has_staircase,
                outline: {x,y,width,length},
                rooms:   [ {id, type, label, zone, x, y, width, length, area,
                            below_min_size, furniture:[{type,x,y,w,l,rotation}]} ],
                walls, doors, windows,
                parking:   {x,y,width,length,capacity_cars,capacity_two_wheelers} | null,
                ramp:      {x,y,width,length,side} | null,
                main_gate: {x,y,width,side} | null } ] }
```

Shape traps worth knowing before you index into it:

- **Rooms use `width`/`length`; every rect the generator passes around
  internally uses `w`/`l`.** The rename happens at the serialization
  boundary in `generate_floor_plan`, and `recompute_floor_geometry` maps
  back the other way. Mixing the two silently produces `None`/`KeyError`.
- **Doors are not uniform.** `{"type": "main_entrance", ...}` carries a
  `wall` key; `{"type": "internal", ...}` carries `connects_to` instead and
  has **no** `wall`. Code that reads `door["wall"]` unconditionally breaks
  on internal doors.
- **Furniture `w`/`l` is the *post-rotation* bounding box**, with
  `rotation` stored separately — both the 2D icon renderer and
  `FloorPlan3DView` must un-swap (`rotation % 180 !== 0`) to get the
  natural pose. The generator always emits `rotation: 0`; non-zero values
  only ever come from the frontend furniture editor.
- All coordinates are **rounded to 2 decimals** on the way out. That
  rounding is exactly why re-derived geometry needs a loosened tolerance —
  see `.claude/rules/room-geometry.md`.
- `cost_estimate`/`boq`/`construction_timeline`/`far` are *derived* and
  live only in the API layer: the generate route in
  `api/v1/requirements.py` attaches them on first build, and
  `_recalculate_estimates` in `api/v1/floorplans.py` re-derives them after
  every geometry edit. `generate_floor_plan` itself never sets them, so a
  plan built by calling the service directly (a smoke script, a test) has
  no `meta.cost_estimate` at all.

### Manual editing after generation

`plan_data` is a plain SQLAlchemy `JSON` column with no mutation tracking,
so **mutating it in place does not mark the row dirty**. All seven routes
in `api/v1/floorplans.py` that write it (furniture, rooms, plan-data
restore, attached-bathroom add/remove, replace, parking) call
`flag_modified(plan, "plan_data")` before `db.commit()`; omit it and the
response still shows the edit — it's served from the live in-session
object — while the database silently keeps the old plan, so the bug only
surfaces on the next request.

Four endpoints mutate an existing `FloorPlan.plan_data` in place rather
than regenerating from scratch, all funneling through the same two
functions: `recompute_floor_geometry(floor, facing)` (rebuilds
windows/doors/walls for one floor from its rooms' *current* x/y/width/length)
and `rooms_are_connected(room_ids, doors)` (union-find check over the
rebuilt door graph) — reusing exactly the derivation the initial generation
pipeline uses so a hand-edited layout keeps the same guarantees:

- `PUT .../rooms` — drag-move/resize a room (frontend room-layout editor).
  **Clears that room's `furniture`** whenever its rect actually moved/
  resized (stale absolute-coordinate placements would otherwise land
  outside the new bounds) — see Undo/Redo below for how the frontend lets
  a user recover from that.
- `PUT .../parking` — drag-resize the parking rect.
- `POST` / `DELETE .../rooms/{room_id}/attached-bathroom` — carve a bathroom
  out of an eligible room (or remove one), via `add_attached_bathroom` /
  `remove_attached_bathroom`, scoring and trial-validating candidate edges
  before committing.
- `PUT .../rooms/{room_id}/replace` — convert a room to a different
  `ROOM_LIBRARY` type in place (e.g. Bathroom → Kitchen) via `replace_room`,
  **reusing its existing rect exactly as-is** (not a resize — geometry is
  untouched, only type/label/furniture and the derived windows/doors/walls
  change). Rejects structural/entrance-role types
  (`ROOM_REPLACE_INELIGIBLE_TYPES` = staircase/veranda/foyer) as either
  source or target, and rejects if the room is below the new type's
  minimum width/length/area. Warns (without blocking) on missing
  ventilation, missing plumbing/drainage access for a `WET_ROOM_TYPES`
  room, or a Vastu-zone mismatch.

Two invariants this pattern exists to protect — a rect can only be split
along a *full* edge (never a corner notch, which would need unsupported
polygon rooms), and anything rebuilding doors/walls from already-rounded
stored rects needs a larger touch-tolerance than the initial generation
pass or it can silently disconnect rooms — are written up in full in
**`.claude/rules/room-geometry.md`**; read that before touching this code.
The **`add-geometry-endpoint`** skill has the step-by-step pattern (trial-
copy-then-commit, candidate scoring, required test coverage) for adding
another endpoint like these.

**Undo/Redo**: since geometry-mutating edits can destructively clear
furniture (see `PUT .../rooms` above), there's a general-purpose
`PUT .../floorplans/{id}/plan-data` (schema: `PlanDataRestore`) that
overwrites `plan_data` wholesale with a previously-returned snapshot,
re-running `_recalculate_estimates` but skipping geometry validation
(the snapshot was already a server-committed state). The frontend
(`ProjectDetailPage.tsx`) keeps a client-side stack of `plan_data`
snapshots — every edit path already funnels through one `applyPlanUpdate`
callback, so this one endpoint serves undo/redo for furniture edits, room/
parking resize, attached-bathroom, and room-replace uniformly, with no
per-edit-type inverse logic needed.

### Key API routes (`app/api/v1/`, prefixed `/api/v1`)

- `auth`: `/auth/register`, `/auth/login` (OAuth2 form), `/auth/refresh`
  (rotates the refresh token), `/auth/logout`, `/auth/me`
- `projects`: CRUD at `/projects`, `/projects/{id}`
- `requirements`: `POST /projects/{id}/requirements` (validates via
  `services/validation.py`), `GET .../latest`,
  `POST /projects/{id}/requirements/{req_id}/generate` — runs the
  generator + cost/BOQ/timeline/FAR estimation, persists a new `FloorPlan`
  version
- `floorplans`: `/projects/{id}/floorplans`, `.../latest`,
  `GET/PATCH/DELETE .../{floor_plan_id}`,
  `PUT .../{floor_plan_id}/furniture` (furniture-editor updates),
  `PUT .../{floor_plan_id}/rooms` / `.../parking` (manual layout edits),
  `POST/DELETE .../{floor_plan_id}/rooms/{room_id}/attached-bathroom`,
  `PUT .../{floor_plan_id}/rooms/{room_id}/replace` (convert a room to a
  different type in place, geometry unchanged),
  `PUT .../{floor_plan_id}/plan-data` (undo/redo: restore a whole
  `plan_data` snapshot),
  `POST/GET/DELETE .../{floor_plan_id}/share` (create/fetch/revoke a
  public share token, backed by `FloorPlanShare`)
- `public`: `GET /public/floorplans/{token}` — unauthenticated read of a
  shared plan
- `chat`: `POST /chat` — house Q&A chat assistant; auth required, optional
  `project_id` grounds the answer with that project's latest
  requirement/floor-plan summary (the frontend's `ChatWidget` currently
  never sends this — chat answers are never actually project-grounded in
  practice today, only via direct API calls)

Regenerating a requirement bumps `FloorPlan.version` rather than mutating
the existing row — plan history per project is preserved.

### Chat assistant (`services/chat_assistant.py`, `POST /api/v1/chat`)

The only place this app calls an external AI API. Proxies to an NVIDIA
NIM-hosted LLM (OpenAI-compatible `/chat/completions`) via `httpx`, with a
system prompt scoping it to house-building topics. Config is entirely
env-driven (`NVIDIA_NIM_API_KEY`/`_BASE_URL`/`_MODEL` in `core/config.py`) —
an unset API key makes the endpoint return `503` rather than failing at
startup, so the rest of the app works with zero chat configuration.
`ChatNotConfiguredError` (→ 503) vs `ChatAssistantError` (→ 502, any other
upstream failure) are distinguished so the frontend can tell "feature off"
from "request failed."

## Frontend architecture

```
src/
  api/client.ts   thin fetch wrapper (api.* namespace); JWT stored in
                  localStorage under "ahl_token", refresh token under
                  "ahl_refresh_token"; a 401 triggers one deduped silent
                  refresh-and-retry before surfacing; ApiError normalizes
                  FastAPI/Pydantic error shapes into a message string
  api/types.ts    TypeScript mirrors of backend schemas
  context/AuthContext.tsx   auth state, wraps the whole app
  components/
    Layout.tsx, ProtectedRoute.tsx     routing shell / auth gate
    FloorPlanViewer.tsx   the big one (~2000 lines) — renders plan_data as
                          SVG, drag-to-edit furniture and room layout (4
                          corner resize handles + drag-a-shared-wall to
                          resize two rooms at once), attached-bathroom
                          add/remove and room-replace controls in the room
                          schedule, PNG export (canvas.toBlob) and PDF
                          export via a hand-rolled minimal PDF builder
                          (buildMinimalPdf, no pdf/canvas libraries in
                          package.json). The toolbar above the drawing is a
                          two-row flex-wrap layout (view toggle/undo-redo/
                          show-furniture on one row, downloads/edit actions
                          on another) specifically so controls wrap onto a
                          new line instead of silently overflowing
                          off-panel as more buttons get added — keep new
                          toolbar buttons inside `.toolbar-row`, not back in
                          one unwrapped row.
    FloorPlan3DView.tsx   Three.js (OrbitControls) 3D walkthrough of the
                          same plan_data — rebuilds rooms/furniture/roof/
                          parked-vehicle meshes procedurally from the plan
                          JSON, no separate 3D data model. Furniture items
                          store `w`/`l` as their *post-rotation* bounding
                          box (rotation is a separate field) — building a
                          correctly-oriented mesh requires un-swapping back
                          to the natural pose first (`rotation % 180 !== 0`
                          means swapped), mirroring the exact transform the
                          2D SVG icon renderer already uses. Per-floor
                          isolation (view one floor at a time vs. the whole
                          stack) via a floor-select control; car/bike meshes
                          are built from real-world-scaled primitives
                          (`buildCarMesh`/`buildBikeMesh`), not fixed-size
                          placeholders, colored `#3B82F6` / `#F59E0B`.
    furnitureIcons.ts, siteIcons.ts    icon/glyph lookups keyed by type
    ChatWidget.tsx   floating "Ask about your house" chat panel, mounted in
                     Layout.tsx for any logged-in user; calls POST /chat
  pages/
    LoginPage, RegisterPage, ProjectsPage, ProjectDetailPage (requirement
    form + generate + plan history + version compare), SharedFloorPlanPage
    (public, unauthenticated view via /share/:token)
```

**Gotcha**: `FloorPlanViewer.tsx` renders the plan two different ways that
must not be confused when reading or testing it. A static SVG string built
by `buildFloorSvg` and injected via `dangerouslySetInnerHTML` (produces
`.room-outline`, `.room-label`, etc., driven by `floor.rooms` from props —
**never updates during a live drag**), versus an interactive JSX overlay
rendered only in room-layout-edit mode (produces `.room-edit-rect`,
`.room-edit-handle`, etc., driven by live `localRooms` state — **does**
update live during drags). Checking `.room-outline` to see whether a drag
"worked" will always show no change regardless of the actual result.

Routing (`App.tsx`): `/login`, `/register` are public;
`/share/:token` renders inside the shared `Layout` but without
`ProtectedRoute`; `/projects` and `/projects/:projectId` require auth.
Everything else redirects to `/projects`.

The frontend has no state management library — data flows through
`api/client.ts` calls made directly in page components plus
`AuthContext`. There's no CSS framework either; each page/component pairs
with its own hand-written `*.css` file.
