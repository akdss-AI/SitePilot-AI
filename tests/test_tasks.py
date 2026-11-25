"""Phase 4 — tasks: creation rules, overdue matrix, ownership, assignment."""
from datetime import date, timedelta

import pytest

from tests.conftest import make_site


def user_id(client, headers):
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["id"]


def make_task(client, headers, project_id, **overrides):
    payload = {"project_id": project_id, "title": "Pour concrete slab", **overrides}
    return client.post("/api/v1/tasks", json=payload, headers=headers)


def setup_task(client, headers, **overrides):
    project_id, site_id = make_site(client, headers)
    response = make_task(client, headers, project_id, site_id=site_id, **overrides)
    assert response.status_code == 201, response.text
    return project_id, site_id, response.json()


# ---- Creation ---------------------------------------------------------------

def test_create_task_defaults_to_todo_and_not_overdue(client, owner_headers):
    project_id, site_id, task = setup_task(client, owner_headers)
    assert task["status"] == "todo"
    assert task["project_id"] == project_id
    assert task["site_id"] == site_id
    assert task["due_date"] is None
    assert task["assigned_to"] is None
    assert task["is_overdue"] is False
    assert task["overdue"] is False


def test_create_task_without_site_is_allowed(client, owner_headers):
    project_id, _ = make_site(client, owner_headers)
    response = make_task(client, owner_headers, project_id)
    assert response.status_code == 201
    assert response.json()["site_id"] is None


def test_create_task_with_foreign_or_missing_project_is_404(client, owner_headers, other_headers):
    project_id, _ = make_site(client, owner_headers)
    assert make_task(client, owner_headers, 99999).status_code == 404
    # Another user's project: treated as not found, never confirmed.
    assert make_task(client, other_headers, project_id).status_code == 404


def test_create_task_site_must_belong_to_the_project(client, owner_headers):
    project_a, site_a = make_site(client, owner_headers, "Project A", "Site A")
    _, site_b = make_site(client, owner_headers, "Project B", "Site B")
    # Site from project B attached to a task on project A.
    assert make_task(
        client, owner_headers, project_a, site_id=site_b
    ).status_code == 422
    # Site from the same project is fine.
    assert make_task(
        client, owner_headers, project_a, site_id=site_a
    ).status_code == 201


def test_create_task_with_foreign_site_is_404(client, owner_headers, other_headers):
    project_id, _ = make_site(client, owner_headers)
    _, foreign_site = make_site(client, other_headers, "Other Project", "Other Site")
    assert make_task(
        client, owner_headers, project_id, site_id=foreign_site
    ).status_code == 404
    assert make_task(client, owner_headers, project_id, site_id=99999).status_code == 404


def test_create_task_requires_title_and_project(client, owner_headers):
    project_id, _ = make_site(client, owner_headers)
    assert client.post(
        "/api/v1/tasks", json={"project_id": project_id, "title": "  "},
        headers=owner_headers,
    ).status_code == 422
    assert client.post(
        "/api/v1/tasks", json={"title": "No project"}, headers=owner_headers
    ).status_code == 422


# ---- Overdue matrix -----------------------------------------------------------
# due offset: -1 past, 0 today, +1 future, None absent
#   x status: todo / in_progress / done
# Overdue only when due date is past AND status is not done.

@pytest.mark.parametrize("offset", [-1, 0, 1, None])
@pytest.mark.parametrize("status", ["todo", "in_progress", "done"])
def test_overdue_matrix(client, owner_headers, offset, status):
    project_id, _ = make_site(client, owner_headers)
    due = (date.today() + timedelta(days=offset)).isoformat() if offset is not None else None
    response = make_task(
        client, owner_headers, project_id, due_date=due, status=status
    )
    assert response.status_code == 201, response.text
    task = response.json()
    expected = offset == -1 and status != "done"
    assert task["is_overdue"] is expected, (offset, status, task)
    assert task["overdue"] is expected

    overdue = client.get("/api/v1/tasks/overdue", headers=owner_headers)
    assert overdue.status_code == 200
    ids = [t["id"] for t in overdue.json()]
    assert (task["id"] in ids) is expected, (offset, status, ids)


