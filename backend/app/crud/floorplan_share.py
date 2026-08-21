import secrets
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.floorplan_share import FloorPlanShare


def get_active_share(db: Session, floor_plan_id: int) -> FloorPlanShare | None:
    return (
        db.query(FloorPlanShare)
        .filter(FloorPlanShare.floor_plan_id == floor_plan_id, FloorPlanShare.deleted_at.is_(None))
        .order_by(FloorPlanShare.id.desc())
        .first()
    )


def create_share(db: Session, floor_plan_id: int, actor_id: int) -> FloorPlanShare:
    existing = get_active_share(db, floor_plan_id)
    if existing:
        return existing
    share = FloorPlanShare(
        floor_plan_id=floor_plan_id,
        token=secrets.token_urlsafe(24),
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(share)
    db.commit()
    db.refresh(share)
    return share


def revoke_share(db: Session, share: FloorPlanShare, actor_id: int) -> None:
    share.deleted_at = datetime.now(timezone.utc)
    share.deleted_by = actor_id
    share.is_active = False
    db.commit()


def get_by_token(db: Session, token: str) -> FloorPlanShare | None:
    return (
        db.query(FloorPlanShare)
        .filter(FloorPlanShare.token == token, FloorPlanShare.deleted_at.is_(None))
        .first()
    )
