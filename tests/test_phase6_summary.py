"""Phase 6 — daily summary, dashboard, cookie page auth, landing + SEO."""
from datetime import date, timedelta

from tests.conftest import (
    PASSWORD,
    make_material,
    make_site,
    make_supplier,
)


def _seed_project(client, headers):
    """One project with known data: 1 overdue, 1 due today, 1 upcoming,
    1 done-past (not overdue), 1 low-stock + 1 OK material, 1 pending
    delivery, and open issues of mixed priority (critical, high, low)
    plus one resolved issue (not open). Returns project_id, site_id."""
    today = date.today()
    project_id, site_id = make_site(client, headers)

    def task(title, due, status="todo"):
        payload = {"project_id": project_id, "site_id": site_id, "title": title}
        if due is not None:
            payload["due_date"] = due.isoformat()
        if status != "todo":
            payload["status"] = status
        r = client.post("/api/v1/tasks", json=payload, headers=headers)
        assert r.status_code == 201, r.text

    task("Overdue plastering", today - timedelta(days=2))
    task("Due today inspection", today)
    task("Upcoming steel fixing", today + timedelta(days=3))
    task("Far future handover", today + timedelta(days=30))
    task("Done late task", today - timedelta(days=5), status="done")
    task("No due date task", None)

    make_material(client, headers, site_id, name="Cement", unit="bags",
                  quantity_on_hand="5", reorder_level="10")   # low stock
    make_material(client, headers, site_id, name="Sand", unit="kg",
                  quantity_on_hand="500", reorder_level="10")  # OK
    supplier_id = make_supplier(client, headers)
    # Pending delivery against the OK material (id lookup via list).
    materials = client.get("/api/v1/materials", headers=headers).json()
    sand = next(m for m in materials if m["name"] == "Sand")
    r = client.post("/api/v1/deliveries", json={
        "material_id": sand["id"], "supplier_id": supplier_id, "quantity": "100",
    }, headers=headers)
    assert r.status_code == 201, r.text

    def issue(title, priority, status="open"):
        r = client.post("/api/v1/issues", json={
            "site_id": site_id, "title": title, "category": "safety",
            "priority": priority, "status": status,
        }, headers=headers)
        assert r.status_code == 201, r.text

    issue("Scaffolding unsafe", "critical")
    issue("Cracked beam", "high")
    issue("Minor paint touch-up", "low")
    issue("Old resolved issue", "critical", status="resolved")
    return project_id, site_id


def _titles(items):
    return [i["title"] for i in items]


# ---- Summary endpoint ----------------------------------------------------

