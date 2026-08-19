from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


class AuditMixin:
    """created/updated/deleted actor+timestamp columns, plus is_active, shared
    by every table. deleted_at/deleted_by drive soft delete: rows are never
    physically removed, only flagged, and read queries filter them out."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)

    @declared_attr
    def created_by(cls) -> Mapped[int | None]:
        return mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    @declared_attr
    def updated_by(cls) -> Mapped[int | None]:
        return mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    @declared_attr
    def deleted_by(cls) -> Mapped[int | None]:
        return mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
