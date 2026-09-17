# AI Home Layout — Frontend

React + TypeScript single-page app for the AI Home Layout project: submit
home-building requirements, generate a floor plan, explore it in 2D and 3D,
edit it by hand, and share it.

See the [root README](../README.md) for the project overview and
`../ARCHITECTURE.md` for diagrams.

## Stack

React 19 · TypeScript · Vite · React Router 7 · Three.js

No state-management library and no CSS framework — data flows through direct
`api/client.ts` calls in page components plus `AuthContext`, and each
page/component pairs with its own hand-written `*.css` file.

## Setup

The [backend](../backend/README.md) needs to be running first.

```bash
cd frontend
npm install
cp .env.example .env     # VITE_API_BASE_URL=http://localhost:8000/api/v1
npm run dev
```

Open the URL Vite prints (`http://localhost:5173` by default) and register
an account.

`VITE_API_BASE_URL` is the only environment variable. Note that the backend
allows CORS from `:5173` and `:3000` by default — if you serve this from
another port, add it to the backend's `BACKEND_CORS_ORIGINS`.

## Scripts

| Command | What it does |
| --- | --- |
| `npm run dev` | Vite dev server with HMR |
| `npm run build` | `tsc -b && vite build` — **the real type-checking gate** |
| `npm run lint` | oxlint |
| `npm run preview` | serve the production build locally |

`npm run lint` is not type-aware: beyond the defaults it only enables
`react/rules-of-hooks` and `react/only-export-components`, and it will not
catch type errors. Run `npm run build` before calling a change done.

There is no test runner configured.

## Structure

```
src/
  api/
    client.ts      thin fetch wrapper (api.* namespace)
    types.ts       TypeScript mirrors of the backend schemas
  context/
    AuthContext.tsx      auth state, wraps the whole app
  components/
    Layout.tsx           routing shell
    ProtectedRoute.tsx   auth gate
    FloorPlanViewer.tsx  the big one — SVG rendering, the layout and
                         furniture editors, PNG/PDF export
    FloorPlan3DView.tsx  Three.js walkthrough of the same plan data
    ChatWidget.tsx       floating "Ask about your house" panel
    furnitureIcons.ts, siteIcons.ts   icon/glyph lookups keyed by type
  pages/
    LoginPage, RegisterPage, ProjectsPage,
    ProjectDetailPage      requirement form, generate, plan history, compare
    SharedFloorPlanPage    public read-only view
```

### Routing

`/login` and `/register` are public. `/share/:token` renders inside the
shared `Layout` but without `ProtectedRoute`, so an unauthenticated visitor
can open a shared plan. `/projects` and `/projects/:projectId` require auth.
Everything else redirects to `/projects`.

### Auth and the API client

`api/client.ts` stores the access token in `localStorage` under `ahl_token`
and the refresh token under `ahl_refresh_token`. A `401` triggers one
deduped silent refresh-and-retry before the error surfaces, so an expired
access token doesn't bounce the user to the login screen. `ApiError`
normalizes FastAPI and Pydantic error shapes down to a message string.

## Features

- **Requirement form** → generate a plan; regenerating creates a new
  version rather than overwriting, with plan history and version compare.
- **2D viewer** — SVG floor plan with a room schedule.
- **3D view** — a Three.js/OrbitControls walkthrough rebuilt procedurally
  from the same plan JSON (rooms, furniture, roof, parked vehicles); there
  is no separate 3D data model. Includes per-floor isolation, so you can
  view one floor or the whole stack.
- **Layout editor** — drag to move or resize a room via four corner
  handles, or drag a shared wall to resize two rooms at once. Also parking
  resize, attached-bathroom add/remove, and room-type replacement from the
  room schedule.
- **Furniture editor** — reposition furniture within a room.
- **Undo/redo** — `ProjectDetailPage` keeps a client-side stack of
  `plan_data` snapshots. Every edit path funnels through one
  `applyPlanUpdate` callback, so a single backend restore endpoint serves
  undo/redo for all edit types with no per-edit inverse logic.
- **Export** — PNG via `canvas.toBlob`, and PDF via a hand-rolled minimal
  PDF builder (`buildMinimalPdf`). There are deliberately no PDF or canvas
  libraries in `package.json`.
- **Sharing** — create a public link that renders at `/share/:token`.
- **Chat** — `ChatWidget`, mounted in `Layout` for any logged-in user.

## Gotchas when working on the viewer

**`FloorPlanViewer.tsx` renders the plan two different ways.** A static SVG
string built by `buildFloorSvg` and injected via `dangerouslySetInnerHTML`
(producing `.room-outline`, `.room-label`, …), driven by `floor.rooms` from
props — this **never updates during a live drag**. And an interactive JSX
overlay rendered only in layout-edit mode (producing `.room-edit-rect`,
`.room-edit-handle`, …), driven by live `localRooms` state — this **does**
update during drags. Inspecting `.room-outline` to check whether a drag
worked will always show no change, regardless of the actual result.

**Furniture `w`/`l` is the post-rotation bounding box**, with `rotation`
stored as a separate field. Building a correctly oriented mesh or icon means
un-swapping back to the natural pose first — `rotation % 180 !== 0` means
the dimensions are swapped. `FloorPlan3DView` and the 2D icon renderer both
apply this same transform.

**The viewer toolbar is a two-row flex-wrap layout** specifically so
controls wrap onto a new line instead of silently overflowing off-panel as
more buttons get added. Keep new toolbar buttons inside `.toolbar-row`.

**Plan coordinates are in feet**, with `x` running west→east and `y` running
north→south, so `y` grows *downward* on screen — which happens to match SVG
convention.
