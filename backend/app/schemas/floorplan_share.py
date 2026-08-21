from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.mixins import AuditRead


class FloorPlanShareRead(AuditRead):
    model_config = ConfigDict(from_attributes=True)

    id: int
    floor_plan_id: int
    token: str


class PublicFloorPlanRead(BaseModel):
    project_name: str
    version: int
    status: str
    plan_data: dict[str, Any]
    total_built_up_area: float
    estimated_cost: float
