from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.crud import floorplan_share as share_crud
from app.crud import project as project_crud
from app.schemas.floorplan_share import PublicFloorPlanRead

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/floorplans/{token}", response_model=PublicFloorPlanRead)
def get_public_floor_plan(token: str, db: Session = Depends(get_db)):
    share = share_crud.get_by_token(db, token)
    plan = share.floor_plan if share else None
    if not share or not plan or plan.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found or revoked")
    project = project_crud.get_project(db, plan.project_id)
    return PublicFloorPlanRead(
        project_name=project.name if project else "Floor plan",
        version=plan.version,
        status=plan.status,
        plan_data=plan.plan_data,
        total_built_up_area=plan.total_built_up_area,
        estimated_cost=plan.estimated_cost,
    )