def test_overdue_endpoint_returns_only_overdue_tasks(client, owner_headers):
    project_id, _ = make_site(client, owner_headers)
    past = (date.today() - timedelta(days=2)).isoformat()
    future = (date.today() + timedelta(days=2)).isoformat()
    overdue_id = make_task(
        client, owner_headers, project_id, due_date=past, title="Late"
    ).json()["id"]
    make_task(client, owner_headers, project_id, due_date=future, title="Future")
    make_task(client, owner_headers, project_id, due_date=past, status="done", title="Done late")
    make_task(client, owner_headers, project_id, title="No date")
    overdue = client.get("/api/v1/tasks/overdue", headers=owner_headers)
    assert [t["id"] for t in overdue.json()] == [overdue_id]


def test_marking_task_done_clears_overdue_and_clearing_due_date_too(client, owner_headers):
    _, _, task = setup_task(
        client, owner_headers,
        due_date=(date.today() - timedelta(days=1)).isoformat(),
    )
    assert task["is_overdue"] is True
    done = client.patch(
        f"/api/v1/tasks/{task['id']}", json={"status": "done"}, headers=owner_headers
    )
    assert done.status_code == 200
    assert done.json()["is_overdue"] is False
    # Reopen it, then clear the due date: also no longer overdue.
    reopened = client.patch(
        f"/api/v1/tasks/{task['id']}", json={"status": "todo", "due_date": None},
        headers=owner_headers,
    )
    assert reopened.status_code == 200
    assert reopened.json()["is_overdue"] is False
    assert reopened.json()["due_date"] is None


# ---- Enum validation ----------------------------------------------------------

def test_invalid_task_status_is_422(client, owner_headers):
    _, _, task = setup_task(client, owner_headers)
    assert client.post(
        "/api/v1/tasks",
        json={"project_id": task["project_id"], "title": "x", "status": "finished"},
        headers=owner_headers,
    ).status_code == 422
    assert client.patch(
        f"/api/v1/tasks/{task['id']}", json={"status": "finished"},
        headers=owner_headers,
    ).status_code == 422


def test_invalid_due_date_is_422(client, owner_headers):
    project_id, _ = make_site(client, owner_headers)
    assert make_task(
        client, owner_headers, project_id, due_date="not-a-date"
    ).status_code == 422


# ---- Assignment ---------------------------------------------------------------

def test_assigned_to_must_be_an_existing_user(client, owner_headers):
    _, _, task = setup_task(client, owner_headers)
    assert make_task(
        client, owner_headers, task["project_id"], assigned_to=99999
    ).status_code == 422
    assert client.patch(
        f"/api/v1/tasks/{task['id']}", json={"assigned_to": 99999},
        headers=owner_headers,
    ).status_code == 422


def test_assigned_to_grants_no_access(client, owner_headers, other_headers):
    project_id, _ = make_site(client, owner_headers)
    other_id = user_id(client, other_headers)
    response = make_task(client, owner_headers, project_id, assigned_to=other_id)
    assert response.status_code == 201
    task = response.json()
    assert task["assigned_to"] == other_id
    # The assignee is not the owner: get / list / patch / overdue all hide it.
    assert client.get(f"/api/v1/tasks/{task['id']}", headers=other_headers).status_code == 404
    assert client.get("/api/v1/tasks", headers=other_headers).json() == []
    assert client.patch(
        f"/api/v1/tasks/{task['id']}", json={"status": "done"}, headers=other_headers
    ).status_code == 404
    assert client.get("/api/v1/tasks/overdue", headers=other_headers).json() == []
    # And the owner can still see and change it.
    assert client.get(f"/api/v1/tasks/{task['id']}", headers=owner_headers).status_code == 200


def test_assigned_to_can_be_set_and_cleared(client, owner_headers, other_headers):
    _, _, task = setup_task(client, owner_headers)
    other_id = user_id(client, other_headers)
    assigned = client.patch(
        f"/api/v1/tasks/{task['id']}", json={"assigned_to": other_id},
        headers=owner_headers,
    )
    assert assigned.status_code == 200
    assert assigned.json()["assigned_to"] == other_id
    cleared = client.patch(
        f"/api/v1/tasks/{task['id']}", json={"assigned_to": None},
        headers=owner_headers,
    )
    assert cleared.status_code == 200
    assert cleared.json()["assigned_to"] is None


# ---- Ownership / listing ------------------------------------------------------

def test_other_user_gets_404_on_get_list_patch_and_overdue(client, owner_headers, other_headers):
    _, _, task = setup_task(
        client, owner_headers,
        due_date=(date.today() - timedelta(days=1)).isoformat(),
    )
    assert client.get(f"/api/v1/tasks/{task['id']}", headers=other_headers).status_code == 404
    assert client.get("/api/v1/tasks", headers=other_headers).json() == []
    assert client.patch(
        f"/api/v1/tasks/{task['id']}", json={"title": "Hijacked"},
        headers=other_headers,
    ).status_code == 404
    assert client.get("/api/v1/tasks/overdue", headers=other_headers).json() == []
    # Owner's record is untouched.
    assert client.get(f"/api/v1/tasks/{task['id']}", headers=owner_headers).json()["title"] == "Pour concrete slab"


