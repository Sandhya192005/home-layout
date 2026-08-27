from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import AuditMixin


class RefreshToken(Base, AuditMixin):
    """A rotating, revocable refresh token. Only a sha256 hash of the raw
    token is stored (mirrors password hashing, not FloorPlanShare's raw
    token, since this one is a bearer secret rather than a link meant to be
    shared); `deleted_at`/`is_active` from AuditMixin double as revocation."""

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
