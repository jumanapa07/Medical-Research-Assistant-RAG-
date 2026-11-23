
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class MessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    role: str
    content: str
    citations: list[dict[str, Any]] | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
