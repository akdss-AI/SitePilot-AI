"""Daily-summary route — Phase 6. Thin: all logic lives in summary_service.

The summary is generated on read from live data; nothing is stored.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.summary import ProjectSummaryOut
from app.services import summary_service

router = APIRouter(tags=["summary"])


@router.get(
    "/projects/{project_id}/summary/today", response_model=ProjectSummaryOut
)
def get_today_summary(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return summary_service.build_project_summary(db, current_user, project_id)
