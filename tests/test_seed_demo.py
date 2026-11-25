"""Phase 7 tests: the fictional demo-data seed script.

The seed runs against the test SQLite database (set up by conftest)
and never calls Groq. Counts are the full seeded dataset, not just
the demo user, because the test database starts empty.
"""
from datetime import date

import pytest
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.inventory import Delivery, DeliveryStatus, Material
from app.models.project import Project, Site
from app.models.tasks import (
    IssuePriority,
    IssueStatus,
    SiteIssue,
    Task,
)
from app.models.user import User
from scripts.seed_demo import (
    DEMO_EMAIL,
    DEMO_PASSWORD,
    DemoDataExistsError,
    seed_demo,
)
from app.services import auth_service


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_seed_creates_expected_dataset(db):
    counts = seed_demo(db)

    assert counts == {
        "users": 1,
        "projects": 2,
        "sites": 3,
        "suppliers": 3,
        "materials": 6,
        "deliveries": 3,
        "tasks": 6,
        "issues": 5,
    }

    # Demo user exists and the documented password actually logs in.
    user = db.scalar(select(User).where(User.email == DEMO_EMAIL))
    assert user is not None
    assert user.full_name == "Demo Contractor"
    assert auth_service.authenticate_user(db, DEMO_EMAIL, DEMO_PASSWORD).id == user.id

    # At least one low-stock material (Sand 40 <= reorder 100).
    low_stock = [m for m in db.scalars(select(Material)) if m.is_low_stock]
    assert low_stock, "expected at least one low-stock material"
    assert {m.name for m in low_stock} == {"Sand", "Paint"}

    # One received delivery (cement stock 120 + 200 = 320) and two pending.
    received = db.scalars(
        select(Delivery).where(Delivery.status == DeliveryStatus.RECEIVED)
    ).all()
    assert len(received) == 1
    assert received[0].quantity == 200
    cement = db.scalar(select(Material).where(Material.name == "Cement"))
    assert cement.quantity_on_hand == 320
    pending = db.scalars(
        select(Delivery).where(Delivery.status == DeliveryStatus.PENDING)
    ).all()
    assert len(pending) == 2

    # Every task status is represented; one overdue, one due today.
    statuses = {t.status for t in db.scalars(select(Task))}
    assert statuses == {"todo", "in_progress", "done"}
    overdue = [t for t in db.scalars(select(Task)) if t.is_overdue]
    assert len(overdue) == 1
    assert overdue[0].title == "Complete Tower A slab formwork"
    due_today = [
        t for t in db.scalars(select(Task))
        if t.due_date == date.today() and t.status != "done"
    ]
    assert len(due_today) == 1
    assert due_today[0].title == "Inspect scaffolding on Tower B"

    # Issues across several categories, incl. one critical open safety issue.
    categories = {i.category for i in db.scalars(select(SiteIssue))}
    assert {"safety", "quality", "material", "equipment", "weather"} <= categories
    critical_open = db.scalars(
        select(SiteIssue).where(
            SiteIssue.priority == IssuePriority.CRITICAL,
            SiteIssue.status == IssueStatus.OPEN,
        )
    ).all()
    assert len(critical_open) == 1
    assert critical_open[0].category == "safety"
    assert "Scaffolding guardrail" in critical_open[0].title

    # Two projects with three sites between them.
    assert _count(db, Project) == 2
    assert _count(db, Site) == 3


def _count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


def test_seed_rerun_without_reset_refuses(db):
    seed_demo(db)
    with pytest.raises(DemoDataExistsError, match="already exists"):
        seed_demo(db)
    # Refusal leaves the existing data untouched (no duplicates).
    assert _count(db, User) == 1
    assert _count(db, Project) == 2


def test_seed_reset_wipes_and_reseeds(db):
    seed_demo(db)
    counts = seed_demo(db, reset=True)
    assert counts == {
        "users": 1,
        "projects": 2,
        "sites": 3,
        "suppliers": 3,
        "materials": 6,
        "deliveries": 3,
        "tasks": 6,
        "issues": 5,
    }
    # Still exactly one demo user and one overdue task — no duplicates.
    assert _count(db, User) == 1
    overdue = [t for t in db.scalars(select(Task)) if t.is_overdue]
    assert len(overdue) == 1
