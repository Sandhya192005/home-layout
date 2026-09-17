# AI Home Layout — Backend

FastAPI service that turns customer requirements (plot size, facing, room
program, parking, floors, budget, Vastu preference) into a dynamically
generated, structured floor plan, then estimates its cost and lets it be
edited by hand afterwards.

See the [root README](../README.md) for the project overview and
`../ARCHITECTURE.md` for diagrams of the request flow.

## Stack

- Python 3.11+, FastAPI, Uvicorn
- PostgreSQL + SQLAlchemy 2.0 + Alembic
- JWT auth (python-jose) with bcrypt password hashing
- httpx, for the one outbound AI call (the chat assistant)

## Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
cp .env.example .env          # then edit DATABASE_URL / SECRET_KEY
```

Create the database (Postgres must be running):

```bash
createdb ai_home_layout
```

Run migrations, then the API:

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

Docs at `http://localhost:8000/docs`, health check at `/health`.

### Configuration

Everything is env-driven through a single `Settings` class in
`app/core/config.py`, and every field has a working default — the app boots
with no `.env` at all. Beyond `DATABASE_URL` and `SECRET_KEY`:

| Variable | Default | Notes |
| --- | --- | --- |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | |
| `BACKEND_CORS_ORIGINS` | `:3000`, `:5173` | a frontend on any other port is CORS-blocked until added |
| `PUBLIC_SHARE_RATE_LIMIT_MAX` | `30` | requests per window on the public share endpoint |
| `PUBLIC_SHARE_RATE_LIMIT_WINDOW_SECONDS` | `60` | |
| `NVIDIA_NIM_API_KEY` | *(empty)* | blank disables the chat assistant |
| `NVIDIA_NIM_BASE_URL` | `https://integrate.api.nvidia.com/v1` | any OpenAI-compatible endpoint |
| `NVIDIA_NIM_MODEL` | `meta/llama-3.1-8b-instruct` | |

Read settings through the module-level `settings` singleton rather than
`os.environ`.

### Migrations

There is no autogenerate setup — revisions are written by hand:

```bash
alembic revision -m "description"    # then edit the new file under alembic/versions/
```

## Architecture

```
app/
  core/       config (env-driven Settings), DB session, JWT/password
              security, rate_limit.py (in-process per-IP limiter used on
              the public share endpoint)
  models/     SQLAlchemy ORM: User, Project, Requirement, FloorPlan,
              FloorPlanShare, RefreshToken
  schemas/    Pydantic request/response models
  crud/       DB access functions
  api/v1/     routers: auth, projects, requirements, floorplans, public, chat
  services/
    floorplan_generator.py  the layout engine — the core of the project
    geometry.py             rectangle/wall/door math helpers
    validation.py           requirement sanity checks (errors + warnings)
    cost_estimator.py       cost tiers, BOQ, construction timeline, FAR
    chat_assistant.py       house Q&A chat — the one external API call
  utils/constants.py        room library (sizes, Vastu zones, furniture),
                            setback rules, cost/BOQ rates
alembic/versions/           hand-written migrations
tests/                      pytest suite (isolated in-memory SQLite)
scripts/                    standalone smoke tests
```

### Data model notes

Every model mixes in `AuditMixin` (`created_at`, `updated_at`, `deleted_at`,
`deleted_by`, `is_active`). **Deletes are soft** — rows are flagged, never
physically removed, so read queries filter on `is_active` / `deleted_at`.

Regenerating a requirement creates a new `FloorPlan` row with a bumped
`version` rather than mutating the existing one, so plan history per project
is preserved and versions can be compared.

### Auth

`POST /auth/login` returns an access token *and* a refresh token.
`POST /auth/refresh` revokes the presented refresh token and issues a fresh
pair — single-use rotation, not a long-lived reusable token. Only a sha256
hash of the refresh token is stored. `FloorPlanShare` tokens, by contrast,
are stored in the clear: those are links meant to be shared, not bearer
secrets.

## How generation works

Every dimension in the output is derived from the input — there is no fixed
template. Changing plot size, room counts, floor count, parking or Vastu
preference changes the plan.

1. **Setbacks** are computed from plot length, width and facing to get a
   buildable rectangle.
