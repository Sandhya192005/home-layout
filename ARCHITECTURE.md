# Architecture

Visual companion to `CLAUDE.md` — that file has the prose detail (routes,
invariants, gotchas); this one is diagrams of how the pieces fit together
and how a request actually flows through the system. Open in VS Code with
the "Markdown Preview Mermaid Support" extension (or view on GitHub) to
render the diagrams.

## 1. System overview

Two independent apps talking over a REST API, plus one external AI call.

```mermaid
flowchart LR
    subgraph Browser["Browser"]
        UI["React 19 + Vite frontend\n(FloorPlanViewer, FloorPlan3DView,\nProjectDetailPage, ChatWidget, ...)"]
    end

    subgraph API["FastAPI backend  (app/api/v1/*)"]
        Auth["auth"]
        Projects["projects"]
        Requirements["requirements"]
        Floorplans["floorplans"]
        Public["public"]
        Chat["chat"]
    end

    subgraph Services["services/"]
        Gen["floorplan_generator.py\n(layout engine)"]
        Geo["geometry.py"]
        Cost["cost_estimator.py"]
        Valid["validation.py"]
        ChatSvc["chat_assistant.py"]
    end

    DB[("PostgreSQL\n(SQLAlchemy models)")]
    NIM["NVIDIA NIM\n(OpenAI-compatible LLM API)"]

    UI -- "fetch via api/client.ts\n(JWT + refresh token)" --> API
    Auth --> DB
    Projects --> DB
    Requirements --> Valid
    Requirements --> DB
    Floorplans --> Gen
    Floorplans --> Geo
    Floorplans --> Cost
    Floorplans --> DB
    Public --> DB
    Chat --> ChatSvc
    ChatSvc -- "httpx" --> NIM

    style NIM fill:#f7d9c4,stroke:#8a5a44
```

**Only one external AI call in the whole app**: the chat assistant. Floor
plan generation, cost/BOQ estimation, and every manual edit (drag-resize,
attach-bathroom, parking resize) are pure geometry/rule-based code — no LLM
involved.

## 2. Generate-a-floor-plan request flow

What happens end to end when a user fills the requirement form and clicks
"Generate".

```mermaid
sequenceDiagram
    participant U as Browser
    participant R as requirements router
    participant V as validation.py
    participant F as floorplans router
    participant G as floorplan_generator.py
    participant C as cost_estimator.py
    participant D as PostgreSQL

    U->>R: POST /projects/{id}/requirements
    R->>V: validate requirement
    V-->>R: ok / 400
    R->>D: insert Requirement
    D-->>R: requirement_id
    R-->>U: 201 Requirement

    U->>F: POST /requirements/{id}/generate
    F->>G: generate_floor_plan(requirement)
    G->>G: buildable rect -> room program -> Vastu zones ->\ngrid slicing -> parking -> staircase ->\nwalls / doors / windows / furniture
    G-->>F: plan_data (JSON)
    F->>C: estimate_cost / estimate_boq /\nestimate_far / estimate_timeline
    C-->>F: cost + BOQ + timeline + FAR
    F->>D: insert FloorPlan (version = prev + 1)
    D-->>F: floor_plan_id
    F-->>U: 201 FloorPlan (plan_data + estimates)
```

Regenerating never overwrites a plan — it inserts a new `FloorPlan` row
with `version = previous + 1`, so plan history per project is preserved.

## 3. Inside the layout engine (`generate_floor_plan`)

The seven-step pipeline that turns a `Requirement` into `plan_data`,
per floor.

```mermaid
flowchart TD
    A["Requirement\n(plot size, facing, rooms, parking, floors, Vastu)"] --> B["1. Buildable rectangle\ncompute_buildable_rect() minus setbacks"]
    B --> C["2. Room program\nflat list of RoomInstances, split across floors"]
    C --> D["3. Vastu zone assignment\ngreedy N/NE/E/SE/S/SW/W/NW/C, load-balanced;\nentrance pinned to facing edge"]
    D --> E["4. Grid slicing\nweighted 3x3 grid; min_w/min_l guaranteed first,\n3-cell rows split into sub-rows"]
    E --> F["5. Parking\ncarved from front setback,\nextends into footprint if needed"]
    F --> G["6. Staircase\nfixed-width strip, consistent edge\nacross floors (multi-floor only)"]
    G --> H["7. Walls / doors / windows / furniture\ndoors = Kruskal's spanning TREE\nover shared walls (widest first)"]
    H --> I["plan_data JSON\n(floors[], each with rooms/walls/doors/windows/furniture/parking)"]
```

