from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.mixins import AuditRead


class AISuggestionRead(AuditRead):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    requirement_id: int
    suggestions: list[dict[str, Any]]
