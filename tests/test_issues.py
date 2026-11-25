"""Phase 4 — site issues: creation rules, enum validation, ownership."""
from tests.conftest import make_site
from tests.test_tasks import user_id


def make_issue(client, headers, site_id, **overrides):
    payload = {
        "site_id": site_id,
        "title": "Scaffolding loose on level 2",
        "category": "safety",
        **overrides,
    }
    return client.post("/api/v1/issues", json=payload, headers=headers)


def setup_issue(client, headers, **overrides):
    _, site_id = make_site(client, headers)
    response = make_issue(client, headers, site_id, **overrides)
    assert response.status_code == 201, response.text
    return site_id, response.json()


# ---- Creation ---------------------------------------------------------------

def test_create_issue_defaults(client, owner_headers):
    site_id, issue = setup_issue(client, owner_headers, priority="high")
    assert issue["site_id"] == site_id
    assert issue["category"] == "safety"
    assert issue["priority"] == "high"
    assert issue["status"] == "open"  # default
    assert issue["reported_by"] == user_id(client, owner_headers)


def test_create_issue_reported_by_is_server_set_not_client_supplied(client, owner_headers):
    _, site_id = make_site(client, owner_headers)
    owner = user_id(client, owner_headers)
    response = make_issue(
        client, owner_headers, site_id, reported_by=99999
    )
    assert response.status_code == 201, response.text
    # The payload value is ignored; the reporter is the authenticated user.
    assert response.json()["reported_by"] == owner


def test_create_issue_requires_a_site(client, owner_headers):
    assert client.post(
        "/api/v1/issues", json={"title": "No site", "category": "safety"},
        headers=owner_headers,
    ).status_code == 422


def test_create_issue_with_foreign_or_missing_site_is_404(client, owner_headers, other_headers):
    _, foreign_site = make_site(client, other_headers, "Other Project", "Other Site")
    assert make_issue(client, owner_headers, 99999).status_code == 404
    assert make_issue(client, owner_headers, foreign_site).status_code == 404


# ---- Enum validation ----------------------------------------------------------

def test_invalid_issue_enums_are_422(client, owner_headers):
    _, site_id = make_site(client, owner_headers)
    assert make_issue(client, owner_headers, site_id, category="urgent").status_code == 422
    assert make_issue(client, owner_headers, site_id, priority="severe").status_code == 422
    assert make_issue(client, owner_headers, site_id, status="pending").status_code == 422


def test_all_issue_categories_priorities_and_statuses_accepted(client, owner_headers):
    _, site_id = make_site(client, owner_headers)
    for category in ["safety", "quality", "material", "labour", "weather", "equipment", "other"]:
        assert make_issue(
            client, owner_headers, site_id, category=category
        ).status_code == 201, category
    for priority in ["low", "medium", "high", "critical"]:
        assert make_issue(
            client, owner_headers, site_id, priority=priority
        ).status_code == 201, priority
    for status in ["open", "in_progress", "resolved", "closed"]:
        assert make_issue(
            client, owner_headers, site_id, status=status
        ).status_code == 201, status


def test_patch_issue_with_invalid_enum_is_422(client, owner_headers):
    _, issue = setup_issue(client, owner_headers)
    assert client.patch(
        f"/api/v1/issues/{issue['id']}", json={"category": "urgent"},
        headers=owner_headers,
    ).status_code == 422
    assert client.patch(
        f"/api/v1/issues/{issue['id']}", json={"priority": "severe"},
        headers=owner_headers,
    ).status_code == 422
    assert client.patch(
        f"/api/v1/issues/{issue['id']}", json={"status": "pending"},
        headers=owner_headers,
    ).status_code == 422


# ---- PATCH --------------------------------------------------------------------

def test_patch_issue_fields(client, owner_headers):
    _, issue = setup_issue(client, owner_headers)
    updated = client.patch(
        f"/api/v1/issues/{issue['id']}",
        json={
            "title": "Scaffolding secured",
            "description": "Tightened all couplers; re-inspected",
            "category": "equipment",
            "priority": "critical",
            "status": "resolved",
        },
        headers=owner_headers,
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["title"] == "Scaffolding secured"
    assert body["description"] == "Tightened all couplers; re-inspected"
    assert body["category"] == "equipment"
    assert body["priority"] == "critical"
    assert body["status"] == "resolved"
    # reported_by never changes through PATCH.
    assert body["reported_by"] == issue["reported_by"]


def test_patch_issue_cannot_change_site_or_reporter(client, owner_headers):
    _, issue = setup_issue(client, owner_headers)
    _, other_site = make_site(client, owner_headers, "Second Project", "Second Site")
    response = client.patch(
        f"/api/v1/issues/{issue['id']}",
        json={"site_id": other_site, "reported_by": 99999},
        headers=owner_headers,
    )
    assert response.status_code == 200
    assert response.json()["site_id"] == issue["site_id"]
    assert response.json()["reported_by"] == issue["reported_by"]


# ---- Ownership / listing ------------------------------------------------------

def test_other_user_gets_404_on_get_list_and_patch(client, owner_headers, other_headers):
    _, issue = setup_issue(client, owner_headers)
    assert client.get(f"/api/v1/issues/{issue['id']}", headers=other_headers).status_code == 404
    assert client.get("/api/v1/issues", headers=other_headers).json() == []
    assert client.patch(
        f"/api/v1/issues/{issue['id']}", json={"status": "closed"},
        headers=other_headers,
    ).status_code == 404
    assert client.get(f"/api/v1/issues/{issue['id']}", headers=owner_headers).json()["status"] == "open"


def test_list_returns_only_callers_own_issues(client, owner_headers, other_headers):
    setup_issue(client, owner_headers, title="Owner issue")
    setup_issue(client, other_headers, title="Other issue")
    assert [i["title"] for i in client.get("/api/v1/issues", headers=owner_headers).json()] == ["Owner issue"]
    assert [i["title"] for i in client.get("/api/v1/issues", headers=other_headers).json()] == ["Other issue"]


def test_list_issues_filters_by_site_category_priority_status(client, owner_headers):
    _, site_id = make_site(client, owner_headers)
    make_issue(client, owner_headers, site_id, title="A", category="safety", priority="critical")
    make_issue(client, owner_headers, site_id, title="B", category="quality", priority="low", status="resolved")
    assert [i["title"] for i in client.get(
        f"/api/v1/issues?site_id={site_id}", headers=owner_headers).json()] == ["A", "B"]
    assert [i["title"] for i in client.get(
        "/api/v1/issues?category=safety", headers=owner_headers).json()] == ["A"]
    assert [i["title"] for i in client.get(
        "/api/v1/issues?priority=critical", headers=owner_headers).json()] == ["A"]
    assert [i["title"] for i in client.get(
        "/api/v1/issues?status=resolved", headers=owner_headers).json()] == ["B"]
    assert client.get(
        "/api/v1/issues?site_id=99999", headers=owner_headers
    ).status_code == 404


def test_get_missing_issue_is_404(client, owner_headers):
    assert client.get("/api/v1/issues/99999", headers=owner_headers).status_code == 404
    assert client.patch(
        "/api/v1/issues/99999", json={"status": "closed"}, headers=owner_headers
    ).status_code == 404


def test_issues_require_auth(client):
    assert client.get("/api/v1/issues").status_code == 401
    assert client.post(
        "/api/v1/issues", json={"site_id": 1, "title": "x", "category": "safety"}
    ).status_code == 401
