"""Phase 2 — project CRUD, validation and ownership tests."""

PROJECT = {"name": "Riverside Villas", "client_name": "Fictional Homes Ltd"}


def create_project(client, headers, **overrides):
    return client.post(
        "/api/v1/projects", json={**PROJECT, **overrides}, headers=headers
    )


def test_unauthenticated_requests_are_401(client):
    assert client.get("/api/v1/projects").status_code == 401
    assert client.post("/api/v1/projects", json=PROJECT).status_code == 401


def test_create_and_read_project(client, owner_headers):
    created = create_project(client, owner_headers)
    assert created.status_code == 201
    project = created.json()
    assert project["name"] == "Riverside Villas"
    assert project["status"] == "active"

    fetched = client.get(f"/api/v1/projects/{project['id']}", headers=owner_headers)
    assert fetched.status_code == 200
    assert fetched.json()["id"] == project["id"]


def test_list_shows_only_own_projects(client, owner_headers, other_headers):
    create_project(client, owner_headers)
    create_project(client, other_headers, name="Other Project")
    mine = client.get("/api/v1/projects", headers=owner_headers)
    assert [p["name"] for p in mine.json()] == ["Riverside Villas"]


def test_other_users_project_is_404_not_leaked(client, owner_headers, other_headers):
    project_id = create_project(client, owner_headers).json()["id"]
    assert client.get(f"/api/v1/projects/{project_id}", headers=other_headers).status_code == 404


def test_nonexistent_project_is_404(client, owner_headers):
    assert client.get("/api/v1/projects/99999", headers=owner_headers).status_code == 404


def test_update_project(client, owner_headers):
    project_id = create_project(client, owner_headers).json()["id"]
    updated = client.patch(
        f"/api/v1/projects/{project_id}",
        json={"status": "on_hold", "location": "Fictional Town"},
        headers=owner_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "on_hold"
    assert updated.json()["location"] == "Fictional Town"
    assert updated.json()["name"] == "Riverside Villas"  # untouched field kept


def test_other_user_cannot_update_or_delete(client, owner_headers, other_headers):
    project_id = create_project(client, owner_headers).json()["id"]
    assert client.patch(
        f"/api/v1/projects/{project_id}", json={"name": "Hijacked"}, headers=other_headers
    ).status_code == 404
    assert client.delete(
        f"/api/v1/projects/{project_id}", headers=other_headers
    ).status_code == 404
    # And the project is genuinely unchanged for its owner.
    still = client.get(f"/api/v1/projects/{project_id}", headers=owner_headers)
    assert still.json()["name"] == "Riverside Villas"


def test_delete_project(client, owner_headers):
    project_id = create_project(client, owner_headers).json()["id"]
    assert client.delete(f"/api/v1/projects/{project_id}", headers=owner_headers).status_code == 204
    assert client.get(f"/api/v1/projects/{project_id}", headers=owner_headers).status_code == 404


def test_duplicate_project_name_same_owner_is_409(client, owner_headers):
    assert create_project(client, owner_headers).status_code == 201
    assert create_project(client, owner_headers).status_code == 409


def test_same_project_name_different_owner_is_allowed(client, owner_headers, other_headers):
    assert create_project(client, owner_headers).status_code == 201
    assert create_project(client, other_headers).status_code == 201


def test_blank_name_is_422(client, owner_headers):
    assert create_project(client, owner_headers, name="   ").status_code == 422


def test_end_date_before_start_date_is_422(client, owner_headers):
    response = create_project(
        client, owner_headers, start_date="2026-06-01", end_date="2026-01-01"
    )
    assert response.status_code == 422


def test_patch_merged_dates_are_validated(client, owner_headers):
    # PATCH sends only end_date; it must still be checked against the
    # project's stored start_date by the service.
    project_id = create_project(
        client, owner_headers, start_date="2026-06-01"
    ).json()["id"]
    response = client.patch(
        f"/api/v1/projects/{project_id}",
        json={"end_date": "2026-01-01"},
        headers=owner_headers,
    )
    assert response.status_code == 422
