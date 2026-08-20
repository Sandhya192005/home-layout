from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.floorplan import FloorPlan
from app.models.project import Project
from app.models.requirement import Requirement
from app.schemas.project import ProjectCreate, ProjectUpdate


def create_project(db: Session, owner_id: int, project_in: ProjectCreate) -> Project:
    project = Project(
        owner_id=owner_id,
        name=project_in.name,
        description=project_in.description,
        created_by=owner_id,
        updated_by=owner_id,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def get_project(db: Session, project_id: int) -> Project | None:
    return db.query(Project).filter(Project.id == project_id, Project.deleted_at.is_(None)).first()


def list_projects(db: Session, owner_id: int) -> list[Project]:
    return (
        db.query(Project)
        .filter(Project.owner_id == owner_id, Project.deleted_at.is_(None))
        .order_by(Project.created_at.desc())
        .all()
    )


def update_project(db: Session, project: Project, project_in: ProjectUpdate, actor_id: int) -> Project:
    data = project_in.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(project, field, value)
    project.updated_by = actor_id
    db.commit()
    db.refresh(project)
    return project


def delete_project(db: Session, project: Project, actor_id: int) -> None:
    """Soft delete: flag the project and cascade the same flag onto its
    requirements/floor plans, since a soft delete doesn't get the database's
    ON DELETE CASCADE for free the way a real delete did."""
    now = datetime.now(timezone.utc)
    project.deleted_at = now
    project.deleted_by = actor_id
    project.is_active = False

    db.query(Requirement).filter(Requirement.project_id == project.id, Requirement.deleted_at.is_(None)).update(
        {"deleted_at": now, "deleted_by": actor_id, "is_active": False}, synchronize_session=False
    )
    db.query(FloorPlan).filter(FloorPlan.project_id == project.id, FloorPlan.deleted_at.is_(None)).update(
        {"deleted_at": now, "deleted_by": actor_id, "is_active": False}, synchronize_session=False
    )
    db.commit()
