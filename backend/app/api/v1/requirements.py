from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.projects import _get_owned_project
from app.core.database import get_db
from app.crud import floorplan as floorplan_crud
from app.crud import requirement as requirement_crud
from app.models.user import User
from app.schemas.floorplan import FloorPlanGenerateResponse, FloorPlanRead
from app.schemas.requirement import RequirementCreate, RequirementRead
from app.services.floorplan_generator import generate_floor_plan
from app.services.validation import validate_requirement

router = APIRouter(prefix="/projects/{project_id}/requirements", tags=["requirements"])


@router.post("", response_model=RequirementRead, status_code=status.HTTP_201_CREATED)
def submit_requirement(
    project_id: int,
    req_in: RequirementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_owned_project(db, project_id, current_user)
    errors, _warnings = validate_requirement(req_in)
    if errors:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"errors": errors})
    return requirement_crud.create_requirement(db, project_id, req_in, current_user.id)


@router.get("", response_model=list[RequirementRead])
def list_requirements(
    project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    _get_owned_project(db, project_id, current_user)
    return requirement_crud.list_requirements(db, project_id)


@router.get("/latest", response_model=RequirementRead)
def get_latest_requirement(
    project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    _get_owned_project(db, project_id, current_user)
    req = requirement_crud.get_latest_requirement(db, project_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No requirement submitted yet")
    return req


@router.post("/{requirement_id}/generate", response_model=FloorPlanGenerateResponse)
def generate_plan_for_requirement(
    project_id: int,
    requirement_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_owned_project(db, project_id, current_user)
    requirement = requirement_crud.get_requirement(db, requirement_id)
    if not requirement or requirement.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requirement not found")

    req_in = RequirementCreate.model_validate(requirement, from_attributes=True)
    errors, warnings = validate_requirement(req_in)
    if errors:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"errors": errors})

    plan_data, total_built_up_area = generate_floor_plan(req_in)

    from app.services.cost_estimator import estimate_boq, estimate_construction_timeline, estimate_cost, estimate_far

    cost = estimate_cost(total_built_up_area, req_in.budget)
    plot_area = req_in.plot_length * req_in.plot_width
    far = estimate_far(total_built_up_area, plot_area)
    plan_data["meta"]["cost_estimate"] = cost
    plan_data["meta"]["boq"] = estimate_boq(total_built_up_area)
    plan_data["meta"]["construction_timeline"] = estimate_construction_timeline(total_built_up_area, req_in.floors)
    plan_data["meta"]["far"] = far
    if far["exceeds_typical_limit"]:
        warnings.append(
            f"Floor-area-ratio (FAR) of the generated plan is {far['far']}, above the typical residential "
            f"limit of {far['max_far']} -- confirm local municipal FAR/FSI norms before proceeding."
        )

    floor_plan = floorplan_crud.create_floor_plan(
        db, project_id, requirement_id, plan_data, total_built_up_area, cost["recommended_cost"], current_user.id
    )

    return FloorPlanGenerateResponse(floor_plan=FloorPlanRead.model_validate(floor_plan), warnings=warnings)
