from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import AuditMixin


class FloorPlanShare(Base, AuditMixin):
    """A public, read-only link token for one floor plan version. Revocation
    reuses the standard soft-delete columns from AuditMixin rather than a
    bespoke revoked_at column."""

    __tablename__ = "floor_plan_shares"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    floor_plan_id: Mapped[int] = mapped_column(ForeignKey("floor_plans.id", ondelete="CASCADE"), index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    floor_plan: Mapped["FloorPlan"] = relationship()
