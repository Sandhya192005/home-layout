from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import generate_refresh_token, hash_refresh_token
from app.models.refresh_token import RefreshToken


def create_refresh_token(db: Session, user_id: int) -> tuple[str, RefreshToken]:
    raw_token = generate_refresh_token()
    row = RefreshToken(
        user_id=user_id,
        token_hash=hash_refresh_token(raw_token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return raw_token, row


def get_valid_refresh_token(db: Session, raw_token: str) -> RefreshToken | None:
    row = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == hash_refresh_token(raw_token), RefreshToken.deleted_at.is_(None))
        .first()
    )
    if not row:
        return None
    # SQLite (used in tests) doesn't preserve tzinfo on round-trip and always
    # comes back naive, even though we only ever write UTC-aware values --
    # Postgres returns aware datetimes here, so normalize before comparing.
    expires_at = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        return None
    return row


def revoke_refresh_token(db: Session, row: RefreshToken) -> None:
    row.deleted_at = datetime.now(timezone.utc)
    row.deleted_by = row.user_id
    row.is_active = False
    db.commit()
