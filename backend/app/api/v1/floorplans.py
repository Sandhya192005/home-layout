from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.api.deps import get_current_user
from app.api.v1.projects import _get_owned_project
from app.core.database import get_db
from app.crud import floorplan as floorplan_crud
from app.crud import floorplan_share as share_crud
from app.crud import requirement as requirement_crud
from app.models.user import User
from app.schemas.floorplan import (
    AttachedBathroomCreate,
    AttachedBathroomResponse,
    FloorPlanRead,
    FloorPlanStatusUpdate,
    FurnitureLayoutUpdate,
    ParkingLayoutUpdate,
    PlanDataRestore,
    RoomLayoutUpdate,
    RoomReplaceRequest,
    RoomReplaceResponse,
)
from app.schemas.floorplan_share import FloorPlanShareRead
from app.services import floorplan_generator as fpg
from app.services import geometry as geo
from app.services.cost_estimator import estimate_boq, estimate_construction_timeline, estimate_cost, estimate_far
from app.utils.constants import CAR_PARKING_SIZE, TWO_WHEELER_PARKING_SIZE

router = APIRouter(prefix="/projects/{project_id}/floorplans", tags=["floorplans"])


@router.get("", response_model=list[FloorPlanRead])
def list_floor_plans(
    project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    _get_owned_project(db, project_id, current_user)
    return floorplan_crud.list_floor_plans(db, project_id)


@router.get("/latest", response_model=FloorPlanRead)
def get_latest_floor_plan(
    project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    _get_owned_project(db, project_id, current_user)
    plan = floorplan_crud.get_latest_floor_plan(db, project_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No floor plan generated yet")
    return plan


@router.get("/{floor_plan_id}", response_model=FloorPlanRead)
def get_floor_plan(
    project_id: int, floor_plan_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    _get_owned_project(db, project_id, current_user)
    plan = floorplan_crud.get_floor_plan(db, floor_plan_id)
    if not plan or plan.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Floor plan not found")
    return plan


@router.patch("/{floor_plan_id}", response_model=FloorPlanRead)
def update_floor_plan_status(
    project_id: int,
    floor_plan_id: int,
    status_in: FloorPlanStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_owned_project(db, project_id, current_user)
    plan = floorplan_crud.get_floor_plan(db, floor_plan_id)
    if not plan or plan.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Floor plan not found")
    plan.status = status_in.status
    plan.updated_by = current_user.id
    db.commit()
    db.refresh(plan)
    return plan


@router.delete("/{floor_plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_floor_plan(
    project_id: int, floor_plan_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    _get_owned_project(db, project_id, current_user)
    plan = floorplan_crud.get_floor_plan(db, floor_plan_id)
    if not plan or plan.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Floor plan not found")
    floorplan_crud.delete_floor_plan(db, plan, current_user.id)


@router.put("/{floor_plan_id}/furniture", response_model=FloorPlanRead)
def update_furniture_layout(
    project_id: int,
    floor_plan_id: int,
    payload: FurnitureLayoutUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_owned_project(db, project_id, current_user)
    plan = floorplan_crud.get_floor_plan(db, floor_plan_id)
    if not plan or plan.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Floor plan not found")

    floors = plan.plan_data.get("floors", [])
    floor = next((f for f in floors if f.get("floor_number") == payload.floor_number), None)
    if not floor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Floor not found")

    valid_room_ids = {r["id"] for r in floor.get("rooms", [])}
    unknown = set(payload.furniture_by_room) - valid_room_ids
    if unknown:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown room id(s): {sorted(unknown)}")

    for room in floor.get("rooms", []):
        if room["id"] in payload.furniture_by_room:
            room["furniture"] = [item.model_dump() for item in payload.furniture_by_room[room["id"]]]

    flag_modified(plan, "plan_data")
    plan.updated_by = current_user.id
    db.commit()
    db.refresh(plan)
    return plan


@router.put("/{floor_plan_id}/rooms", response_model=FloorPlanRead)
def update_room_layout(
    project_id: int,
    floor_plan_id: int,
    payload: RoomLayoutUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_owned_project(db, project_id, current_user)
    plan = floorplan_crud.get_floor_plan(db, floor_plan_id)
    if not plan or plan.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Floor plan not found")

    floors = plan.plan_data.get("floors", [])
    floor = next((f for f in floors if f.get("floor_number") == payload.floor_number), None)
    if not floor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Floor not found")

    rooms_by_id = {r["id"]: r for r in floor["rooms"]}
    unknown = set(payload.rooms) - set(rooms_by_id)
    if unknown:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown room id(s): {sorted(unknown)}")

    staircase_edits = {rid for rid in payload.rooms if rooms_by_id[rid]["type"] == "staircase"}
    if staircase_edits:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"The staircase can't be resized -- it must stay aligned across floors: {sorted(staircase_edits)}",
        )

    outline = floor["outline"]
    outline_rect = {"x": outline["x"], "y": outline["y"], "w": outline["width"], "l": outline["length"]}

    new_rects = {r["id"]: {"x": r["x"], "y": r["y"], "w": r["width"], "l": r["length"]} for r in floor["rooms"]}
    for room_id, upd in payload.rooms.items():
        new_rects[room_id] = {"x": upd.x, "y": upd.y, "w": upd.width, "l": upd.length}

    eps = 1e-6
    # A small (sub-half-inch) overlap tolerance: stored room rects are each
    # independently rounded to 2 decimals at generation time, so two rooms
    # that are meant to exactly touch can already differ by a ~0.01 ft
    # rounding sliver -- only re-check pairs touching an *edited* room
    # (unedited pairs were already accepted at generation time) so that
    # pre-existing rounding noise elsewhere on the floor is never re-flagged.
    overlap_tolerance = 0.05
    edited_ids = list(payload.rooms.keys())

    for room_id in edited_ids:
        rect = new_rects[room_id]
        if (
            rect["x"] < outline_rect["x"] - eps
            or rect["y"] < outline_rect["y"] - eps
            or geo.rect_x2(rect) > geo.rect_x2(outline_rect) + eps
            or geo.rect_y2(rect) > geo.rect_y2(outline_rect) + eps
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Room '{room_id}' would extend outside the floor's outer walls.",
            )

    checked_pairs = set()
    for a in edited_ids:
        for b in new_rects:
            if a == b:
                continue
            pair_key = tuple(sorted((a, b)))
            if pair_key in checked_pairs:
                continue
            checked_pairs.add(pair_key)
            if geo.rects_overlap(new_rects[a], new_rects[b], tolerance=overlap_tolerance):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=f"Rooms '{a}' and '{b}' would overlap."
                )

    # Commit the validated rects, clearing furniture only for rooms that
    # actually moved/resized -- furniture positions are stored in absolute
    # plot coordinates, so old placements would otherwise land outside (or
    # inside a wall of) the room's new bounds.
    for room_id, upd in payload.rooms.items():
        room = rooms_by_id[room_id]
        moved = (
            abs(room["x"] - upd.x) > eps
            or abs(room["y"] - upd.y) > eps
            or abs(room["width"] - upd.width) > eps
            or abs(room["length"] - upd.length) > eps
        )
        room["x"], room["y"], room["width"], room["length"] = upd.x, upd.y, upd.width, upd.length
        if moved:
            room["furniture"] = []

    fpg.recompute_floor_geometry(floor, plan.plan_data["meta"]["facing"])

    if not fpg.rooms_are_connected([r["id"] for r in floor["rooms"]], floor["doors"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This layout would leave one or more rooms unreachable -- keep every room touching at least "
            "one neighbor with a wide enough shared wall for a doorway.",
        )

    total_area = round(sum(r["width"] * r["length"] for f in floors for r in f["rooms"]), 2)
    plan.plan_data["meta"]["total_built_up_area"] = total_area
    plan.total_built_up_area = total_area

    flag_modified(plan, "plan_data")
    plan.updated_by = current_user.id
    db.commit()
    db.refresh(plan)
    return plan


def _recalculate_estimates(db: Session, plan) -> None:
    """Re-derive total_built_up_area, the cost/BOQ/timeline/FAR meta, and the
    stored total_built_up_area/estimated_cost columns from the plan's current
    room geometry -- shared by any endpoint that edits room geometry after
    generation (the attached-bathroom add/remove routes below)."""
    floors = plan.plan_data.get("floors", [])
    total_area = round(sum(r["width"] * r["length"] for f in floors for r in f["rooms"]), 2)
    plan.plan_data["meta"]["total_built_up_area"] = total_area
    plan.total_built_up_area = total_area

    requirement = requirement_crud.get_requirement(db, plan.requirement_id)
    budget = requirement.budget if requirement else 0
    cost = estimate_cost(total_area, budget)
    plan.plan_data["meta"]["cost_estimate"] = cost
    plan.plan_data["meta"]["boq"] = estimate_boq(total_area)
    plan.plan_data["meta"]["construction_timeline"] = estimate_construction_timeline(
        total_area, plan.plan_data["meta"]["floors"]
    )
    plot_area = plan.plan_data["meta"]["plot_length"] * plan.plan_data["meta"]["plot_width"]
    plan.plan_data["meta"]["far"] = estimate_far(total_area, plot_area)
    plan.estimated_cost = cost["recommended_cost"]


@router.put("/{floor_plan_id}/plan-data", response_model=FloorPlanRead)
def restore_plan_data(
    project_id: int,
    floor_plan_id: int,
    payload: PlanDataRestore,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Overwrites plan_data wholesale with a previously-returned snapshot --
    what the frontend's undo/redo stack calls. Every other endpoint in this
    file mutates plan_data incrementally and re-derives geometry from
    scratch; this one exists because undo/redo needs to restore *any* prior
    state uniformly (furniture, room/parking resize, attached-bathroom,
    room-replace) without a bespoke inverse for each edit type. Since the
    snapshot was already a server-returned, previously committed plan_data,
    it isn't re-run through geometry validation -- only checked for the
    right overall shape."""
    plan = _get_owned_floor_plan(db, project_id, floor_plan_id, current_user)
    floors = payload.plan_data.get("floors")
    meta = payload.plan_data.get("meta")
    if not isinstance(floors, list) or not isinstance(meta, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="plan_data must include 'floors' and 'meta'."
        )

    plan.plan_data = payload.plan_data
    _recalculate_estimates(db, plan)
    flag_modified(plan, "plan_data")
    plan.updated_by = current_user.id
    db.commit()
    db.refresh(plan)
    return plan


@router.post("/{floor_plan_id}/rooms/{room_id}/attached-bathroom", response_model=AttachedBathroomResponse)
def add_attached_bathroom(
    project_id: int,
    floor_plan_id: int,
    room_id: str,
    payload: AttachedBathroomCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plan = _get_owned_floor_plan(db, project_id, floor_plan_id, current_user)
    floors = plan.plan_data.get("floors", [])
    floor = next((f for f in floors if f.get("floor_number") == payload.floor_number), None)
    if not floor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Floor not found")

    meta = plan.plan_data["meta"]
    try:
        _new_room, warnings = fpg.add_attached_bathroom(floor, room_id, meta["facing"], meta.get("vastu_compliant", False))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    _recalculate_estimates(db, plan)
    flag_modified(plan, "plan_data")
    plan.updated_by = current_user.id
    db.commit()
    db.refresh(plan)
    return AttachedBathroomResponse(floor_plan=FloorPlanRead.model_validate(plan), warnings=warnings)


@router.delete("/{floor_plan_id}/rooms/{room_id}/attached-bathroom", response_model=AttachedBathroomResponse)
def remove_attached_bathroom(
    project_id: int,
    floor_plan_id: int,
    room_id: str,
    floor_number: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plan = _get_owned_floor_plan(db, project_id, floor_plan_id, current_user)
    floors = plan.plan_data.get("floors", [])
    floor = next((f for f in floors if f.get("floor_number") == floor_number), None)
    if not floor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Floor not found")

    try:
        warnings = fpg.remove_attached_bathroom(floor, room_id, plan.plan_data["meta"]["facing"])
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    _recalculate_estimates(db, plan)
    flag_modified(plan, "plan_data")
    plan.updated_by = current_user.id
    db.commit()
    db.refresh(plan)
    return AttachedBathroomResponse(floor_plan=FloorPlanRead.model_validate(plan), warnings=warnings)


@router.put("/{floor_plan_id}/rooms/{room_id}/replace", response_model=RoomReplaceResponse)
def replace_room(
    project_id: int,
    floor_plan_id: int,
    room_id: str,
    payload: RoomReplaceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plan = _get_owned_floor_plan(db, project_id, floor_plan_id, current_user)
    floors = plan.plan_data.get("floors", [])
    floor = next((f for f in floors if f.get("floor_number") == payload.floor_number), None)
    if not floor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Floor not found")

    meta = plan.plan_data["meta"]
    try:
        _new_room, warnings = fpg.replace_room(
            floor, room_id, payload.new_type, meta["facing"], meta.get("vastu_compliant", False)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    _recalculate_estimates(db, plan)
    flag_modified(plan, "plan_data")
    plan.updated_by = current_user.id
    db.commit()
    db.refresh(plan)
    return RoomReplaceResponse(floor_plan=FloorPlanRead.model_validate(plan), warnings=warnings)


def _get_owned_floor_plan(db: Session, project_id: int, floor_plan_id: int, current_user: User):
    _get_owned_project(db, project_id, current_user)
    plan = floorplan_crud.get_floor_plan(db, floor_plan_id)
    if not plan or plan.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Floor plan not found")
    return plan


def _parking_min_size(parking: dict) -> tuple[float, float]:
    """Smallest width/length that still fits the parking's own declared
    vehicle capacity -- a single vehicle's own footprint, not the sum of
    all of them, since shrinking is meant to be allowed as long as at
    least one vehicle of each kind present still physically fits."""
    cars, bikes = parking["capacity_cars"], parking["capacity_two_wheelers"]
    widths = [w for w, has in ((CAR_PARKING_SIZE["w"], cars), (TWO_WHEELER_PARKING_SIZE["w"], bikes)) if has]
    depths = [l for l, has in ((CAR_PARKING_SIZE["l"], cars), (TWO_WHEELER_PARKING_SIZE["l"], bikes)) if has]
    return (max(widths) if widths else 3.0, max(depths) if depths else 3.0)


@router.put("/{floor_plan_id}/parking", response_model=FloorPlanRead)
def update_parking_layout(
    project_id: int,
    floor_plan_id: int,
    payload: ParkingLayoutUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plan = _get_owned_floor_plan(db, project_id, floor_plan_id, current_user)

    floors = plan.plan_data.get("floors", [])
    floor = next((f for f in floors if f.get("floor_number") == payload.floor_number), None)
    if not floor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Floor not found")
    if not floor.get("parking"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This floor has no parking to edit")

    meta = plan.plan_data["meta"]
    new_rect = {"x": payload.parking.x, "y": payload.parking.y, "w": payload.parking.width, "l": payload.parking.length}

    eps = 1e-6
    if (
        new_rect["x"] < -eps
        or new_rect["y"] < -eps
        or geo.rect_x2(new_rect) > meta["plot_width"] + eps
        or geo.rect_y2(new_rect) > meta["plot_length"] + eps
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Parking would extend outside the plot boundary.")

    min_w, min_l = _parking_min_size(floor["parking"])
    if payload.parking.width < min_w - eps or payload.parking.length < min_l - eps:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Parking needs at least {min_w:.0f}x{min_l:.0f} ft for the vehicles it's sized for.",
        )

    overlap_tolerance = 0.05
    for room in floor["rooms"]:
        room_rect = {"x": room["x"], "y": room["y"], "w": room["width"], "l": room["length"]}
        if geo.rects_overlap(new_rect, room_rect, tolerance=overlap_tolerance):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Parking would overlap room '{room['id']}'.")

    floor["parking"]["x"] = payload.parking.x
    floor["parking"]["y"] = payload.parking.y
    floor["parking"]["width"] = payload.parking.width
    floor["parking"]["length"] = payload.parking.length

    flag_modified(plan, "plan_data")
    plan.updated_by = current_user.id
    db.commit()
    db.refresh(plan)
    return plan


@router.get("/{floor_plan_id}/share", response_model=FloorPlanShareRead | None)
def get_share(
    project_id: int, floor_plan_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    _get_owned_floor_plan(db, project_id, floor_plan_id, current_user)
    return share_crud.get_active_share(db, floor_plan_id)


@router.post("/{floor_plan_id}/share", response_model=FloorPlanShareRead)
def create_share(
    project_id: int, floor_plan_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    _get_owned_floor_plan(db, project_id, floor_plan_id, current_user)
    return share_crud.create_share(db, floor_plan_id, current_user.id)


@router.delete("/{floor_plan_id}/share", status_code=status.HTTP_204_NO_CONTENT)
def revoke_share(
    project_id: int, floor_plan_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    _get_owned_floor_plan(db, project_id, floor_plan_id, current_user)
    share = share_crud.get_active_share(db, floor_plan_id)
    if share:
        share_crud.revoke_share(db, share, current_user.id)