def test_list_returns_only_callers_own_tasks(client, owner_headers, other_headers):
    project_id, _ = make_site(client, owner_headers)
    make_task(client, owner_headers, project_id, title="Owner task")
    other_project, _ = make_site(client, other_headers, "Other Project", "Other Site")
    make_task(client, other_headers, other_project, title="Other task")
    owner_list = client.get("/api/v1/tasks", headers=owner_headers).json()
    assert [t["title"] for t in owner_list] == ["Owner task"]
    other_list = client.get("/api/v1/tasks", headers=other_headers).json()
    assert [t["title"] for t in other_list] == ["Other task"]


def test_list_filters_by_project_site_and_status(client, owner_headers):
    project_id, site_id = make_site(client, owner_headers)
    _, other_site = make_site(client, owner_headers, "Second Project", "Second Site")
    make_task(client, owner_headers, project_id, site_id=site_id, title="A")
    make_task(client, owner_headers, project_id, title="B", status="done")
    listed = client.get(f"/api/v1/tasks?project_id={project_id}", headers=owner_headers).json()
    assert len(listed) == 2
    assert [t["title"] for t in client.get(
        f"/api/v1/tasks?site_id={site_id}", headers=owner_headers).json()] == ["A"]
    assert [t["title"] for t in client.get(
        "/api/v1/tasks?status=done", headers=owner_headers).json()] == ["B"]
    # Filtering by a foreign project/site is a 404, not an empty list.
    _, foreign_site = make_site(client, owner_headers, "Third Project", "Third Site")
    assert client.get(
        f"/api/v1/tasks?project_id=99999", headers=owner_headers
    ).status_code == 404
    assert client.get(
        f"/api/v1/tasks?site_id=99999", headers=owner_headers
    ).status_code == 404
    assert foreign_site  # helper created the site; filter check above covers scope


# ---- PATCH --------------------------------------------------------------------

def test_patch_task_fields(client, owner_headers):
    project_id, site_id, task = setup_task(client, owner_headers)
    updated = client.patch(
        f"/api/v1/tasks/{task['id']}",
        json={
            "title": "Pour slab — revised",
            "description": "Add curing compound",
            "status": "in_progress",
            "due_date": (date.today() + timedelta(days=3)).isoformat(),
            "site_id": site_id,
        },
        headers=owner_headers,
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["title"] == "Pour slab — revised"
    assert body["description"] == "Add curing compound"
    assert body["status"] == "in_progress"
    assert body["site_id"] == site_id
    assert body["project_id"] == project_id


def test_patch_task_site_must_belong_to_its_project(client, owner_headers):
    _, _, task = setup_task(client, owner_headers)
    _, other_site = make_site(client, owner_headers, "Other Project", "Other Site")
    assert client.patch(
        f"/api/v1/tasks/{task['id']}", json={"site_id": other_site},
        headers=owner_headers,
    ).status_code == 422
    # Clearing the site is allowed.
    cleared = client.patch(
        f"/api/v1/tasks/{task['id']}", json={"site_id": None},
        headers=owner_headers,
    )
    assert cleared.status_code == 200
    assert cleared.json()["site_id"] is None


def test_patch_task_cannot_move_it_to_another_project(client, owner_headers):
    _, _, task = setup_task(client, owner_headers)
    other_project, _ = make_site(client, owner_headers, "Other Project", "Other Site")
    # project_id is not a PATCH field: it is ignored, the task stays put.
    response = client.patch(
        f"/api/v1/tasks/{task['id']}", json={"project_id": other_project},
        headers=owner_headers,
    )
    assert response.status_code == 200
    assert response.json()["project_id"] != other_project


def test_get_missing_task_is_404(client, owner_headers):
    assert client.get("/api/v1/tasks/99999", headers=owner_headers).status_code == 404
    assert client.patch(
        "/api/v1/tasks/99999", json={"status": "done"}, headers=owner_headers
    ).status_code == 404


def test_tasks_require_auth(client):
    assert client.get("/api/v1/tasks").status_code == 401
    assert client.post("/api/v1/tasks", json={"project_id": 1, "title": "x"}).status_code == 401
