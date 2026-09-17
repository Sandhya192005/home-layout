# AI Home Layout

Turn a customer's home-building requirements into a fully dimensioned,
customized floor plan — in 2D and 3D, with a cost estimate, a bill of
quantities, and an editor to adjust the result by hand.

Give it a plot size, a facing direction, a family size, a room program, a
parking need, a floor count, a budget and a Vastu preference. It returns a
complete plan: rooms, walls, doors, windows, furniture, parking, staircase,
compound gate and — if requested — a wheelchair ramp, every dimension
derived from that specific input.

**There is no template.** Change the plot width or add a car and the
partitioning, the room sizes, the door graph and the cost all change with
it. Generation is pure geometry and rules — no LLM is involved anywhere in
the layout, cost or editing paths. (The one external AI call in the project
is the optional house Q&A chat assistant, and the app runs fine with it
switched off.)

<!-- Screenshots go here — e.g. docs/screenshot-2d.png and docs/screenshot-3d.png -->

---

## Features

**Generation**
- Setback-aware buildable rectangle from plot size + facing
- Vastu compass-zone assignment on a 3×3 grid, with a functional fallback
  when Vastu is off
- Minimum-size-aware weighted partitioning — rooms that genuinely cannot
  fit are flagged `below_min_size` rather than silently shrunk
- Parking carved from the front setback, staircase stacked identically
  across floors, veranda spanning the facade
- Doors built as a spanning tree over shared walls, so every room is
  reachable and no room gets a redundant door
- `duplex` (one household across floors) or `independent` (each floor its
  own self-contained unit) multi-floor modes
- Optional wheelchair accessibility: entrance ramp plus an accessible
  bathroom in the room program

**Viewing and editing**
- SVG 2D viewer with a room schedule
- Three.js 3D walkthrough built procedurally from the same plan data, with
  per-floor isolation and real-world-scaled car/bike meshes
- Manual layout editor: drag-move/resize a room, drag a shared wall to
  resize two rooms at once, resize parking
- Attach or remove a bathroom on an eligible room
- Replace a room with a different type in place, geometry untouched
- Furniture editor, with undo/redo across every edit type
- PNG and PDF export (hand-rolled, no PDF or canvas dependencies)

**Project management**
- JWT auth with single-use rotating refresh tokens
- Versioned plan history per project, plus version compare — regenerating
  bumps a version instead of overwriting
- Shareable public read-only links (tokened, rate-limited)
- Cost estimate across four quality tiers, rule-of-thumb BOQ, phased
  construction timeline, and a FAR/FSI limit check
- Soft-delete audit trail on every record

**Optional**
- "Ask about your house" chat assistant, backed by an NVIDIA NIM-hosted
  LLM. Leave the API key unset and the endpoint returns `503` — the rest of
  the app is unaffected.

---

## Tech stack

| | |
| --- | --- |
| **Backend** | Python 3.11+, FastAPI, Uvicorn, SQLAlchemy 2.0, Alembic, PostgreSQL, JWT (python-jose + bcrypt) |
| **Frontend** | React 19, TypeScript, Vite, React Router 7, Three.js |
| **Tests** | pytest (backend, isolated in-memory SQLite) |
| **Lint / build** | oxlint, `tsc -b` |

Two independent apps in one repo, talking over a REST API.

---

## Quick start

Prerequisites: **Python 3.11+**, **Node 20+**, and a running **PostgreSQL**.

```bash
git clone https://github.com/Sandhya192005/home-layout.git
cd home-layout
```

### 1. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt

cp .env.example .env             # then edit DATABASE_URL and SECRET_KEY
createdb ai_home_layout          # Postgres must be running
alembic upgrade head

uvicorn app.main:app --reload
```

The API runs on `http://localhost:8000`, with interactive docs at
`http://localhost:8000/docs` and a health check at `/health`.

### 2. Frontend

In a second terminal:

```bash
cd frontend
npm install
cp .env.example .env             # VITE_API_BASE_URL=http://localhost:8000/api/v1
npm run dev
```

Open the URL Vite prints (`http://localhost:5173` by default), register an
account, create a project, fill in the requirement form and generate.

---

## Configuration

All backend settings are environment-driven via `backend/.env`, and every
one has a working default — the app boots with no `.env` at all.

| Variable | Default | Notes |
| --- | --- | --- |
| `DATABASE_URL` | local Postgres `ai_home_layout` | SQLAlchemy URL |
| `SECRET_KEY` | dev placeholder | **change this** for any real deployment |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | |
| `BACKEND_CORS_ORIGINS` | `:3000` and `:5173` | a frontend on any other port is CORS-blocked until added here |
| `PUBLIC_SHARE_RATE_LIMIT_MAX` | `30` | requests per window on the public share endpoint |
| `PUBLIC_SHARE_RATE_LIMIT_WINDOW_SECONDS` | `60` | |
| `NVIDIA_NIM_API_KEY` | *(empty)* | blank disables the chat assistant |
| `NVIDIA_NIM_BASE_URL` | `https://integrate.api.nvidia.com/v1` | any OpenAI-compatible endpoint |
| `NVIDIA_NIM_MODEL` | `meta/llama-3.1-8b-instruct` | |

The frontend's `.env` holds only `VITE_API_BASE_URL`.

---

## How generation works

Every dimension in the output is derived from the input.

