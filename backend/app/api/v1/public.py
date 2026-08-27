from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import RateLimiter
from app.crud import floorplan_share as share_crud
from app.crud import project as project_crud
from app.schemas.floorplan_share import PublicFloorPlanRead

router = APIRouter(prefix="/public", tags=["public"])

public_share_limiter = RateLimiter(
    settings.PUBLIC_SHARE_RATE_LIMIT_MAX, settings.PUBLIC_SHARE_RATE_LIMIT_WINDOW_SECONDS
)


def rate_limit_public_share(request: Request) -> None:
    client_host = request.client.host if request.client else "unknown"
    if not public_share_limiter.allow(client_host):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests to this shared link -- try again in a minute.",
        )


@router.get("/floorplans/{token}", response_model=PublicFloorPlanRead, dependencies=[Depends(rate_limit_public_share)])
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
