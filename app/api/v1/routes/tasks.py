"""Task & SiteIssue routes — Phase 4. Thin: all rules live in tasks_service.

Route order matters: /tasks/overdue is declared BEFORE /tasks/{task_id},
otherwise "overdue" would be treated as an id.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.tasks import IssueCategory, IssuePriority, IssueStatus, TaskStatus
from app.models.user import User
from app.schemas.tasks import (
    IssueCreate,
    IssueOut,
    IssueUpdate,
    TaskCreate,
    TaskOut,
    TaskUpdate,
)
from app.services import tasks_service

router = APIRouter(tags=["tasks", "issues"])


# ---- Tasks ---------------------------------------------------------------

@router.post("/tasks", response_model=TaskOut, status_code=201)
def create_task(data: TaskCreate, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    return tasks_service.create_task(db, current_user, data)


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(project_id: int | None = None, site_id: int | None = None,
               status: TaskStatus | None = None,
               db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    return tasks_service.list_tasks(db, current_user, project_id, site_id, status)


@router.get("/tasks/overdue", response_model=list[TaskOut])
def list_overdue_tasks(db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    return tasks_service.list_overdue_tasks(db, current_user)


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: int, db: Session = Depends(get_db),
             current_user: User = Depends(get_current_user)):
    return tasks_service.get_owned_task(db, current_user, task_id)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(task_id: int, data: TaskUpdate,
                db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    return tasks_service.update_task(db, current_user, task_id, data)


# ---- Site issues -----------------------------------------------------------

@router.post("/issues", response_model=IssueOut, status_code=201)
def create_issue(data: IssueCreate, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    return tasks_service.create_issue(db, current_user, data)


@router.get("/issues", response_model=list[IssueOut])
def list_issues(site_id: int | None = None,
                category: IssueCategory | None = None,
                priority: IssuePriority | None = None,
                status: IssueStatus | None = None,
                db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    return tasks_service.list_issues(db, current_user, site_id, category, priority, status)


@router.get("/issues/{issue_id}", response_model=IssueOut)
def get_issue(issue_id: int, db: Session = Depends(get_db),
              current_user: User = Depends(get_current_user)):
    return tasks_service.get_owned_issue(db, current_user, issue_id)


@router.patch("/issues/{issue_id}", response_model=IssueOut)
def update_issue(issue_id: int, data: IssueUpdate,
                 db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    return tasks_service.update_issue(db, current_user, issue_id, data)
