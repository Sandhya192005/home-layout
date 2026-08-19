from sqlalchemy.orm import Session

from app.models.requirement import Requirement
from app.schemas.requirement import RequirementCreate


def create_requirement(db: Session, project_id: int, req_in: RequirementCreate, actor_id: int) -> Requirement:
    requirement = Requirement(
        project_id=project_id, **req_in.model_dump(), created_by=actor_id, updated_by=actor_id
    )
    db.add(requirement)
    db.commit()
    db.refresh(requirement)
    return requirement


def get_requirement(db: Session, requirement_id: int) -> Requirement | None:
    return (
        db.query(Requirement)
        .filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None))
        .first()
    )


def get_latest_requirement(db: Session, project_id: int) -> Requirement | None:
    return (
        db.query(Requirement)
        .filter(Requirement.project_id == project_id, Requirement.deleted_at.is_(None))
        .order_by(Requirement.created_at.desc())
        .first()
    )


def list_requirements(db: Session, project_id: int) -> list[Requirement]:
    return (
        db.query(Requirement)
        .filter(Requirement.project_id == project_id, Requirement.deleted_at.is_(None))
        .order_by(Requirement.created_at.desc())
        .all()
    )
