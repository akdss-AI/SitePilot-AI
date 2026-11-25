"""SQLAlchemy models.

Importing this package registers every model on Base.metadata — main.py
and the tests rely on that to create tables. Add each new model module
here in the phase that introduces it.
"""
from app.models.inventory import Delivery, DeliveryStatus, Material, Supplier
from app.models.project import Project, ProjectStatus, Site, SiteStatus
from app.models.site_updates import (
    ALLOWED_ACTION_TYPES,
    SiteUpdate,
    SiteUpdateAction,
    SiteUpdateActionType,
    SiteUpdateStatus,
)
from app.models.tasks import (
    IssueCategory,
    IssuePriority,
    IssueStatus,
    SiteIssue,
    Task,
    TaskStatus,
)
from app.models.user import User

__all__ = [
    "User",
    "Project",
    "ProjectStatus",
    "Site",
    "SiteStatus",
    "Supplier",
    "Material",
    "Delivery",
    "DeliveryStatus",
    "Task",
    "TaskStatus",
    "SiteIssue",
    "IssueCategory",
    "IssuePriority",
    "IssueStatus",
    "SiteUpdate",
    "SiteUpdateStatus",
    "SiteUpdateAction",
    "SiteUpdateActionType",
    "ALLOWED_ACTION_TYPES",
]