def test_summary_counts_match_seeded_data(client, owner_headers):
    project_id, _ = _seed_project(client, owner_headers)
    r = client.get(f"/api/v1/projects/{project_id}/summary/today",
                   headers=owner_headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["project_id"] == project_id
    assert data["date"] == date.today().isoformat()
    assert data["overdue_count"] == 1
    assert _titles(data["overdue_tasks"]) == ["Overdue plastering"]
    assert data["due_today_count"] == 1
    assert _titles(data["due_today_tasks"]) == ["Due today inspection"]
    assert data["upcoming_count"] == 1  # only the +3d task; +30d is outside 7d
    assert _titles(data["upcoming_tasks"]) == ["Upcoming steel fixing"]
    assert data["upcoming_days"] == 7
    assert data["low_stock_count"] == 1
    assert [m["name"] for m in data["low_stock_materials"]] == ["Cement"]
    assert data["open_issues_count"] == 3  # resolved one excluded
    assert data["critical_high_issues_count"] == 2
    # Critical first, then high, then low.
    assert [i["priority"] for i in data["open_issues"]] == [
        "critical", "high", "low"]
    assert data["pending_deliveries_count"] == 1
    assert data["recent_updates_count"] == 0


def test_summary_other_users_project_is_404(client, owner_headers, other_headers):
    project_id, _ = _seed_project(client, owner_headers)
    r = client.get(f"/api/v1/projects/{project_id}/summary/today",
                   headers=other_headers)
    assert r.status_code == 404
    assert client.get("/api/v1/projects/99999/summary/today",
                      headers=owner_headers).status_code == 404


def test_summary_requires_auth(client, owner_headers):
    project_id, _ = _seed_project(client, owner_headers)
    assert client.get(f"/api/v1/projects/{project_id}/summary/today").status_code == 401


def test_summary_empty_project_is_all_zero(client, owner_headers):
    project_id, _ = make_site(client, owner_headers)
    data = client.get(f"/api/v1/projects/{project_id}/summary/today",
                      headers=owner_headers).json()
    assert data["overdue_count"] == 0
    assert data["low_stock_count"] == 0
    assert data["open_issues_count"] == 0
    assert data["pending_deliveries_count"] == 0


# ---- Cookie login + dashboard pages --------------------------------------

def _login_via_form(client, email="owner@example.com"):
    return client.post("/login", data={"username": email, "password": PASSWORD},
                       follow_redirects=False)


def test_login_form_sets_cookie_and_dashboard_renders(client, owner_headers):
    # owner_headers fixture already registered owner@example.com.
    r = _login_via_form(client)
    assert r.status_code == 303, r.text
    assert r.headers["location"] == "/dashboard"
    assert "sitepilot_token" in r.headers.get("set-cookie", "")
    assert "HttpOnly" in r.headers.get("set-cookie", "")
    project_id, _ = _seed_project(client, owner_headers)
    # The TestClient keeps the cookie set by the login response.
    page = client.get("/dashboard")
    assert page.status_code == 200, page.text
    assert "Riverside Villas" in page.text
    assert "Overdue plastering" in page.text
    assert "Cement" in page.text
    assert "Scaffolding unsafe" in page.text


def test_login_with_wrong_password_shows_error(client, owner_headers):
    r = client.post("/login", data={"username": "owner@example.com",
                                    "password": "wrong-password"},
                    follow_redirects=False)
    assert r.status_code == 401
    assert "Invalid email or password" in r.text


def test_dashboard_without_login_redirects_to_login(client):
    r = client.get("/dashboard", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/login"


def test_login_page_renders(client):
    r = client.get("/login")
    assert r.status_code == 200
    assert "<form" in r.text
    assert "password" in r.text.lower()


def test_project_detail_page_renders_summary(client, owner_headers):
    project_id, _ = _seed_project(client, owner_headers)
    _login_via_form(client)
    page = client.get(f"/projects/{project_id}")
    assert page.status_code == 200, page.text
    assert "Riverside Villas" in page.text
    assert "Overdue plastering" in page.text
    assert "Due today inspection" in page.text


def test_project_detail_other_users_project_is_404(client, owner_headers, other_headers):
    project_id, _ = _seed_project(client, owner_headers)
    _login_via_form(client, email="other@example.com")
    assert client.get(f"/projects/{project_id}").status_code == 404


# ---- Landing page + SEO --------------------------------------------------

def test_landing_has_pricing_tiers_meta_and_og(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Starter" in r.text
    assert "Professional" in r.text
    assert "Business" in r.text
    assert "$29" in r.text and "$79" in r.text and "$199" in r.text
    assert "manual" in r.text.lower()  # billing is manual in v1
    assert 'name="description"' in r.text
    assert 'property="og:title"' in r.text
    assert 'property="og:description"' in r.text
    assert 'property="og:type"' in r.text
    assert "I build simple AI-powered operations systems" in r.text
    assert "Daily summary" in r.text or "daily summary" in r.text.lower()


def test_sitemap_lists_public_pages(client):
    r = client.get("/sitemap.xml")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/xml")
    assert r.text.startswith("<?xml")
    assert "<loc>http://testserver/</loc>" in r.text
    assert "<loc>http://testserver/login</loc>" in r.text


def test_robots_allows_all_and_points_at_sitemap(client):
    r = client.get("/robots.txt")
    assert r.status_code == 200
    assert "User-agent: *" in r.text
    assert "Allow: /" in r.text
    assert "Sitemap: http://testserver/sitemap.xml" in r.text
