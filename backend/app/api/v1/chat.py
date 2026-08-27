from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.crud import floorplan as floorplan_crud
from app.crud import project as project_crud
from app.crud import requirement as requirement_crud
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_assistant import ChatAssistantError, ChatNotConfiguredError, get_chat_reply

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(payload: ChatRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    requirement = None
    floor_plan = None
    if payload.project_id is not None:
        project = project_crud.get_project(db, payload.project_id)
        if not project or project.owner_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your project")
        requirement = requirement_crud.get_latest_requirement(db, payload.project_id)
        floor_plan = floorplan_crud.get_latest_floor_plan(db, payload.project_id)

    try:
        reply = get_chat_reply(payload.messages, requirement, floor_plan)
    except ChatNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except ChatAssistantError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return ChatResponse(reply=reply)
