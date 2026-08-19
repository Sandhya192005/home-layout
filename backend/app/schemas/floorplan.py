from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.mixins import AuditRead


class FloorPlanRead(AuditRead):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    requirement_id: int
    version: int
    status: str
    plan_data: dict[str, Any]
    total_built_up_area: float
    estimated_cost: float


class FloorPlanGenerateResponse(BaseModel):
    floor_plan: FloorPlanRead
    warnings: list[str] = []


class FloorPlanStatusUpdate(BaseModel):
    status: str
