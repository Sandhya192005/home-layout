from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.floorplan import FloorPlan


def get_next_version(db: Session, project_id: int) -> int:
    latest = (
        db.query(FloorPlan)
        .filter(FloorPlan.project_id == project_id)
        .order_by(FloorPlan.version.desc())
        .first()
    )
    return (latest.version + 1) if latest else 1


def create_floor_plan(
    db: Session,
    project_id: int,
    requirement_id: int,
    plan_data: dict,
    total_built_up_area: float,
    estimated_cost: float,
    actor_id: int,
) -> FloorPlan:
    floor_plan = FloorPlan(
        project_id=project_id,
        requirement_id=requirement_id,
        version=get_next_version(db, project_id),
        plan_data=plan_data,
        total_built_up_area=total_built_up_area,
        estimated_cost=estimated_cost,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(floor_plan)
    db.commit()
    db.refresh(floor_plan)
    return floor_plan


def get_floor_plan(db: Session, floor_plan_id: int) -> FloorPlan | None:
    return (
        db.query(FloorPlan)
        .filter(FloorPlan.id == floor_plan_id, FloorPlan.deleted_at.is_(None))
        .first()
    )


def list_floor_plans(db: Session, project_id: int) -> list[FloorPlan]:
    return (
        db.query(FloorPlan)
        .filter(FloorPlan.project_id == project_id, FloorPlan.deleted_at.is_(None))
        .order_by(FloorPlan.version.desc())
        .all()
    )


def get_latest_floor_plan(db: Session, project_id: int) -> FloorPlan | None:
    return (
        db.query(FloorPlan)
        .filter(FloorPlan.project_id == project_id, FloorPlan.deleted_at.is_(None))
        .order_by(FloorPlan.version.desc())
        .first()
    )


def delete_floor_plan(db: Session, floor_plan: FloorPlan, actor_id: int) -> None:
    floor_plan.deleted_at = datetime.now(timezone.utc)
    floor_plan.deleted_by = actor_id
    floor_plan.is_active = False
    db.commit()
