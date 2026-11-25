"""Task and SiteIssue models — Phase 4.

Relationships
-------------
Task       belongs to one Project (required) and optionally one Site.
           assigned_to is a nullable reference to a User id: a display /
           follow-up reference only — it grants no access and is not a
           permission or a notification target. Ownership is still
           project-owner only, checked through Task.project_id.
SiteIssue  belongs to one Site only (no project link, decided Phase 4):
           its project — and therefore its owner — is reached through
           the site. reported_by is set server-side from the
           authenticated user, never from a request payload.

Overdue rule (in exactly one place, Task.is_overdue):
    due_date is set AND due_date < today AND status != done.
A task with no due date can never be overdue; a task due today is NOT
overdue. is_overdue is computed, never a stored column.
"""
import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TaskStatus(str, enum.Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class IssueCategory(str, enum.Enum):
    SAFETY = "safety"
    QUALITY = "quality"
    MATERIAL = "material"
    LABOUR = "labour"
    WEATHER = "weather"
    EQUIPMENT = "equipment"
    OTHER = "other"


class IssuePriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IssueStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # If a site is deleted, its tasks survive at project level with
    # site_id cleared (SET NULL) — the work itself is not lost.
    site_id: Mapped[int | None] = mapped_column(
        ForeignKey("sites.id", ondelete="SET NULL"), index=True
    )
    # Display/follow-up reference only — see module docstring.
    assigned_to: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status"),
        default=TaskStatus.TODO,
        nullable=False,
    )
    due_date: Mapped[date | None] = mapped_column(Date)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    project: Mapped["Project"] = relationship(back_populates="tasks")  # noqa: F821
    site: Mapped["Site | None"] = relationship(back_populates="tasks")  # noqa: F821
    assignee: Mapped["User | None"] = relationship()  # noqa: F821

    @property
    def is_overdue(self) -> bool:
        """The overdue rule, in exactly one place (see module docstring)."""
        return (
            self.due_date is not None
            and self.due_date < date.today()
            and self.status != TaskStatus.DONE
        )

    @property
    def overdue(self) -> bool:
        """Alias of is_overdue, so API responses can expose both names."""
        return self.is_overdue


class SiteIssue(Base):
    __tablename__ = "site_issues"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Issues attach to a site only; deleting the site removes its issues.
    site_id: Mapped[int] = mapped_column(
        ForeignKey("sites.id", ondelete="CASCADE"), index=True, nullable=False
    )
    reported_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[IssueCategory] = mapped_column(
        Enum(IssueCategory, name="issue_category"), nullable=False
    )
    priority: Mapped[IssuePriority] = mapped_column(
        Enum(IssuePriority, name="issue_priority"),
        default=IssuePriority.MEDIUM,
        nullable=False,
    )
    status: Mapped[IssueStatus] = mapped_column(
        Enum(IssueStatus, name="issue_status"),
        default=IssueStatus.OPEN,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    site: Mapped["Site"] = relationship(back_populates="issues")  # noqa: F821
    reporter: Mapped["User"] = relationship()  # noqa: F821
