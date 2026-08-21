from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.mixins import AuditRead


class FurnitureItemUpdate(BaseModel):
    type: str
    x: float
    y: float
    w: float
    l: float
    rotation: float = 0


class FurnitureLayoutUpdate(BaseModel):
    floor_number: int
    furniture_by_room: dict[str, list[FurnitureItemUpdate]]


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
