"""SiteUpdate and SiteUpdateAction models — Phase 5.

SiteUpdate is the audit record of one natural-language submission:
the manager's raw text, who submitted it, and whether it was
processed or failed. SiteUpdateAction is one row per action the LLM
proposed for that update: its allow-listed type, the validated payload
(as JSON), whether it was applied, and — when it was not — why.

Failed-attempt recording (decided Phase 5, recorded in ARCHITECTURE.md):
the SiteUpdate row itself IS always saved, even when processing fails —
it is the audit of the attempt, not a business change. What is never
saved on failure is any business change: no delivery, no stock change,
no task/issue change, and no action row marked applied.
  * Groq unreachable / LLM output unparseable: SiteUpdate saved with
    status=failed and failure_reason set; zero SiteUpdateAction rows
    (no actions were ever parsed).
  * One or more proposed actions invalid: SiteUpdate saved with
    status=failed and failure_reason set; one SiteUpdateAction row per
    proposed action, ALL with applied=False and a rejection_reason —
    the valid-looking ones included, because nothing was applied.
  * Success: SiteUpdate processed; one row per action, all applied=True.

Ownership: an update belongs to a site, and through the site to a
project and its owner (update.site.project.owner_id). Actions belong
to their update; deleting a site removes its updates and actions.
"""
import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SiteUpdateStatus(str, enum.Enum):
    PROCESSED = "processed"
    FAILED = "failed"


class SiteUpdateActionType(str, enum.Enum):
    RECORD_DELIVERY = "record_delivery"
    CREATE_ISSUE = "create_issue"
    CREATE_TASK = "create_task"
    UPDATE_TASK_STATUS = "update_task_status"
    UPDATE_TASK_DUE_DATE = "update_task_due_date"


# The allow-list, in one place. The executor and the LLM schemas both
# derive from this enum — an action type outside it can never be applied.
ALLOWED_ACTION_TYPES = frozenset(t.value for t in SiteUpdateActionType)


class SiteUpdate(Base):
    __tablename__ = "site_updates"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(
        ForeignKey("sites.id", ondelete="CASCADE"), index=True, nullable=False
    )
    submitted_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[SiteUpdateStatus] = mapped_column(
        Enum(SiteUpdateStatus, name="site_update_status"),
        default=SiteUpdateStatus.FAILED,
        nullable=False,
    )
    # One-sentence human-readable summary of what the LLM understood
    # (from the LLM output on success; None when parsing failed).
    summary: Mapped[str | None] = mapped_column(Text)
    # Human-readable reason processing failed; None on success.
    failure_reason: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    site: Mapped["Site"] = relationship(back_populates="site_updates")  # noqa: F821
    submitter: Mapped["User"] = relationship()  # noqa: F821
    actions: Mapped[list["SiteUpdateAction"]] = relationship(
        back_populates="site_update", cascade="all, delete-orphan"
    )


class SiteUpdateAction(Base):
    __tablename__ = "site_update_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_update_id: Mapped[int] = mapped_column(
        ForeignKey("site_updates.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    action_type: Mapped[SiteUpdateActionType] = mapped_column(
        Enum(SiteUpdateActionType, name="site_update_action_type"),
        nullable=False,
    )
    # The validated payload, JSON-serialised (Decimals/dates as strings).
    # For a rejected action this is the payload as proposed, so the
    # audit trail shows exactly what was rejected and why.
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Human-readable reason this action was not applied; None when applied.
    rejection_reason: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    site_update: Mapped["SiteUpdate"] = relationship(back_populates="actions")
