from sqlalchemy import Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import AuditMixin


class FloorPlan(Base, AuditMixin):
    __tablename__ = "floor_plans"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    requirement_id: Mapped[int] = mapped_column(ForeignKey("requirements.id", ondelete="CASCADE"), index=True)

    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(50), default="generated")  # generated, approved, archived

    plan_data: Mapped[dict] = mapped_column(JSON, nullable=False)  # structured floor plan for frontend rendering
    total_built_up_area: Mapped[float] = mapped_column(Float, default=0)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0)

    project: Mapped["Project"] = relationship(back_populates="floor_plans")
    requirement: Mapped["Requirement"] = relationship(back_populates="floor_plans")


class AISuggestion(Base, AuditMixin):
    __tablename__ = "ai_suggestions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    requirement_id: Mapped[int] = mapped_column(ForeignKey("requirements.id", ondelete="CASCADE"), index=True)

    suggestions: Mapped[list] = mapped_column(JSON, nullable=False)
