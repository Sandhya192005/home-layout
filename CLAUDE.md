# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

Takes a customer's home-building requirements (plot size, family size, room
program, parking, floors, budget, Vastu preference) and procedurally
generates a customized 2D floor plan (rooms, walls, doors, windows,
furniture, parking, staircase) — sized and positioned specifically for that
input, not a fixed template. Floor-plan generation itself is pure geometry
(no LLM/external AI API involved), and the "AI suggestions" feature is a
deterministic rule-based engine (isolated so it could later be swapped for
a real LLM call). The one place an external AI API *is* used is the house
Q&A chat assistant (`services/chat_assistant.py`, `POST /api/v1/chat`),
which calls an NVIDIA NIM-hosted LLM (OpenAI-compatible chat completions) —
see below.

Two independent apps in one repo: `backend/` (FastAPI + PostgreSQL) and
`frontend/` (React 19 + Vite + TypeScript), talking over a REST API.

Note: `PROJECT_STATUS.md` says the frontend is "not built yet" — that is
stale. The frontend under `frontend/src/` is fully implemented (auth,
project/requirement flow, SVG floor-plan viewer, furniture editor, PNG/PDF
export, shareable public links).

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

## Backend architecture

```
app/
  core/       config (env-driven Settings), DB session, JWT/password security,
              rate_limit.py (in-process per-IP limiter, applied to the public
              share endpoint)
  models/     SQLAlchemy ORM (User, Project, Requirement, FloorPlan, FloorPlanShare)
  schemas/    Pydantic request/response models
  crud/       DB access functions
  api/v1/     FastAPI routers (auth, projects, requirements, floorplans, public)
  services/
    floorplan_generator.py  the dynamic layout engine (see below) — 900 lines, the core of the project
    geometry.py               rectangle/wall/door math helpers
    validation.py              requirement sanity checks
    cost_estimator.py          budget/tier estimation
    ai_suggestions.py          rule-based (non-LLM) design suggestions
    chat_assistant.py          house Q&A chat -- the one LLM/external-API call in the app (NVIDIA NIM)
  utils/constants.py    room library (sizes, Vastu zones, furniture), setback rules — swap these for a real locality's code
alembic/versions/   hand-written migrations (no autogenerate configured — write revisions manually)
```

Every model mixes in `AuditMixin` (`app/models/mixins.py`): `created_at` /
`updated_at` / `deleted_at` / `deleted_by` / `is_active`. **Soft delete
only** — rows are flagged, never physically removed; read queries must
filter on `is_active` / `deleted_at`.

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
   exterior-facing habitable rooms, simple wall-anchored furniture.

Known simplification: every floor shares the same footprint (no
upper-floor step-backs), except the "independent-floor duplex mode" noted
in recent commits which allows floors to diverge.

### Key API routes (`app/api/v1/`, prefixed `/api/v1`)

- `auth`: `/auth/register`, `/auth/login` (OAuth2 form), `/auth/me`
- `projects`: CRUD at `/projects`, `/projects/{id}`
- `requirements`: `POST /projects/{id}/requirements` (validates via
  `services/validation.py`), `GET .../latest`,
  `POST /projects/{id}/requirements/{req_id}/generate` — runs the
  generator + `ai_suggestions.py`, persists a new `FloorPlan` version
- `floorplans`: `/projects/{id}/floorplans`, `.../latest`,
  `GET/PATCH/DELETE .../{floor_plan_id}`,
  `PUT .../{floor_plan_id}/furniture` (furniture-editor updates),
  `POST/GET/DELETE .../{floor_plan_id}/share` (create/fetch/revoke a
  public share token, backed by `FloorPlanShare`)
- `public`: `GET /public/floorplans/{token}` — unauthenticated read of a
  shared plan
- `chat`: `POST /chat` — house Q&A chat assistant; auth required, optional
  `project_id` grounds the answer with that project's latest
  requirement/floor-plan summary. See below.

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
from "request failed." When `project_id` is passed, the caller's latest
`Requirement`/`FloorPlan` are summarized into the system prompt so
project-specific questions ("why is my kitchen small?") work too.

## Frontend architecture

```
src/
  api/client.ts   thin fetch wrapper (api.* namespace); JWT stored in
                  localStorage under "ahl_token"; ApiError normalizes
                  FastAPI/Pydantic error shapes into a message string
  api/types.ts    TypeScript mirrors of backend schemas
  context/AuthContext.tsx   auth state, wraps the whole app
  components/
    Layout.tsx, ProtectedRoute.tsx     routing shell / auth gate
    FloorPlanViewer.tsx   the big one (~1000 lines) — renders the plan_data
                          JSON as SVG, drag-to-edit furniture, PNG export
                          (canvas.toBlob) and PDF export via a hand-rolled
                          minimal PDF builder (buildMinimalPdf) — no
                          pdf/canvas libraries are in package.json
    furnitureIcons.ts, siteIcons.ts    icon/glyph lookups keyed by type
    ChatWidget.tsx   floating "Ask about your house" chat panel, mounted in
                     Layout.tsx for any logged-in user; calls POST /chat
  pages/
    LoginPage, RegisterPage, ProjectsPage, ProjectDetailPage (requirement
    form + generate + plan history), SharedFloorPlanPage (public,
    unauthenticated view via /share/:token)
```

Routing (`App.tsx`): `/login`, `/register` are public;
`/share/:token` renders inside the shared `Layout` but without
`ProtectedRoute`; `/projects` and `/projects/:projectId` require auth.
Everything else redirects to `/projects`.

The frontend has no state management library — data flows through
`api/client.ts` calls made directly in page components plus
`AuthContext`. There's no CSS framework either; each page/component pairs
with its own hand-written `*.css` file.
