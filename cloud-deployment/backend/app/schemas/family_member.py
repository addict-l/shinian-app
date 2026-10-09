from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class FamilyMemberCreate(BaseModel):
    client_request_id: UUID | None = None

    family_id: UUID

    name: str = Field(min_length=1, max_length=100)

    relationship: str = Field(min_length=1, max_length=50)

    birth_date: date | None = None

    @field_validator('name', 'relationship')
    @classmethod
    def strip_text(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('姓名和家庭身份不能为空')
        return value

    @field_validator('birth_date')
    @classmethod
    def validate_birthday(cls, value):
        if value and value > date.today():
            raise ValueError('生日不能在未来')
        return value


class FamilyMember(BaseModel):
    family_id: UUID

    id: UUID

    name: str = Field(min_length=1, max_length=100)

    relationship: str = Field(min_length=1, max_length=50)

    birth_date: date | None

    created_at: datetime