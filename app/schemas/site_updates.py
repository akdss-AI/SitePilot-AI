"""Site-update API schemas — Phase 5 validation boundary.

SiteUpdateCreate is the only client input: a site id and raw text.
Everything else (actions, summary, status) comes from the LLM and
the executor, never from the client.
"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.site_updates import SiteUpdateActionType, SiteUpdateStatus


class SiteUpdateCreate(BaseModel):
    site_id: int
    raw_text: str = Field(min_length=1, max_length=5000)

    @field_validator("raw_text")
    @classmethod
    def clean_raw_text(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("raw_text must not be blank")
        return v


class SiteUpdateActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    site_update_id: int
    action_type: SiteUpdateActionType
    payload: dict[str, Any]
    applied: bool
    rejection_reason: str | None
    created_at: datetime


class SiteUpdateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    site_id: int
    submitted_by: int
    raw_text: str
    status: SiteUpdateStatus
    summary: str | None
    failure_reason: str | None
    created_at: datetime
    # The per-action audit trail: what was understood, what changed,
    # and what was rejected and why. Loaded by the GET endpoints.
    actions: list[SiteUpdateActionOut] = []
