"""Health endpoint.

Reports whether the app is running and whether the database answers.
A failed database check returns status "degraded" — it does not crash
the app, because a health endpoint that crashes tells you nothing.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    settings = get_settings()
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
        status = "ok"
    except Exception:
        database = "unavailable"
        status = "degraded"
    return {
        "status": status,
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.app_env,
        "database": database,
        # Presence only — the key itself is never returned.
        "groq_configured": settings.groq_configured,
    }
