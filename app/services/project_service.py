"""Project & Site business logic. No HTTP code here — routes call this.

Ownership rule (the security core of Phase 2): every read and write goes
through a query filtered by owner_id == current_user.id. A record owned
by someone else is treated as not found (404), so the API never even
confirms that another user's project exists.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.project import Project, Site
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectUpdate, SiteCreate, SiteUpdate


# ---- Projects -----------------------------------------------------------

def create_project(db: Session, owner: User, data: ProjectCreate) -> Project:
    duplicate = db.scalar(
        select(Project).where(
            Project.owner_id == owner.id, Project.name == data.name
        )
    )
    if duplicate is not None:
        raise AppError("You already have a project with this name.", 409)
    project = Project(owner_id=owner.id, **data.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def list_projects(db: Session, owner: User) -> list[Project]:
    return list(
        db.scalars(
            select(Project)
            .where(Project.owner_id == owner.id)
            .order_by(Project.id)
        )
    )


def get_owned_project(db: Session, owner: User, project_id: int) -> Project:
    project = db.scalar(
        select(Project).where(
            Project.id == project_id, Project.owner_id == owner.id
        )
    )
    if project is None:
        raise AppError("Project not found.", 404)
    return project


def update_project(
    db: Session, owner: User, project_id: int, data: ProjectUpdate
) -> Project:
    project = get_owned_project(db, owner, project_id)
    changes = data.model_dump(exclude_unset=True)

    if "name" in changes and changes["name"] != project.name:
        duplicate = db.scalar(
            select(Project).where(
                Project.owner_id == owner.id,
                Project.name == changes["name"],
                Project.id != project.id,
            )
        )
        if duplicate is not None:
            raise AppError("You already have a project with this name.", 409)

    # Schema validation only sees the fields sent in this PATCH, so check
    # the *merged* dates here before writing anything.
    new_start = changes.get("start_date", project.start_date)
    new_end = changes.get("end_date", project.end_date)
    if new_start and new_end and new_end < new_start:
        raise AppError("end_date must not be before start_date.", 422)

    for field, value in changes.items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return project


def delete_project(db: Session, owner: User, project_id: int) -> None:
    project = get_owned_project(db, owner, project_id)
    db.delete(project)  # sites are removed by cascade (model + FK ondelete)
    db.commit()


# ---- Sites --------------------------------------------------------------

def create_site(db: Session, owner: User, project_id: int, data: SiteCreate) -> Site:
    # Resolving the project through get_owned_project is the ownership
    # check AND the invalid-reference check in one step: a project that
    # does not exist, or belongs to someone else, is a 404.
    project = get_owned_project(db, owner, project_id)
    duplicate = db.scalar(
        select(Site).where(Site.project_id == project.id, Site.name == data.name)
    )
    if duplicate is not None:
        raise AppError("This project already has a site with this name.", 409)
    site = Site(project_id=project.id, **data.model_dump())
    db.add(site)
    db.commit()
    db.refresh(site)
    return site


def list_sites(db: Session, owner: User, project_id: int) -> list[Site]:
    project = get_owned_project(db, owner, project_id)
    return list(
        db.scalars(
            select(Site).where(Site.project_id == project.id).order_by(Site.id)
        )
    )


def get_owned_site(db: Session, owner: User, site_id: int) -> Site:
    # Join through Project so ownership is checked on the same query.
    site = db.scalar(
        select(Site)
        .join(Project, Site.project_id == Project.id)
        .where(Site.id == site_id, Project.owner_id == owner.id)
    )
    if site is None:
        raise AppError("Site not found.", 404)
    return site


def update_site(db: Session, owner: User, site_id: int, data: SiteUpdate) -> Site:
    site = get_owned_site(db, owner, site_id)
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] != site.name:
        duplicate = db.scalar(
            select(Site).where(
                Site.project_id == site.project_id,
                Site.name == changes["name"],
                Site.id != site.id,
            )
        )
        if duplicate is not None:
            raise AppError("This project already has a site with this name.", 409)
    for field, value in changes.items():
        setattr(site, field, value)
    db.commit()
    db.refresh(site)
    return site
