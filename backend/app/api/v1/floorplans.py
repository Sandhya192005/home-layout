from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.projects import _get_owned_project
from app.core.database import get_db
from app.crud import floorplan as floorplan_crud
from app.models.user import User
from app.schemas.floorplan import FloorPlanRead, FloorPlanStatusUpdate

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
