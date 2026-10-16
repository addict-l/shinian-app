from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
import re


class AccountCredentials(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=1, max_length=32)
    password: SecretStr

    @field_validator('username')
    @classmethod
    def normalize_username(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r'[a-z0-9_]{3,32}', value):
            raise ValueError('账号须为 3–32 位字母、数字或下划线')
        return value


class AccountIdentity(BaseModel):
    account_id: UUID
    family_id: UUID
    username: str
    legacy: bool = False


class LoginResponse(AccountIdentity):
    token: str
    token_type: str = 'Bearer'
    expires_at: datetime
