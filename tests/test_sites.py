"""Phase 2 — site CRUD, invalid references and ownership tests."""
from tests.test_projects import create_project


def make_project(client, headers, name="Riverside Villas"):
    return create_project(client, headers, name=name).json()["id"]


def create_site(client, headers, project_id, name="Tower A"):
    return client.post(
        f"/api/v1/projects/{project_id}/sites",
        json={"name": name, "location": "North plot"},
        headers=headers,
    )


def test_create_and_read_site(client, owner_headers):
    project_id = make_project(client, owner_headers)
    created = create_site(client, owner_headers, project_id)
    assert created.status_code == 201
    site = created.json()
    assert site["project_id"] == project_id
    assert site["status"] == "active"

    fetched = client.get(f"/api/v1/sites/{site['id']}", headers=owner_headers)
    assert fetched.status_code == 200


def test_create_site_under_nonexistent_project_is_404(client, owner_headers):
    assert create_site(client, owner_headers, 99999).status_code == 404


def test_create_site_under_other_users_project_is_404(client, owner_headers, other_headers):
    project_id = make_project(client, owner_headers)
    assert create_site(client, other_headers, project_id).status_code == 404


def test_list_sites_requires_ownership(client, owner_headers, other_headers):
    project_id = make_project(client, owner_headers)
    create_site(client, owner_headers, project_id)
    listed = client.get(f"/api/v1/projects/{project_id}/sites", headers=owner_headers)
    assert [s["name"] for s in listed.json()] == ["Tower A"]
    assert client.get(
        f"/api/v1/projects/{project_id}/sites", headers=other_headers
    ).status_code == 404


def test_duplicate_site_name_in_same_project_is_409(client, owner_headers):
    project_id = make_project(client, owner_headers)
    assert create_site(client, owner_headers, project_id).status_code == 201
    assert create_site(client, owner_headers, project_id).status_code == 409


def test_same_site_name_in_different_projects_is_allowed(client, owner_headers):
    p1 = make_project(client, owner_headers, name="Project One")
    p2 = make_project(client, owner_headers, name="Project Two")
    assert create_site(client, owner_headers, p1).status_code == 201
    assert create_site(client, owner_headers, p2).status_code == 201


def test_other_users_site_is_404_and_cannot_be_patched(client, owner_headers, other_headers):
    project_id = make_project(client, owner_headers)
    site_id = create_site(client, owner_headers, project_id).json()["id"]
    assert client.get(f"/api/v1/sites/{site_id}", headers=other_headers).status_code == 404
    assert client.patch(
        f"/api/v1/sites/{site_id}", json={"name": "Hijacked"}, headers=other_headers
    ).status_code == 404


def test_update_site(client, owner_headers):
    project_id = make_project(client, owner_headers)
    site_id = create_site(client, owner_headers, project_id).json()["id"]
    updated = client.patch(
        f"/api/v1/sites/{site_id}",
        json={"status": "on_hold"},
        headers=owner_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "on_hold"


def test_deleting_project_removes_its_sites(client, owner_headers):
    project_id = make_project(client, owner_headers)
    site_id = create_site(client, owner_headers, project_id).json()["id"]
    assert client.delete(f"/api/v1/projects/{project_id}", headers=owner_headers).status_code == 204
    assert client.get(f"/api/v1/sites/{site_id}", headers=owner_headers).status_code == 404
