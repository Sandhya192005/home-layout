from datetime import datetime

from pydantic import BaseModel


class AuditRead(BaseModel):
    created_at: datetime
    created_by: int | None = None
    updated_at: datetime
    updated_by: int | None = None
    deleted_at: datetime | None = None
    deleted_by: int | None = None
    is_active: bool
