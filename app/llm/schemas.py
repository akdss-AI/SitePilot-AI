"""Pydantic schemas for the LLM's structured output — Phase 5.

These are NOT API schemas: they validate what Groq returns, before
anything is applied. Strictness policy (documented, deliberate):
  * Known fields are validated strictly — wrong types, non-positive
    quantities, invalid enum values, blank titles, bad dates all fail
    validation, and a failed validation means the whole update fails
    with zero business writes (see site_update_service).
  * Unknown fields inside an action or at the top level are IGNORED
    (extra="ignore"), not rejected: Groq models routinely add harmless
    extra keys, and rejecting the whole update for one would make the
    feature brittle. Nothing unknown is ever applied — only the
    validated known fields reach the executor.
  * An UNKNOWN action_type is NOT ignored: the discriminated union
    below has no matching variant, so validation fails and the whole
    update is rejected and reported. That is the allow-list enforced
    at the parse boundary, before the executor's own check.

Quantities are Decimal (never float), dates are date objects, and
every referenced id is a plain int — the executor then checks each id
against the caller's owned records; an id that does not exist (or
belongs to someone else) is rejected there, never trusted here.
"""
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.site_updates import SiteUpdateActionType
from app.models.tasks import IssueCategory, IssuePriority, TaskStatus


class _LLMBase(BaseModel):
    # Unknown keys from the model are ignored (see module docstring);
    # only validated known fields are ever used downstream.
    model_config = ConfigDict(extra="ignore")


def _clean_text(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("must not be blank")
    return v


class RecordDeliveryAction(_LLMBase):
    action_type: Literal[SiteUpdateActionType.RECORD_DELIVERY]
    material_id: int
    supplier_id: int
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None


class CreateIssueAction(_LLMBase):
    action_type: Literal[SiteUpdateActionType.CREATE_ISSUE]
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    category: IssueCategory
    priority: IssuePriority = IssuePriority.MEDIUM

    _title = field_validator("title")(_clean_text)


class CreateTaskAction(_LLMBase):
    action_type: Literal[SiteUpdateActionType.CREATE_TASK]
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    due_date: date | None = None

    _title = field_validator("title")(_clean_text)


class UpdateTaskStatusAction(_LLMBase):
    action_type: Literal[SiteUpdateActionType.UPDATE_TASK_STATUS]
    task_id: int
    status: TaskStatus


class UpdateTaskDueDateAction(_LLMBase):
    action_type: Literal[SiteUpdateActionType.UPDATE_TASK_DUE_DATE]
    task_id: int
    due_date: date


# Discriminated union on action_type: an unknown type matches no
# variant, so the whole LLM output fails validation (see docstring).
LLMAction = Annotated[
    Union[
        RecordDeliveryAction,
        CreateIssueAction,
        CreateTaskAction,
        UpdateTaskStatusAction,
        UpdateTaskDueDateAction,
    ],
    Field(discriminator="action_type"),
]


class LLMParsedUpdate(_LLMBase):
    """The whole structured response from Groq for one site update."""

    summary: str = ""
    actions: list[LLMAction] = Field(default_factory=list)

    @field_validator("summary")
    @classmethod
    def clean_summary(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v

    def payloads(self) -> list[dict]:
        """Each action as a JSON-serialisable dict (for the audit rows).

        Decimals become strings and dates become ISO strings, matching
        how the API serialises them elsewhere in the app — never floats,
        so stock/money values stay exact.
        """
        from datetime import date as _date
        from decimal import Decimal as _Decimal
        from enum import Enum as _Enum

        def _serialise(value):
            if isinstance(value, _Decimal):
                return str(value)
            if isinstance(value, _date):
                return value.isoformat()
            if isinstance(value, _Enum):
                return value.value
            if isinstance(value, dict):
                return {k: _serialise(v) for k, v in value.items()}
            if isinstance(value, (list, tuple)):
                return [_serialise(v) for v in value]
            return value

        return [_serialise(a.model_dump()) for a in self.actions]
