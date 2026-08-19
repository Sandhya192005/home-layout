from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.projects import _get_owned_project
from app.core.database import get_db
from app.crud import floorplan as floorplan_crud
from app.models.user import User
from app.schemas.suggestion import AISuggestionRead

router = APIRouter(prefix="/projects/{project_id}/suggestions", tags=["suggestions"])


@router.get("/latest", response_model=AISuggestionRead)
def get_latest_suggestions(
    project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    _get_owned_project(db, project_id, current_user)
    suggestion = floorplan_crud.get_latest_suggestion(db, project_id)
    if not suggestion:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No suggestions generated yet")
    return suggestion
