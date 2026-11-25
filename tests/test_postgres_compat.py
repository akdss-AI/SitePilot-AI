"""PostgreSQL compatibility tests.

Two layers, kept deliberately separate and honestly labelled:

1. DDL compilation (always runs, no server needed): every table's
   CREATE TABLE statement must compile under the PostgreSQL dialect.
   This catches dialect-specific mistakes (column types, constraints)
   but does NOT prove the app runs against PostgreSQL.

2. Live PostgreSQL flow (runs ONLY when SITEPILOT_PG_TEST_URL is set):
   exercises register -> project/site -> supplier/material -> delivery
   -> receive against a real PostgreSQL server, through the service
   layer. Skipped — with this reason printed — when no server is
   configured. Example:
       SITEPILOT_PG_TEST_URL=postgresql+psycopg2://user:pass@localhost:5432/sitepilot_test \
           python -m pytest tests/test_postgres_compat.py
"""
import os
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateTable

from app.db.base import Base

import app.models as _models  # noqa: F401


def test_all_tables_compile_for_postgresql():
    assert Base.metadata.tables, "no models registered"
    for table in Base.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
        assert "CREATE TABLE" in ddl


def test_no_sqlite_autoincrement_hacks_in_models():
    # sqlite_autoincrement is a SQLite-only table option; using it would
    # mean the models are quietly SQLite-shaped instead of portable.
    for table in Base.metadata.sorted_tables:
        assert not table.kwargs.get("sqlite_autoincrement")


PG_URL = os.environ.get("SITEPILOT_PG_TEST_URL", "")


@pytest.mark.skipif(
    not PG_URL.startswith("postgresql"),
    reason="SITEPILOT_PG_TEST_URL not set — live PostgreSQL not verified in this run",
)
def test_live_postgresql_end_to_end_flow():
    from app.schemas.inventory import DeliveryCreate, MaterialCreate, SupplierCreate
    from app.schemas.project import ProjectCreate, SiteCreate
    from app.schemas.user import UserCreate
    from app.services import auth_service, inventory_service, project_service

    engine = create_engine(PG_URL)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        user = auth_service.register_user(
            db, UserCreate(full_name="PG Tester", email="pg@example.com",
                           password="test-password-123")
        )
        project = project_service.create_project(
            db, user, ProjectCreate(name="PG Project")
        )
        site = project_service.create_site(
            db, user, project.id, SiteCreate(name="PG Site")
        )
        supplier = inventory_service.create_supplier(
            db, user, SupplierCreate(name="PG Supplier")
        )
        material = inventory_service.create_material(
            db, user,
            MaterialCreate(site_id=site.id, name="Cement", unit="bags",
                           quantity_on_hand=Decimal("10"), reorder_level=Decimal("5")),
        )
        delivery = inventory_service.create_delivery(
            db, user,
            DeliveryCreate(material_id=material.id, supplier_id=supplier.id,
                           quantity=Decimal("200")),
        )
        inventory_service.receive_delivery(db, user, delivery.id)
        db.refresh(material)
        assert material.quantity_on_hand == Decimal("210")
        assert inventory_service.list_stock_alerts(db, user) == []
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
