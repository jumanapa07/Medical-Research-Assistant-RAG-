
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    id: UUID
    title: str
    original_filename: str
    file_size: int
    status: str
    visibility: str
    version: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
