"""Site-update (LLM) routes — Phase 5. Thin: all rules live in
site_update_service; the Groq call lives in app.llm.

POST returns 201 with the recorded SiteUpdate in every case where
the submission itself was accepted — including when processing
failed (Groq down, unparseable output, invalid actions). The failure
is in the body's status/failure_reason, never hidden: a failed
update is status="failed", never presented as success. The one
exception is a missing GROQ_API_KEY, a pre-flight configuration
error: that returns 503 and no update row is created.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.site_updates import SiteUpdateCreate, SiteUpdateOut
from app.services import site_update_service

router = APIRouter(tags=["site-updates"])


@router.post("/site-updates", response_model=SiteUpdateOut, status_code=201)
def submit_site_update(
    data: SiteUpdateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return site_update_service.submit_site_update(
        db, current_user, data.site_id, data.raw_text
    )


@router.get("/site-updates", response_model=list[SiteUpdateOut])
def list_site_updates(
    site_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return site_update_service.list_site_updates(db, current_user, site_id)


@router.get("/site-updates/{update_id}", response_model=SiteUpdateOut)
def get_site_update(
    update_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return site_update_service.get_owned_site_update(db, current_user, update_id)
