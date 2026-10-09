"""Collected facts, distinct from information not yet asked about."""
from enum import Enum
from uuid import UUID
from pydantic import BaseModel, Field, model_validator


class InformationStatus(str, Enum):
    missing = 'missing'
    known = 'known'
    approximate = 'approximate'
    unknown = 'unknown'
    withheld = 'withheld'


class InformationDimension(BaseModel):
    status: InformationStatus = InformationStatus.missing
    value: str | None = Field(default=None, max_length=2000)
    source_message_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode='after')
    def coherent(self):
        if self.status == InformationStatus.missing:
            if self.value is not None or self.source_message_ids:
                raise ValueError('未采集的信息不能包含值或原文依据')
        elif not self.value or not self.value.strip():
            raise ValueError('已采集信息必须保留可读说明，包括模糊或未知的表达')
        return self


class StoryInformation(BaseModel):
    people: InformationDimension = Field(default_factory=InformationDimension)
    event: InformationDimension = Field(default_factory=InformationDimension)
    time: InformationDimension = Field(default_factory=InformationDimension)
    place: InformationDimension = Field(default_factory=InformationDimension)
    feeling: InformationDimension = Field(default_factory=InformationDimension)
    detail: InformationDimension = Field(default_factory=InformationDimension)
