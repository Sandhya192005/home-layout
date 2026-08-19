# AI Home Layout — Backend

FastAPI backend that turns customer requirements (plot size, room program,
parking, floors, budget, Vastu preference) into a dynamically generated,
structured 2D floor plan for a React frontend to render.

## Stack

- Python 3.11+, FastAPI, Uvicorn
- PostgreSQL + SQLAlchemy 2.0 + Alembic
- JWT auth (python-jose + passlib/bcrypt)

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

Run migrations:

```bash
alembic upgrade head
```

Run the API:

```bash
uvicorn app.main:app --reload
```

Docs at `http://localhost:8000/docs`.

## Architecture

```
app/
  core/       config, database session, JWT/password security
  models/     SQLAlchemy ORM models (User, Project, Requirement, FloorPlan, AISuggestion)
  schemas/    Pydantic request/response models
  crud/       DB access functions
  api/v1/     FastAPI routers
  services/
    floorplan_generator.py  the dynamic layout engine (see below)
    geometry.py              rectangle/wall/door math helpers
    validation.py             requirement sanity checks
    cost_estimator.py         budget/tier estimation
    ai_suggestions.py         rule-based design suggestions
  utils/constants.py   room library (sizes, Vastu zones, furniture), setback rules
alembic/      DB migrations
```

## How generation works

Every dimension in the output is derived from the input — there is no fixed
template:

1. **Setbacks** are computed from plot length/width/facing to get a
   buildable rectangle.
2. A **room program** (list of rooms) is built from bedroom/bathroom counts,
   optional rooms, and additional rooms, and split across floors.
3. **Vastu zone assignment**: each room is greedily assigned to its
   preferred compass zone (N/NE/E/SE/S/SW/W/NW/C) in a 3x3 grid, balanced by
   load; if Vastu is disabled, a functional fallback order is used instead.
4. The buildable rectangle is sliced into a **weighted, minimum-size-aware
   grid**: rows/columns are sized proportional to the total room weight
   assigned to them, but every room's `min_w`/`min_l` is guaranteed first
   whenever the floor has enough total space for it — leftover space is then
   handed out by weight. Rows that end up with 3 occupied Vastu cells (which
   internally split into two stacked sub-rows) get their minimum depth sized
   for *both* sub-rows up front, and zone assignment itself is biased to
   avoid tripling up a row's column count unless Vastu compliance requires
   that exact cell — both changes exist specifically to stop the sliver/
   undersized rooms a naive weight-only split produces.
5. **Parking** is carved from the ground-floor front setback (extending into
   the footprint if vehicles don't fit within the setback alone).
6. A **staircase** strip (multi-floor only) is reserved at a fixed
   west/east edge so it stacks identically on every floor.
7. **Walls** (exterior outline + shared interior edges), **doors** (entrance
   + one internal door per room on its largest shared wall), **windows**
   (exterior-facing habitable rooms) and simple **furniture placement** are
   derived from the final room rectangles.

Changing plot size, room counts, floors, parking, or Vastu preference
changes every one of these steps, so the output plan changes accordingly.

## Key endpoints

- `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `GET /api/v1/auth/me`
- `POST /api/v1/projects`, `GET /api/v1/projects`, `GET/PUT/DELETE /api/v1/projects/{id}`
- `POST /api/v1/projects/{id}/requirements` — submit + validate requirements
- `POST /api/v1/projects/{id}/requirements/{req_id}/generate` — generate & persist a floor plan + AI suggestions
- `GET /api/v1/projects/{id}/floorplans`, `GET .../latest`, `GET/PATCH/DELETE .../{floor_plan_id}`
- `GET /api/v1/projects/{id}/suggestions/latest`

## Notes / simplifications

- Setback and cost figures are illustrative defaults, not a specific
  municipal code — swap `app/utils/constants.py` values for your locality.
- Every floor shares the same footprint (no upper-floor step-backs).
- The AI suggestion engine is deterministic/rule-based; it's isolated in
  `services/ai_suggestions.py` so it can be swapped for an LLM call later
  without touching the API layer.
- The room grid is a weighted-partition heuristic, not a full layout
  optimizer/constraint solver. It now guarantees each room's minimum size
  whenever the floor's total buildable area is large enough to fit the whole
  program (see step 4 above) — but on genuinely tight or very narrow plots
  (e.g. a ~22ft-wide frontage carrying 3 floors' worth of bedrooms) there
  still isn't enough physical space to honor every minimum. Those cases are
  flagged per-room via `below_min_size` in the plan JSON and surfaced as
  suggestions rather than silently hidden.
