from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=20)
    # When set, the assistant is given a short summary of that project's
    # latest requirement/floor plan as extra context (so "why is my kitchen
    # small?" works), in addition to answering general house-building questions.
    project_id: int | None = None


class ChatResponse(BaseModel):
    reply: str
