from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.mixins import AuditRead


class RequirementBase(BaseModel):
    plot_length: float = Field(gt=0, le=1000, description="North-South depth in feet")
    plot_width: float = Field(gt=0, le=1000, description="East-West frontage in feet")
    facing: Literal["north", "south", "east", "west"] = "north"

    family_members: int = Field(default=4, ge=1, le=30)
    bedrooms: int = Field(default=2, ge=1, le=12)
    bathrooms: int = Field(default=2, ge=1, le=12)

    has_living_room: bool = True
    has_dining_room: bool = True
    has_pooja_room: bool = False
    has_study_room: bool = False
    has_utility_room: bool = True
    has_veranda: bool = True
    has_foyer: bool = False
    balconies: int = Field(default=0, ge=0, le=12)

    cars: int = Field(default=1, ge=0, le=10)
    two_wheelers: int = Field(default=1, ge=0, le=10)

    floors: int = Field(default=1, ge=1, le=5)
    budget: float = Field(default=0, ge=0)

    vastu_compliant: bool = False
    wheelchair_accessible: bool = False
    additional_rooms: list[str] = Field(default_factory=list)
    other_requirements: str | None = None

    @field_validator("additional_rooms")
    @classmethod
    def validate_additional_rooms(cls, v: list[str]) -> list[str]:
        allowed = {"home_office", "servant_room", "store_room", "guest_room", "gym", "library"}
        for room in v:
            if room not in allowed:
                raise ValueError(f"Unsupported additional room type: {room}. Allowed: {sorted(allowed)}")
        return v


class RequirementCreate(RequirementBase):
    pass


class RequirementRead(RequirementBase, AuditRead):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
