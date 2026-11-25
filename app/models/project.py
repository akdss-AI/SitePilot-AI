"""Project and Site models.

Project is the ownership boundary of the whole system: every protected
lookup filters on Project.owner_id == current_user.id.

Site belongs to exactly one project. Later phases attach materials,
tasks, issues and site updates to sites.
"""
import enum
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ProjectStatus(str, enum.Enum):
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class SiteStatus(str, enum.Enum):
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"


class Project(Base):
    __tablename__ = "projects"
    # One owner cannot have two projects with the same name.
    # Different owners may reuse a name — the constraint includes owner_id.
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_project_owner_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    client_name: Mapped[str | None] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, name="project_status"),
        default=ProjectStatus.ACTIVE,
        nullable=False,
    )
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    owner: Mapped["User"] = relationship(back_populates="projects")  # noqa: F821
    sites: Mapped[list["Site"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    # Phase 4: tasks attach at project level (site optional).
    tasks: Mapped[list["Task"]] = relationship(  # noqa: F821
        back_populates="project", cascade="all, delete-orphan"
    )


class Site(Base):
    __tablename__ = "sites"
    # Site names are unique within their project, not globally.
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_site_project_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    location: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[SiteStatus] = mapped_column(
        Enum(SiteStatus, name="site_status"),
        default=SiteStatus.ACTIVE,
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

    project: Mapped["Project"] = relationship(back_populates="sites")
    # Phase 3: materials tracked at this site.
    materials: Mapped[list["Material"]] = relationship(  # noqa: F821
        back_populates="site", cascade="all, delete-orphan"
    )
    # Phase 4: tasks optionally attached to this site; issues always are.
    tasks: Mapped[list["Task"]] = relationship(  # noqa: F821
        back_populates="site"
    )
    issues: Mapped[list["SiteIssue"]] = relationship(  # noqa: F821
        back_populates="site", cascade="all, delete-orphan"
    )
    # Phase 5: natural-language updates submitted for this site.
    site_updates: Mapped[list["SiteUpdate"]] = relationship(  # noqa: F821
        back_populates="site", cascade="all, delete-orphan"
    )
