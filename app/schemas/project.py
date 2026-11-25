"""Project and Site schemas — the validation boundary for those resources.

Anything invalid (blank names, an end date before the start date, a status
outside the enum) is rejected here by Pydantic with a 422 before any
service or database code runs.
"""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.project import ProjectStatus, SiteStatus


def _clean_name(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("name must not be blank")
    return v


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    client_name: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    description: str | None = None
    status: ProjectStatus = ProjectStatus.ACTIVE
    start_date: date | None = None
    end_date: date | None = None

    _name = field_validator("name")(_clean_name)

    @model_validator(mode="after")
    def check_dates(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        return self


class ProjectUpdate(BaseModel):
    """All fields optional — PATCH only changes what is sent."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    client_name: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    description: str | None = None
    status: ProjectStatus | None = None
    start_date: date | None = None
    end_date: date | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, v):
        return _clean_name(v) if v is not None else v

    @model_validator(mode="after")
    def check_dates(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        return self


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    name: str
    client_name: str | None
    location: str | None
    description: str | None
    status: ProjectStatus
    start_date: date | None
    end_date: date | None
    created_at: datetime
    updated_at: datetime


class SiteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    notes: str | None = None
    status: SiteStatus = SiteStatus.ACTIVE

    _name = field_validator("name")(_clean_name)


class SiteUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    notes: str | None = None
    status: SiteStatus | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, v):
        return _clean_name(v) if v is not None else v


class SiteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    location: str | None
    notes: str | None
    status: SiteStatus
    created_at: datetime
    updated_at: datetime
