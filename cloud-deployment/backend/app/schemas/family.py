from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class FamilyCreate(BaseModel):

    name: str = Field(
        min_length=1,
        max_length=100,
    )


class Family(BaseModel):

    id: UUID

    name: str

    created_at: datetime

    updated_at: datetime