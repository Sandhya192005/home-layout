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
```

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
   bedroom/bathroom counts + optional/additional rooms, split across floors.
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
   rather than silently shrunk further.
5. **Parking**: carved from the ground-floor front setback, extending into
   the footprint if vehicles don't fit within the setback alone.
6. **Staircase**: a fixed-width strip reserved at a consistent west/east
   edge (multi-floor only) so it stacks identically across floors — in
   duplex/multi-floor mode the staircase is enclosed inside the house
   footprint, not tacked onto the exterior.
7. **Walls, doors, windows, furniture** derived from final room rects:
   exterior outline + shared interior walls, an entrance door plus one
   internal door per room on its largest shared wall, windows on
   exterior-facing habitable rooms, simple wall-anchored furniture. Doors
   are built as a Kruskal's-style spanning **tree** over every pair of rooms
   sharing a wall wide enough for a doorway (widest wall first) — a tree,
   not a general graph, so every room has exactly the doors it needs and no
   redundant ones; this matters when editing geometry later (see below).

Known simplification: every floor shares the same footprint (no
upper-floor step-backs), except the "independent-floor duplex mode" noted
in recent commits which allows floors to diverge.

### Manual editing after generation

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