**Known simplification**: every floor shares the same footprint, except
"independent-floor duplex mode" which lets floors diverge.

## 4. Manual post-generation edits

Three endpoints mutate `plan_data` in place instead of regenerating from
scratch — all funnel through the same two functions, reusing the exact
derivation the generator itself uses so a hand-edited layout keeps the same
connectivity guarantees.

```mermaid
flowchart TD
    subgraph Endpoints["api/v1/floorplans.py"]
        E1["PUT .../rooms\n(drag-move/resize a room)"]
        E2["PUT .../parking\n(drag-resize parking rect)"]
        E3["POST/DELETE .../rooms/{id}/attached-bathroom\n(add_attached_bathroom / remove_attached_bathroom)"]
    end

    E1 --> RC["recompute_floor_geometry(floor, facing)\nrebuilds windows/doors/walls from\ncurrent room x/y/width/length"]
    E2 --> RC
    E3 --> RC
    RC --> Conn["rooms_are_connected(room_ids, doors)\nunion-find over rebuilt door graph"]
    Conn -->|connected| Commit["commit plan_data\n(flag_modified + db.commit)"]
    Conn -->|disconnected| Reject["reject / raise\n(trial-copy pattern:\nnever commit a broken layout)"]
```

Two geometry invariants make this safe — see
`.claude/rules/room-geometry.md` for the full writeup:

- A rect can only be split along a **full edge** (never a corner notch —
  the room model has no polygon support).
- Rebuilding from **already-rounded, stored** rects needs a larger touch
  tolerance (`0.05`) than the strict tolerance the initial generation pass
  uses, or rounding slivers silently disconnect rooms.

## 5. Data model

```mermaid
erDiagram
    USER ||--o{ PROJECT : owns
    PROJECT ||--o{ REQUIREMENT : has
    REQUIREMENT ||--o{ FLOOR_PLAN : "generates versions of"
    FLOOR_PLAN ||--o| FLOOR_PLAN_SHARE : "may have"
    USER ||--o{ REFRESH_TOKEN : holds

    USER {
        int id
        string email
        string password_hash
    }
    PROJECT {
        int id
        int user_id
        string name
    }
    REQUIREMENT {
        int id
        int project_id
        json plot_and_room_program
    }
    FLOOR_PLAN {
        int id
        int requirement_id
        int version
        json plan_data
        float total_built_up_area
        float estimated_cost
    }
    FLOOR_PLAN_SHARE {
        int id
        int floor_plan_id
        string token
    }
    REFRESH_TOKEN {
        int id
        int user_id
        string token_hash
    }
```

Every model mixes in `AuditMixin` (`created_at` / `updated_at` /
`deleted_at` / `deleted_by` / `is_active`) — **soft delete only**, rows are
flagged not physically removed. `FloorPlanShare.token` is stored in the
clear (it's a link meant to be shared); `RefreshToken.token_hash` stores
only a sha256 hash (it's a bearer secret).

## 6. Frontend view layer

```mermaid
flowchart LR
    PD["ProjectDetailPage\n(requirement form, generate, version history)"]
    FPV["FloorPlanViewer\n(~2000 lines)"]
    F3D["FloorPlan3DView\n(Three.js)"]
    CW["ChatWidget\n(floating, mounted in Layout)"]

    PD --> FPV
    FPV -->|"viewMode toggle"| F3D
    FPV -->|"static SVG string\n(buildFloorSvg, dangerouslySetInnerHTML)\nnever updates during drag"| SVG["2D plan display"]
    FPV -->|"interactive JSX overlay\n(localRooms state)\nupdates live during drags"| Edit["room/furniture edit mode"]
    CW -->|"POST /chat"| Chat["chat router"]
```

Both `FloorPlanViewer` and `FloorPlan3DView` render from the same
`plan_data` prop — no separate 3D data model. `FloorPlan3DView` rebuilds
its Three.js scene procedurally on every relevant prop/state change
(plan, floor filter, roof toggle, furniture toggle).