2. A **room program** is built from bedroom/bathroom counts, optional rooms
   and additional rooms, split across floors. `floor_type` decides how:
   `duplex` spreads one household across floors (only the ground floor gets
   a front door), while `independent` makes each floor a self-contained unit
   off a shared staircase landing, each with its own kitchen, living room
   and entrance. Use the `is_independent_floors(req)` predicate rather than
   reading the field — it is also False for single-floor plans.
3. **Vastu zone assignment**: each room is greedily assigned to its
   preferred compass zone (N/NE/E/SE/S/SW/W/NW/C) on a 3×3 grid, balanced by
   load; with Vastu disabled a functional fallback order is used instead.
   The room holding the entrance is pinned to whichever edge the plot's
   facing puts on the street, regardless of Vastu.
4. The buildable rectangle is sliced into a **weighted, minimum-size-aware
   grid**: rows and columns are sized proportional to the room weight
   assigned to them, but every room's `min_w`/`min_l` is guaranteed first
   whenever the floor has enough total space for the whole program —
   leftover space is then handed out by weight, biased toward each room's
   target aspect ratio so a lightly-weighted room doesn't become a sliver.
   Rows that end up with 3 occupied Vastu cells (which internally split into
   two stacked sub-rows) get their minimum depth sized for *both* sub-rows
   up front, and zone assignment is itself biased against tripling up a row
   unless Vastu requires that exact cell.
5. **Parking** is carved from the ground-floor front setback, extending into
   the footprint if the vehicles don't fit within the setback alone.
6. **Staircase and veranda strips** are cut with `geo.split_strip` *before*
   slicing: the staircase at a consistent west/east edge so it stacks
   identically on every floor (enclosed inside the footprint, not tacked
   onto the exterior), the veranda as a full-width strip off the front edge
   so it spans the facade.
7. **Walls** (exterior outline + shared interior edges), **doors**,
   **windows** (exterior-facing habitable rooms) and simple wall-anchored
   **furniture** are derived from the final room rectangles. Doors are built
   as a Kruskal-style spanning **tree** over every pair of rooms sharing a
   wall wide enough for a doorway — a tree, not a general graph, so every
   room is reachable with no redundant doors.
8. **Site elements** on the ground floor, in plot coordinates: a compound
   gate centered on the parking, and a wheelchair ramp from the entrance
   door when `wheelchair_accessible` is set.

Cost, BOQ, construction timeline and FAR are then estimated from the
resulting built-up area.

Note the signature: `generate_floor_plan(req)` is annotated `-> dict` but
actually returns `(plan_data, total_built_up_area)`.

## Manual editing after generation

Several endpoints mutate an existing `FloorPlan.plan_data` in place instead
of regenerating. They all funnel through the same two functions —
`recompute_floor_geometry(floor, facing)`, which rebuilds
windows/doors/walls for one floor from its rooms' *current* rectangles, and
`rooms_are_connected(room_ids, doors)`, a union-find check over the rebuilt
door graph — reusing exactly the derivation the generator uses, so a
hand-edited layout keeps the same guarantees as a fresh one.

- `PUT .../rooms` — drag-move/resize a room. Clears that room's furniture
  when its rectangle actually changed, since stale absolute positions would
  land outside the new bounds.
- `PUT .../parking` — drag-resize the parking rectangle.
- `POST`/`DELETE .../rooms/{room_id}/attached-bathroom` — carve a bathroom
  out of an eligible room, or remove one.
- `PUT .../rooms/{room_id}/replace` — convert a room to a different
  `ROOM_LIBRARY` type in place, reusing its rectangle exactly. Rejects
  structural/entrance types and rooms below the new type's minimum size;
  warns without blocking on missing ventilation, missing plumbing access for
  a wet room, or a Vastu mismatch.
- `PUT .../plan-data` — restore a whole previously-returned `plan_data`
  snapshot. This is what powers the frontend's undo/redo for every edit type
  uniformly, with no per-edit inverse logic.

Two invariants make this work, and they are written up in full in
`../.claude/rules/room-geometry.md`:

1. **Rooms are axis-aligned rectangles.** A rectangle can only be split by
   cutting a full-width or full-length strip off one edge — a corner notch
   would leave an L-shape, which the model cannot represent.
