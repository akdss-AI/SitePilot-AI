"""Seed fictional demo data for SitePilot AI.

Run from the project root:

    python scripts/seed_demo.py            # seed once
    python scripts/seed_demo.py --reset    # wipe the demo data and re-seed
    python -m scripts.seed_demo            # same as the first form

The script uses DATABASE_URL from the environment (or .env in the
project root) and creates any missing tables first, so it works
against a fresh database. It does NOT call Groq and does NOT require
GROQ_API_KEY: all records are created through the normal service
functions (auth_service, project_service, inventory_service,
tasks_service), so the same ownership and validation rules apply as
through the API.

Re-run behaviour
----------------
- Running it a second time WITHOUT --reset refuses cleanly: it prints
  a message and exits with code 2, leaving the existing data untouched.
- WITH --reset it deletes ONLY the demo user's data (the demo user and
  everything owned by them) and re-seeds from scratch. It never
  touches other users' data.

Demo login (throwaway demo credentials ONLY — never a real account):
    email:    demo@sitepilot.example
    password: demo-sitepilot-2026

All names are fictional: no real companies or people.
"""
import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

# Allow `python scripts/seed_demo.py` from anywhere: make sure the
# project root (the parent of this scripts/ folder) is importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.inventory import Delivery, Material
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
from app.schemas.inventory import (
    DeliveryCreate,
    MaterialCreate,
    SupplierCreate,
)
from app.schemas.project import ProjectCreate, SiteCreate
from app.schemas.tasks import IssueCreate, TaskCreate
from app.schemas.user import UserCreate
from app.services import auth_service, inventory_service, project_service, tasks_service

DEMO_EMAIL = "demo@sitepilot.example"
DEMO_PASSWORD = "demo-sitepilot-2026"  # throwaway demo login ONLY
DEMO_NAME = "Demo Contractor"


class DemoDataExistsError(Exception):
    """Raised when demo data already exists and --reset was not given."""


def _demo_user(db: Session) -> User | None:
    return db.scalar(select(User).where(User.email == DEMO_EMAIL))


def _delete_demo_data(db: Session, user: User) -> None:
    """Delete ONLY the demo user's data.

    Deliveries are deleted first: their foreign keys to materials and
    suppliers are RESTRICT, so the database would refuse to delete a
    material or supplier that still has deliveries. Everything else
    cascades from the user row (projects -> sites -> materials/issues/
    tasks; suppliers are owned by the user).
    """
    for delivery in inventory_service.list_deliveries(db, user):
        db.delete(delivery)
    db.flush()
    db.delete(user)
    db.commit()


