"""Task & SiteIssue business logic — Phase 4. No HTTP code here.

Ownership (same rule as Phases 2–3, extended through the chain):
- Task:      task.project.owner_id == current user
- SiteIssue: issue.site.project.owner_id == current user
Anything outside that chain is "not found" (404) — including when a user
references another user's project/site while creating a record.

Scope rules that are 422, not 404 (the record exists and belongs to the
caller, but the requested combination is invalid):
- a task's site_id must belong to the task's project;
- assigned_to must reference an existing user id (it grants that user
  NO access — ownership is still project-owner only).
A site that does not exist, or belongs to someone else, is a 404 via
get_owned_site / get_owned_project, exactly as in earlier phases.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.project import Project, Site
from app.models.tasks import (
    IssueCategory,
    IssuePriority,
    IssueStatus,
    SiteIssue,
    Task,
    TaskStatus,
)
from app.models.user import User
from app.schemas.tasks import IssueCreate, IssueUpdate, TaskCreate, TaskUpdate
from app.services.project_service import get_owned_project, get_owned_site


def _validate_assigned_to(db: Session, assigned_to: int | None) -> None:
    """assigned_to, if given, must be an existing user id — else 422."""
    if assigned_to is not None and db.get(User, assigned_to) is None:
        raise AppError("Assigned user not found.", 422)


def _validate_task_site(db: Session, owner: User, project_id: int, site_id: int | None) -> None:
    """A task's site, if given, must exist, belong to the caller, and
    belong to the task's project — the last part is a 422."""
    if site_id is None:
        return
    site = get_owned_site(db, owner, site_id)  # 404: missing / foreign site
    if site.project_id != project_id:
        raise AppError("Site does not belong to this project.", 422)


# ---- Tasks ---------------------------------------------------------------

def create_task(db: Session, owner: User, data: TaskCreate) -> Task:
    get_owned_project(db, owner, data.project_id)  # 404: bad/foreign project
    _validate_task_site(db, owner, data.project_id, data.site_id)
    _validate_assigned_to(db, data.assigned_to)
    task = Task(**data.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def list_tasks(
    db: Session,
    owner: User,
    project_id: int | None = None,
    site_id: int | None = None,
    status: TaskStatus | None = None,
) -> list[Task]:
    query = (
        select(Task)
        .join(Project, Task.project_id == Project.id)
        .where(Project.owner_id == owner.id)
        .order_by(Task.id)
    )
    if project_id is not None:
        get_owned_project(db, owner, project_id)  # filtering by a foreign project is 404
        query = query.where(Task.project_id == project_id)
    if site_id is not None:
        get_owned_site(db, owner, site_id)  # filtering by a foreign site is 404
        query = query.where(Task.site_id == site_id)
    if status is not None:
        query = query.where(Task.status == status)
    return list(db.scalars(query))


def list_overdue_tasks(db: Session, owner: User) -> list[Task]:
    """Only the caller's overdue tasks. Filtered in Python through the
    model's is_overdue property so the endpoint and the response field
    can never disagree about the rule."""
    return [t for t in list_tasks(db, owner) if t.is_overdue]


def get_owned_task(db: Session, owner: User, task_id: int) -> Task:
    task = db.scalar(
        select(Task)
        .join(Project, Task.project_id == Project.id)
        .where(Task.id == task_id, Project.owner_id == owner.id)
    )
    if task is None:
        raise AppError("Task not found.", 404)
    return task


def update_task(
    db: Session, owner: User, task_id: int, data: TaskUpdate
) -> Task:
    task = get_owned_task(db, owner, task_id)
    changes = data.model_dump(exclude_unset=True)
    if "site_id" in changes:
        _validate_task_site(db, owner, task.project_id, changes["site_id"])
    if "assigned_to" in changes:
        _validate_assigned_to(db, changes["assigned_to"])
    for field, value in changes.items():
        setattr(task, field, value)
    db.commit()
    db.refresh(task)
    return task


# ---- Site issues -----------------------------------------------------------

def create_issue(db: Session, owner: User, data: IssueCreate) -> SiteIssue:
    # Site must exist and belong to the caller — a foreign site is a 404.
    get_owned_site(db, owner, data.site_id)
    # reported_by is set here, server-side, from the authenticated user.
    # IssueCreate carries no reported_by field, so a client cannot spoof it.
    issue = SiteIssue(reported_by=owner.id, **data.model_dump())
    db.add(issue)
    db.commit()
    db.refresh(issue)
    return issue


def list_issues(
    db: Session,
    owner: User,
    site_id: int | None = None,
    category: IssueCategory | None = None,
    priority: IssuePriority | None = None,
    status: IssueStatus | None = None,
) -> list[SiteIssue]:
    query = (
        select(SiteIssue)
        .join(Site, SiteIssue.site_id == Site.id)
        .join(Project, Site.project_id == Project.id)
        .where(Project.owner_id == owner.id)
        .order_by(SiteIssue.id)
    )
    if site_id is not None:
        get_owned_site(db, owner, site_id)  # filtering by a foreign site is 404
        query = query.where(SiteIssue.site_id == site_id)
    if category is not None:
        query = query.where(SiteIssue.category == category)
    if priority is not None:
        query = query.where(SiteIssue.priority == priority)
    if status is not None:
        query = query.where(SiteIssue.status == status)
    return list(db.scalars(query))


def get_owned_issue(db: Session, owner: User, issue_id: int) -> SiteIssue:
    issue = db.scalar(
        select(SiteIssue)
        .join(Site, SiteIssue.site_id == Site.id)
        .join(Project, Site.project_id == Project.id)
        .where(SiteIssue.id == issue_id, Project.owner_id == owner.id)
    )
    if issue is None:
        raise AppError("Issue not found.", 404)
    return issue


def update_issue(
    db: Session, owner: User, issue_id: int, data: IssueUpdate
) -> SiteIssue:
    issue = get_owned_issue(db, owner, issue_id)
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(issue, field, value)
    db.commit()
    db.refresh(issue)
    return issue
