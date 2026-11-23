
from pydantic import BaseModel, Field
from typing import Any
from uuid import UUID


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=10000)


class ChatResponse(BaseModel):
    conversation_id: UUID
    user_message_id: UUID
    assistant_message_id: UUID
    answer: str
    citations: list[dict[str, Any]]


class ConversationCreate(BaseModel):
    title: str = Field(
        default="New conversation",
        min_length=1,
        max_length=255,
    )
