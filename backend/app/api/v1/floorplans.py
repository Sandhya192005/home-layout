from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.api.deps import get_current_user
from app.api.v1.projects import _get_owned_project
from app.core.database import get_db
from app.crud import floorplan as floorplan_crud
from app.crud import floorplan_share as share_crud
from app.models.user import User
from app.schemas.floorplan import FloorPlanRead, FloorPlanStatusUpdate, FurnitureLayoutUpdate
from app.schemas.floorplan_share import FloorPlanShareRead

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


def _get_owned_floor_plan(db: Session, project_id: int, floor_plan_id: int, current_user: User):
    _get_owned_project(db, project_id, current_user)
    plan = floorplan_crud.get_floor_plan(db, floor_plan_id)
    if not plan or plan.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Floor plan not found")
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
