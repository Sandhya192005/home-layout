from sqlalchemy import String, ForeignKey, Float, Integer, Boolean, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import AuditMixin


class Requirement(Base, AuditMixin):
    __tablename__ = "requirements"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)

    # Plot
    plot_length: Mapped[float] = mapped_column(Float, nullable=False)  # north-south depth, feet
    plot_width: Mapped[float] = mapped_column(Float, nullable=False)  # east-west frontage, feet
    facing: Mapped[str] = mapped_column(String(20), default="north")  # north, south, east, west

    # Household
    family_members: Mapped[int] = mapped_column(Integer, default=4)
    bedrooms: Mapped[int] = mapped_column(Integer, default=2)
    bathrooms: Mapped[int] = mapped_column(Integer, default=2)

    # Rooms
    has_living_room: Mapped[bool] = mapped_column(Boolean, default=True)
    has_dining_room: Mapped[bool] = mapped_column(Boolean, default=True)
    has_pooja_room: Mapped[bool] = mapped_column(Boolean, default=False)
    has_study_room: Mapped[bool] = mapped_column(Boolean, default=False)
    has_utility_room: Mapped[bool] = mapped_column(Boolean, default=True)
    balconies: Mapped[int] = mapped_column(Integer, default=0)

    # Parking
    cars: Mapped[int] = mapped_column(Integer, default=1)
    two_wheelers: Mapped[int] = mapped_column(Integer, default=1)

    # Structure
    floors: Mapped[int] = mapped_column(Integer, default=1)
    budget: Mapped[float] = mapped_column(Float, default=0)  # in currency units (e.g. INR)

    # Preferences
    vastu_compliant: Mapped[bool] = mapped_column(Boolean, default=False)
    wheelchair_accessible: Mapped[bool] = mapped_column(Boolean, default=False)
    additional_rooms: Mapped[list] = mapped_column(JSON, default=list)  # e.g. ["home_office", "servant_room"]
    other_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped["Project"] = relationship(back_populates="requirements")
    floor_plans: Mapped[list["FloorPlan"]] = relationship(back_populates="requirement")
