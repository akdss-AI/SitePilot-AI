"""Project & Site routes — thin: every rule lives in project_service."""
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.project import (
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
    SiteCreate,
    SiteOut,
    SiteUpdate,
)
from app.services import project_service

router = APIRouter(tags=["projects"])


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(
    data: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return project_service.create_project(db, current_user, data)


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return project_service.list_projects(db, current_user)


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return project_service.get_owned_project(db, current_user, project_id)


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int,
    data: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return project_service.update_project(db, current_user, project_id, data)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project_service.delete_project(db, current_user, project_id)
    return Response(status_code=204)


# ---- Sites (nested create/list, direct get/update) ----------------------

@router.post(
    "/projects/{project_id}/sites", response_model=SiteOut, status_code=201
)
def create_site(
    project_id: int,
    data: SiteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return project_service.create_site(db, current_user, project_id, data)


@router.get("/projects/{project_id}/sites", response_model=list[SiteOut])
def list_sites(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return project_service.list_sites(db, current_user, project_id)


@router.get("/sites/{site_id}", response_model=SiteOut)
def get_site(
    site_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return project_service.get_owned_site(db, current_user, site_id)


@router.patch("/sites/{site_id}", response_model=SiteOut)
def update_site(
    site_id: int,
    data: SiteUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return project_service.update_site(db, current_user, site_id, data)
