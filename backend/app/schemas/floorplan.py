from typing import Any

from pydantic import BaseModel, ConfigDict, Field

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


class RoomRectUpdate(BaseModel):
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    width: float = Field(gt=0)
    length: float = Field(gt=0)


class RoomLayoutUpdate(BaseModel):
    floor_number: int
    rooms: dict[str, RoomRectUpdate]


class ParkingRectUpdate(BaseModel):
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    width: float = Field(gt=0)
    length: float = Field(gt=0)


class ParkingLayoutUpdate(BaseModel):
    floor_number: int
    parking: ParkingRectUpdate


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


class AttachedBathroomCreate(BaseModel):
    floor_number: int


class AttachedBathroomResponse(BaseModel):
    floor_plan: FloorPlanRead
    warnings: list[str] = []


class RoomReplaceRequest(BaseModel):
    floor_number: int
    new_type: str


class RoomReplaceResponse(BaseModel):
    floor_plan: FloorPlanRead
    warnings: list[str] = []


class PlanDataRestore(BaseModel):
    """Restores plan_data to a previously-returned snapshot -- what the
    frontend's undo/redo stack sends back. Not itself re-validated against
    geometry rules: the snapshot was already a server-returned, previously
    committed state, so this only checks it has the right overall shape."""

    plan_data: dict[str, Any]