1. **Buildable rectangle** — plot length, width and facing minus mandatory
   setbacks.
2. **Room program** — a flat room list built from bedroom and bathroom
   counts plus optional and additional rooms, split across floors according
   to `floor_type`.
3. **Vastu zone assignment** — each room greedily assigned a preferred
   compass zone (N/NE/E/SE/S/SW/W/NW/C) on a 3×3 grid, load-balanced. With
   Vastu off, a functional fallback order is used instead. The entrance
   room is always pinned to whichever edge the plot's facing puts on the
   street.
4. **Grid slicing** — the buildable rectangle becomes a weighted grid, but
   every room's minimum width and length is guaranteed first whenever the
   floor has enough total area for the whole program. Leftover space is
   then distributed by weight, biased toward sane room aspect ratios so a
   lightly-weighted room doesn't end up a sliver.
5. **Parking** — carved from the ground-floor front setback, extending into
   the footprint if the vehicles don't fit within the setback alone.
6. **Staircase and veranda** — cut as full-edge strips before slicing, so
   the staircase stacks identically on every floor and the veranda spans
   the whole facade.
7. **Walls, doors, windows, furniture** — derived from the final room
   rectangles. Doors form a spanning tree over every pair of rooms sharing
   a wall wide enough for a doorway, so every room is reachable.
8. **Site elements** — the compound gate, and a wheelchair ramp when
   requested.

Cost, BOQ, construction timeline and FAR are then estimated from the
resulting built-up area, and re-derived after every manual edit.

Manual edits never regenerate from scratch — they mutate the stored plan
and re-run the *same* wall/door/window derivation the generator uses, so a
hand-edited layout keeps the same guarantees as a freshly generated one.

---

## API overview

All routes are prefixed with `/api/v1`. Full interactive reference at
`/docs`.

| Area | Routes |
| --- | --- |
| Auth | `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me` |
| Projects | `GET/POST /projects`, `GET/PUT/DELETE /projects/{id}` |
| Requirements | `POST /projects/{id}/requirements`, `GET .../latest`, `POST .../{req_id}/generate` |
| Floor plans | `GET /projects/{id}/floorplans`, `.../latest`, `GET/PATCH/DELETE .../{plan_id}` |
| Plan editing | `PUT .../{plan_id}/furniture`, `.../rooms`, `.../parking`, `.../plan-data`, `PUT .../rooms/{room_id}/replace`, `POST/DELETE .../rooms/{room_id}/attached-bathroom` |
| Sharing | `POST/GET/DELETE .../{plan_id}/share`, plus public `GET /public/floorplans/{token}` |
| Chat | `POST /chat` |

---

## Testing

```bash
cd backend
.venv\Scripts\python.exe -m pytest                                 # full suite
.venv\Scripts\python.exe -m pytest tests/test_generation.py -q      # one file
```

The suite is fully isolated — each test gets its own in-memory SQLite
database and never touches the Postgres instance in `DATABASE_URL`.

Two standalone smoke scripts cover the same ground end to end without
pytest:

```bash
python backend/scripts/smoke_test_generator.py   # layout engine across 4 scenarios
python backend/scripts/smoke_test_api.py         # full HTTP flow incl. cross-user 403 checks
```

The frontend has no test runner. `npm run build` (`tsc -b && vite build`)
is the type-checking gate, and `npm run lint` runs oxlint.

---

## Project structure

```
backend/
  app/
    api/v1/      routers: auth, projects, requirements, floorplans, public, chat
    core/        settings, DB session, JWT/password security, rate limiting
    models/      SQLAlchemy ORM (soft-delete audit mixin on everything)
    schemas/     Pydantic request/response models
    crud/        DB access functions
    services/
      floorplan_generator.py   the layout engine — the core of the project
      geometry.py              rectangle/wall/door math
      cost_estimator.py        cost tiers, BOQ, timeline, FAR
      validation.py            requirement sanity checks
      chat_assistant.py        the one external AI call
    utils/constants.py         room library, setback rules, cost rates
  alembic/versions/            hand-written migrations
  tests/                       pytest suite
frontend/
  src/
    api/         fetch wrapper + TypeScript mirrors of the backend schemas
    components/  FloorPlanViewer (SVG + editor), FloorPlan3DView, ChatWidget
    pages/       login, register, projects, project detail, shared plan
```

`ARCHITECTURE.md` has Mermaid diagrams of the request flow; `CLAUDE.md`
carries the detailed engineering notes and invariants.

---

## Known limitations

These are deliberate scope choices, documented rather than hidden:

- Setback rules, cost tiers (INR) and BOQ ratios in
  `backend/app/utils/constants.py` are **illustrative defaults**, not any
  specific municipal code. Swap them for your locality before relying on
  the numbers.
- Rooms are axis-aligned rectangles only — no L-shaped or polygonal rooms.
- Every floor shares the same footprint; there are no upper-floor
  step-backs.
- The layout engine is a weighted-partition heuristic, not a constraint
  solver. On genuinely tight plots — say a 22ft frontage carrying three
  floors of bedrooms — it cannot honor every room's minimum size, and flags
  those rooms via `below_min_size` instead of pretending they fit.
- Cost, BOQ and timeline figures are indicative, not a substitute for a
  quantity surveyor or a structural engineer.

---

## License

No license file is currently included, so all rights are reserved by
default. Add a `LICENSE` file if you intend others to reuse this code.
