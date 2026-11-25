"""Test setup.

Tests must never touch a real database or a real .env. The test database
URL is set BEFORE any app module is imported, because app.db.session
creates its engine at import time.
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["APP_ENV"] = "test"
# Long test-only secret: the short dev placeholder triggers JWT
# InsecureKeyLengthWarning (HS256 wants >= 32 bytes). Still not a real secret.
os.environ["SECRET_KEY"] = "test-only-secret-key-with-at-least-32-bytes"
os.environ["GROQ_API_KEY"] = ""  # tests never call the real Groq API

import pytest
from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import engine
from app.main import create_app

import app.models as _models  # noqa: F401  (register models before create_all)


@pytest.fixture(autouse=True)
def fresh_tables():
    """Isolate tests: empty schema before and after every test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client():
    return TestClient(create_app())


# ---- Phase 2 helpers -----------------------------------------------------

PASSWORD = "test-password-123"


def register(client, email="owner@example.com", name="Test Owner"):
    return client.post(
        "/api/v1/auth/register",
        json={"full_name": name, "email": email, "password": PASSWORD},
    )


def auth_headers(client, email="owner@example.com", name="Test Owner"):
    """Register a fresh user and return Authorization headers for them."""
    response = register(client, email=email, name=name)
    assert response.status_code == 201, response.text
    login = client.post(
        "/api/v1/auth/login", data={"username": email, "password": PASSWORD}
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.fixture()
def owner_headers(client):
    return auth_headers(client, "owner@example.com", "Project Owner")


@pytest.fixture()
def other_headers(client):
    return auth_headers(client, "other@example.com", "Other User")


# ---- Phase 3 helpers -----------------------------------------------------

def make_site(client, headers, project_name="Riverside Villas", site_name="Tower A"):
    """Create one project + one site, return (project_id, site_id)."""
    project = client.post(
        "/api/v1/projects", json={"name": project_name}, headers=headers
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    site = client.post(
        f"/api/v1/projects/{project_id}/sites",
        json={"name": site_name},
        headers=headers,
    )
    assert site.status_code == 201, site.text
    return project_id, site.json()["id"]


def make_supplier(client, headers, name="Ali Traders"):
    response = client.post(
        "/api/v1/suppliers", json={"name": name}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def make_material(client, headers, site_id, **overrides):
    payload = {"site_id": site_id, "name": "Cement", "unit": "bags", **overrides}
    response = client.post("/api/v1/materials", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()