2. **Re-derived geometry needs a looser touch tolerance.** Rectangles read
   back from stored `plan_data` are already rounded to 2 decimals, so two
   rooms meant to touch can differ by a ~0.01ft sliver. At the strict
   tolerance used during initial generation, that sliver reads as a gap and
   silently drops a doorway — and since doors form a spanning tree, losing
   one edge can disconnect a whole branch of rooms.

Also note that `plan_data` is a plain `JSON` column with no mutation
tracking: every route that edits it must call
`flag_modified(plan, "plan_data")` before `db.commit()`, or the response
will show the edit (served from the live session object) while the database
keeps the old plan.

## API

All routes are prefixed with `/api/v1`. Full interactive reference at
`/docs`.

**Auth**
- `POST /auth/register`, `POST /auth/login` (OAuth2 form)
- `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me`

**Projects and requirements**
- `GET/POST /projects`, `GET/PUT/DELETE /projects/{id}`
- `POST /projects/{id}/requirements` — submit + validate
- `GET /projects/{id}/requirements`, `GET .../latest`
- `POST /projects/{id}/requirements/{req_id}/generate` — generate and
  persist a new floor-plan version with cost/BOQ/timeline/FAR

**Floor plans** (under `/projects/{id}/floorplans`)
- `GET /`, `GET /latest`, `GET/PATCH/DELETE /{plan_id}`
- `PUT /{plan_id}/furniture` — furniture-editor updates
- `PUT /{plan_id}/rooms`, `PUT /{plan_id}/parking` — manual layout edits
- `POST/DELETE /{plan_id}/rooms/{room_id}/attached-bathroom`
- `PUT /{plan_id}/rooms/{room_id}/replace`
- `PUT /{plan_id}/plan-data` — restore a snapshot (undo/redo)
- `POST/GET/DELETE /{plan_id}/share` — create/fetch/revoke a share token

**Public and chat**
- `GET /public/floorplans/{token}` — unauthenticated read of a shared plan,
  rate-limited per IP
- `POST /chat` — house Q&A assistant; auth required. An optional
  `project_id` grounds the answer in that project's latest requirement and
  plan summary. Returns `503` when no API key is configured and `502` on any
  other upstream failure, so a client can tell "feature off" from "request
  failed".

## Testing

```bash
cd backend
.venv\Scripts\python.exe -m pytest                                # full suite
.venv\Scripts\python.exe -m pytest tests/test_generation.py -q     # one file
.venv\Scripts\python.exe -m pytest -k test_replace_room_rejects    # one test
```

Every test gets its own in-memory SQLite database wired in through a
dependency override, so the suite never touches the Postgres instance in
`DATABASE_URL` and is safe to run freely. `conftest.py` provides a fixture
ladder — `client` → `auth_headers` → `project` → `requirement` →
`floor_plan` — so a test can depend on the highest rung it needs.

Anything touching `services/floorplan_generator.py` or `services/geometry.py`
is shared by every layout and editing feature: run the **full** suite
afterwards, not just the file for the feature you changed.

Two standalone smoke scripts cover the same ground end to end without
pytest, against no live database:

```bash
python scripts/smoke_test_generator.py   # the layout engine across 4 scenarios
python scripts/smoke_test_api.py         # full HTTP flow incl. cross-user 403 checks
```

There is no linter, formatter or type checker configured, and no CI —
running pytest locally is the only gate.

## Notes and simplifications

- Setback rules, cost tiers (INR) and BOQ ratios in `app/utils/constants.py`
  are illustrative defaults, not a specific municipal code. Swap them for
  your locality before relying on the numbers.
- Rooms are axis-aligned rectangles only — no L-shaped or polygonal rooms.
- Every floor shares the same footprint; no upper-floor step-backs.
- The room grid is a weighted-partition heuristic, not a constraint solver.
  It guarantees each room's minimum size whenever the floor's buildable area
  is large enough for the whole program, but on genuinely tight plots — a
  ~22ft frontage carrying three floors of bedrooms, say — there isn't the
  physical space to honor every minimum. Those rooms are flagged per-room
  via `below_min_size` in the plan JSON rather than silently shrunk.
- Cost, BOQ and timeline figures are indicative, not a substitute for a
  quantity surveyor or structural engineer.
