"""Daily summary — Phase 6. No HTTP code here, no stored rows.

The summary is GENERATED ON READ from live tasks / materials / issues /
deliveries / site updates, so it can never drift out of sync with the
real data. There is deliberately no summary table.

Ownership is never re-implemented here: every list comes from the
existing ownership-scoped service getters (list_tasks,
list_stock_alerts / list_materials, list_issues, list_deliveries), and
the project itself is resolved through get_owned_project, so another
user's project is a 404 before any data is read.

Definitions (same rules as the rest of the system):
- overdue:    due_date set AND due_date < today AND status != done
              (Task.is_overdue, the single source of truth).
- due today:  due_date == today AND status != done.
- upcoming:   due_date in (tomorrow .. today + 7 days) AND status != done.
- low stock:  quantity_on_hand <= reorder_level (Material.is_low_stock).
- open issue: status is open or in_progress (i.e. not resolved/closed).
              Listed critical first, then high, medium, low.
- pending delivery: status == pending.
- recent activity: the project's site updates, newest first (max 5).
"""
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.inventory import DeliveryStatus
from app.models.project import Project, Site
from app.models.site_updates import SiteUpdate
from app.models.tasks import IssuePriority, IssueStatus, TaskStatus
from app.models.user import User
from app.services import inventory_service, tasks_service
from app.services.project_service import get_owned_project, list_projects, list_sites

UPCOMING_DAYS = 7
RECENT_UPDATES_LIMIT = 5

_PRIORITY_ORDER = {
    IssuePriority.CRITICAL: 0,
    IssuePriority.HIGH: 1,
    IssuePriority.MEDIUM: 2,
    IssuePriority.LOW: 3,
}

_OPEN_ISSUE_STATUSES = (IssueStatus.OPEN, IssueStatus.IN_PROGRESS)


def _project_materials(db: Session, owner: User, project):
    """Materials belonging to this project, via its sites."""
    site_ids = {site.id for site in list_sites(db, owner, project.id)}
    return [m for m in inventory_service.list_materials(db, owner)
            if m.site_id in site_ids]


def _project_issues(db: Session, owner: User, project):
    site_ids = {site.id for site in list_sites(db, owner, project.id)}
    return [i for i in tasks_service.list_issues(db, owner)
            if i.site_id in site_ids]


def _project_deliveries(db: Session, owner: User, project):
    site_ids = {site.id for site in list_sites(db, owner, project.id)}
    materials = _project_materials(db, owner, project)
    material_ids = {m.id for m in materials}
    return [d for d in inventory_service.list_deliveries(db, owner)
            if d.material_id in material_ids]


def _project_recent_updates(db: Session, owner: User, project):
    """Newest site updates for this project's sites (max 5)."""
    site_ids = {site.id for site in list_sites(db, owner, project.id)}
    if not site_ids:
        return []
    query = (
        select(SiteUpdate)
        .join(Site, SiteUpdate.site_id == Site.id)
        .where(SiteUpdate.site_id.in_(site_ids))
        .order_by(SiteUpdate.created_at.desc(), SiteUpdate.id.desc())
        .limit(RECENT_UPDATES_LIMIT)
    )
    return list(db.scalars(query))


def build_project_summary(db: Session, owner: User, project_id: int,
                          upcoming_days: int = UPCOMING_DAYS) -> dict:
    """One project's daily summary, computed on read. 404 for a foreign
    or missing project (via get_owned_project)."""
    project = get_owned_project(db, owner, project_id)
    today = date.today()
    upcoming_end = today + timedelta(days=upcoming_days)

    tasks = tasks_service.list_tasks(db, owner, project_id=project_id)
    overdue = [t for t in tasks if t.is_overdue]
    due_today = [t for t in tasks
                 if t.due_date == today and t.status != TaskStatus.DONE]
    upcoming = sorted(
        (t for t in tasks
         if t.due_date is not None and today < t.due_date <= upcoming_end
         and t.status != TaskStatus.DONE),
        key=lambda t: (t.due_date, t.id),
    )

    low_stock = [m for m in _project_materials(db, owner, project)
                 if m.is_low_stock]
    issues = _project_issues(db, owner, project)
    open_issues = sorted(
        (i for i in issues if i.status in _OPEN_ISSUE_STATUSES),
        key=lambda i: (_PRIORITY_ORDER[i.priority], i.id),
    )
    critical_high = [i for i in open_issues
                     if i.priority in (IssuePriority.CRITICAL, IssuePriority.HIGH)]
    pending_deliveries = [d for d in _project_deliveries(db, owner, project)
                          if d.status == DeliveryStatus.PENDING]
    recent_updates = _project_recent_updates(db, owner, project)

    return {
        "project_id": project.id,
        "project_name": project.name,
        "date": today,
        "overdue_count": len(overdue),
        "overdue_tasks": overdue,
        "due_today_count": len(due_today),
        "due_today_tasks": due_today,
        "upcoming_count": len(upcoming),
        "upcoming_tasks": upcoming,
        "upcoming_days": upcoming_days,
        "low_stock_count": len(low_stock),
        "low_stock_materials": low_stock,
        "open_issues_count": len(open_issues),
        "open_issues": open_issues,
        "critical_high_issues_count": len(critical_high),
        "critical_high_issues": critical_high,
        "pending_deliveries_count": len(pending_deliveries),
        "pending_deliveries": pending_deliveries,
        "recent_updates_count": len(recent_updates),
        "recent_updates": recent_updates,
    }


def build_dashboard(db: Session, owner: User) -> dict:
    """The logged-in user's overview, aggregated across their projects
    using the same ownership-scoped getters as the per-project summary.
    Each project also gets its own summary (computed on read)."""
    projects = list_projects(db, owner)
    summaries = [build_project_summary(db, owner, p.id) for p in projects]
    overdue = tasks_service.list_overdue_tasks(db, owner)
    low_stock = inventory_service.list_stock_alerts(db, owner)
    open_issues = sorted(
        (i for i in tasks_service.list_issues(db, owner)
         if i.status in _OPEN_ISSUE_STATUSES),
        key=lambda i: (_PRIORITY_ORDER[i.priority], i.id),
    )
    critical_high = [i for i in open_issues
                     if i.priority in (IssuePriority.CRITICAL, IssuePriority.HIGH)]
    return {
        "projects": projects,
        "project_summaries": summaries,
        "overdue_count": len(overdue),
        "overdue_tasks": overdue,
        "low_stock_count": len(low_stock),
        "low_stock_materials": low_stock,
        "open_issues_count": len(open_issues),
        "open_issues": open_issues,
        "critical_high_issues_count": len(critical_high),
        "critical_high_issues": critical_high,
    }
