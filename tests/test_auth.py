"""Phase 2 — authentication tests."""
from tests.conftest import PASSWORD, register


def test_register_succeeds_and_never_exposes_password(client):
    response = register(client)
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "owner@example.com"
    assert body["full_name"] == "Test Owner"
    assert "password" not in body
    assert "hashed_password" not in body


def test_register_normalises_email_case(client):
    response = register(client, email="MixedCase@Example.COM")
    assert response.status_code == 201
    assert response.json()["email"] == "mixedcase@example.com"


def test_register_duplicate_email_is_409(client):
    assert register(client).status_code == 201
    duplicate = register(client, email="OWNER@example.com")  # same, other case
    assert duplicate.status_code == 409


def test_register_short_password_is_422(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"full_name": "X", "email": "x@example.com", "password": "short"},
    )
    assert response.status_code == 422


def test_register_invalid_email_is_422(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"full_name": "X", "email": "not-an-email", "password": PASSWORD},
    )
    assert response.status_code == 422


def test_login_succeeds_and_me_returns_the_user(client):
    register(client)
    login = client.post(
        "/api/v1/auth/login",
        data={"username": "owner@example.com", "password": PASSWORD},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    assert login.json()["token_type"] == "bearer"

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "owner@example.com"


def test_login_wrong_password_is_401(client):
    register(client)
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "owner@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401


def test_login_unknown_email_gives_same_401(client):
    # Same generic failure as a wrong password — the API must not reveal
    # whether an email is registered.
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "ghost@example.com", "password": PASSWORD},
    )
    assert response.status_code == 401


def test_me_without_token_is_401(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_with_garbage_token_is_401(client):
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401
