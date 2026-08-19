from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import AuditMixin


class Project(Base, AuditMixin):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="draft")  # draft, generated, finalized

    owner: Mapped["User"] = relationship(back_populates="projects", foreign_keys=[owner_id])
    requirements: Mapped[list["Requirement"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Requirement.created_at.desc()"
    )
    floor_plans: Mapped[list["FloorPlan"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="FloorPlan.version.desc()"
    )
