"""Task and SiteIssue schemas — Phase 4 validation boundary.

Enum fields reject anything outside the fixed sets with a 422 before
any service or database code runs. TaskCreate has no reported_by-style
server-set field to smuggle in; SiteIssueCreate has no reported_by
field at all — the service sets it from the authenticated user.
"""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.tasks import (
    IssueCategory,
    IssuePriority,
    IssueStatus,
    TaskStatus,
)


def _clean_title(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("title must not be blank")
    return v


# ---- Tasks ---------------------------------------------------------------

class TaskCreate(BaseModel):
    project_id: int
    site_id: int | None = None
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    status: TaskStatus = TaskStatus.TODO
    due_date: date | None = None
    assigned_to: int | None = None

    _title = field_validator("title")(_clean_title)


class TaskUpdate(BaseModel):
    """All fields optional — PATCH only changes what is sent.
    Sending an explicit null clears site_id / due_date / assigned_to.
    project_id is deliberately absent: a task never moves projects."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: TaskStatus | None = None
    due_date: date | None = None
    assigned_to: int | None = None
    site_id: int | None = None

    @field_validator("title")
    @classmethod
    def clean_title(cls, v):
        return _clean_title(v) if v is not None else v


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    site_id: int | None
    assigned_to: int | None
    title: str
    description: str | None
    status: TaskStatus
    due_date: date | None
    # Computed, not stored — read from the model property of the same name.
    is_overdue: bool
    overdue: bool
    created_at: datetime
    updated_at: datetime


# ---- Site issues -----------------------------------------------------------

class IssueCreate(BaseModel):
    site_id: int
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    category: IssueCategory
    priority: IssuePriority = IssuePriority.MEDIUM
    status: IssueStatus = IssueStatus.OPEN

    _title = field_validator("title")(_clean_title)


class IssueUpdate(BaseModel):
    """All fields optional — PATCH only changes what is sent."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    category: IssueCategory | None = None
    priority: IssuePriority | None = None
    status: IssueStatus | None = None

    @field_validator("title")
    @classmethod
    def clean_title(cls, v):
        return _clean_title(v) if v is not None else v


class IssueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    site_id: int
    reported_by: int
    title: str
    description: str | None
    category: IssueCategory
    priority: IssuePriority
    status: IssueStatus
    created_at: datetime
    updated_at: datetime