def seed_demo(db: Session, reset: bool = False) -> dict:
    """Create the fictional demo dataset. Returns a dict of counts.

    Raises DemoDataExistsError if the demo user already exists and
    reset is False. With reset=True the demo user's data is deleted
    first and re-created.
    """
    existing = _demo_user(db)
    if existing is not None:
        if not reset:
            raise DemoDataExistsError(
                f"Demo data already exists (user {DEMO_EMAIL}). "
                "Re-run with --reset to wipe it and re-seed."
            )
        _delete_demo_data(db, existing)

    today = date.today()
    yesterday = today - timedelta(days=1)
    days_ago_5 = today - timedelta(days=5)

    # ---- Demo user ------------------------------------------------------
    user = auth_service.register_user(
        db, UserCreate(full_name=DEMO_NAME, email=DEMO_EMAIL, password=DEMO_PASSWORD)
    )

    # ---- Suppliers ------------------------------------------------------
    suppliers = {}
    for data in (
        SupplierCreate(
            name="Ravi Building Supplies",
            contact_person="Ravi Kumar (demo)",
            phone="+92 300 1112223",
            email="orders@ravi-building.example",
            notes="Cement, sand and aggregates.",
        ),
        SupplierCreate(
            name="Mehran Steel Traders",
            contact_person="Mehran Ali (demo)",
            phone="+92 321 4445556",
            email="sales@mehran-steel.example",
            notes="Steel rebar and structural steel.",
        ),
        SupplierCreate(
            name="City Hardware Depot",
            contact_person="Sara Iqbal (demo)",
            phone="+92 333 7778889",
            email="hello@city-hardware.example",
            notes="Bricks, paint, tiles and general hardware.",
        ),
    ):
        supplier = inventory_service.create_supplier(db, user, data)
        suppliers[supplier.name] = supplier

    # ---- Projects + sites ----------------------------------------------
    project1 = project_service.create_project(
        db,
        user,
        ProjectCreate(
            name="Riverside Villas",
            client_name="Sunrise Properties (Demo)",
            location="Clifton Block 4, Karachi (demo)",
            description="Two residential towers, 48 apartments.",
            start_date=today - timedelta(days=90),
        ),
    )
    tower_a = project_service.create_site(
        db, user, project1.id, SiteCreate(name="Tower A", location="Plot 12, Riverside Villas")
    )
    tower_b = project_service.create_site(
        db, user, project1.id, SiteCreate(name="Tower B", location="Plot 13, Riverside Villas")
    )

    project2 = project_service.create_project(
        db,
        user,
        ProjectCreate(
            name="Green Acres Commercial Plaza",
            client_name="Acme Developers (Demo)",
            location="Gulberg Greens, Lahore (demo)",
            description="Ground + 5 floors of retail and offices.",
            start_date=today - timedelta(days=30),
        ),
    )
    block_c = project_service.create_site(
        db, user, project2.id, SiteCreate(name="Block C", location="Main Boulevard, Green Acres")
    )

    # ---- Materials (opening stock) --------------------------------------
    # Sand (40 <= reorder 100) and Paint (18 <= reorder 20) are low stock.
    materials = {}
    for data in (
        MaterialCreate(
            site_id=tower_a.id, name="Cement", unit="bags",
            quantity_on_hand=120, reorder_level=50,
            preferred_supplier_id=suppliers["Ravi Building Supplies"].id,
        ),
        MaterialCreate(
            site_id=tower_a.id, name="Steel Rebar", unit="kg",
            quantity_on_hand=850, reorder_level=500,
            preferred_supplier_id=suppliers["Mehran Steel Traders"].id,
        ),
        MaterialCreate(
            site_id=tower_a.id, name="Sand", unit="cubic ft",
            quantity_on_hand=40, reorder_level=100,
            preferred_supplier_id=suppliers["Ravi Building Supplies"].id,
        ),
        MaterialCreate(
            site_id=tower_b.id, name="Bricks", unit="pcs",
            quantity_on_hand=5000, reorder_level=2000,
            preferred_supplier_id=suppliers["City Hardware Depot"].id,
        ),
        MaterialCreate(
            site_id=tower_b.id, name="Paint", unit="litres",
            quantity_on_hand=18, reorder_level=20,
            preferred_supplier_id=suppliers["City Hardware Depot"].id,
        ),
        MaterialCreate(
            site_id=block_c.id, name="Ceramic Tiles", unit="boxes",
            quantity_on_hand=60, reorder_level=30,
            preferred_supplier_id=suppliers["City Hardware Depot"].id,
        ),
    ):
        material = inventory_service.create_material(db, user, data)
        materials[material.name] = material

    # ---- Deliveries ------------------------------------------------------
    # One received (stock goes 120 -> 320 bags of cement), two pending.
    received = inventory_service.create_delivery(
        db,
        user,
        DeliveryCreate(
            material_id=materials["Cement"].id,
            supplier_id=suppliers["Ravi Building Supplies"].id,
            quantity=200,
            unit_price=1150,
            expected_date=yesterday,
            notes="Cement delivery arrived on schedule.",
        ),
    )
    inventory_service.receive_delivery(db, user, received.id)

    inventory_service.create_delivery(
        db,
        user,
        DeliveryCreate(
            material_id=materials["Bricks"].id,
            supplier_id=suppliers["City Hardware Depot"].id,
            quantity=3000,
            unit_price=28,
            expected_date=today + timedelta(days=3),
            notes="Bricks for Tower B second-floor walls.",
        ),
    )
    inventory_service.create_delivery(
        db,
        user,
        DeliveryCreate(
            material_id=materials["Paint"].id,
            supplier_id=suppliers["City Hardware Depot"].id,
            quantity=40,
            unit_price=2400,
            expected_date=today + timedelta(days=2),
            notes="Exterior paint, expected before the weekend.",
        ),
    )

    # ---- Tasks (every status; one overdue, one due today) ----------------
    for data in (
        TaskCreate(
            project_id=project1.id, site_id=tower_a.id,
            title="Complete Tower A slab formwork",
            description="Formwork for the third-floor slab is behind schedule.",
            status=TaskStatus.TODO, due_date=yesterday,  # OVERDUE
        ),
        TaskCreate(
            project_id=project1.id, site_id=tower_b.id,
            title="Inspect scaffolding on Tower B",
            description="Daily safety walk before work starts.",
            status=TaskStatus.IN_PROGRESS, due_date=today,  # DUE TODAY
        ),
        TaskCreate(
            project_id=project1.id, site_id=tower_b.id,
            title="Pour concrete for Tower B columns",
            description="Second-floor columns, weather permitting.",
            status=TaskStatus.TODO, due_date=today + timedelta(days=4),
        ),
        TaskCreate(
            project_id=project1.id, site_id=tower_a.id,
            title="Submit Tower A foundation inspection report",
            description="Signed off by the site engineer.",
            status=TaskStatus.DONE, due_date=days_ago_5,
        ),
        TaskCreate(
            project_id=project1.id, site_id=None,
            title="Coordinate crane schedule with site team",
            description="Crane is shared between Tower A and Tower B.",
            status=TaskStatus.IN_PROGRESS, due_date=None,  # never overdue
        ),
        TaskCreate(
            project_id=project2.id, site_id=block_c.id,
            title="Finalise shop drawings for Block C",
            description="Retail floor layout approval from the client.",
            status=TaskStatus.TODO, due_date=today + timedelta(days=7),
        ),
    ):
        tasks_service.create_task(db, user, data)

    # ---- Issues (several categories; one critical open safety issue) -----
    for data in (
        IssueCreate(
            site_id=tower_b.id,
            title="Scaffolding guardrail missing on Tower B level 3",
            description="Guardrail removed during material lifting and not replaced.",
            category=IssueCategory.SAFETY,
            priority=IssuePriority.CRITICAL,
            status=IssueStatus.OPEN,
        ),
        IssueCreate(
            site_id=tower_a.id,
            title="Hairline cracks in Tower A ground-floor plaster",
            description="Cracks along the corridor wall; needs inspection.",
            category=IssueCategory.QUALITY,
            priority=IssuePriority.HIGH,
            status=IssueStatus.OPEN,
        ),
        IssueCreate(
            site_id=tower_a.id,
            title="Cement bags damaged by overnight rain",
            description="12 bags got wet where the tarp slipped.",
            category=IssueCategory.MATERIAL,
            priority=IssuePriority.MEDIUM,
            status=IssueStatus.IN_PROGRESS,
        ),
        IssueCreate(
            site_id=tower_b.id,
            title="Tower crane brake warning light on",
            description="Operator reported a warning light; crane parked until checked.",
            category=IssueCategory.EQUIPMENT,
            priority=IssuePriority.HIGH,
            status=IssueStatus.OPEN,
        ),
        IssueCreate(
            site_id=block_c.id,
            title="Rain delay expected this week",
            description="Forecast rain slowed excavation for two days.",
            category=IssueCategory.WEATHER,
            priority=IssuePriority.LOW,
            status=IssueStatus.RESOLVED,
        ),
    ):
        tasks_service.create_issue(db, user, data)

    counts = {
        "users": db.scalar(select(func.count()).select_from(User)),
        "projects": db.scalar(select(func.count()).select_from(Project)),
        "sites": db.scalar(select(func.count()).select_from(Site)),
        "suppliers": len(suppliers),
        "materials": db.scalar(select(func.count()).select_from(Material)),
        "deliveries": db.scalar(select(func.count()).select_from(Delivery)),
        "tasks": db.scalar(select(func.count()).select_from(Task)),
        "issues": db.scalar(select(func.count()).select_from(SiteIssue)),
    }
    return counts


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(
        description="Seed fictional demo data for SitePilot AI."
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the existing demo user's data first, then re-seed.",
    )
    args = parser.parse_args(argv)

    # Create tables if the database is fresh (no-op if they exist).
    import app.models as _models  # noqa: F401  (register models on Base.metadata)

    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        counts = seed_demo(db, reset=args.reset)
    except DemoDataExistsError as exc:
        print(f"Seed refused: {exc}")
        return 2
    finally:
        db.close()

    print("SitePilot AI demo data seeded:")
    for key in (
        "users", "projects", "sites", "suppliers",
        "materials", "deliveries", "tasks", "issues",
    ):
        print(f"  {key}: {counts[key]}")
    print()
    print("Demo login (throwaway demo credentials only):")
    print(f"  email:    {DEMO_EMAIL}")
    print(f"  password: {DEMO_PASSWORD}")
    print("Log in at /login, or POST /api/v1/auth/login.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
