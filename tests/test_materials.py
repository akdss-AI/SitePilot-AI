"""Phase 3 — materials CRUD, validation, references, stock alerts."""
from tests.conftest import make_material, make_site, make_supplier


def stock(client, headers, material_id):
    body = client.get(f"/api/v1/materials/{material_id}", headers=headers).json()
    return float(body["quantity_on_hand"])


def test_create_material_with_opening_stock(client, owner_headers):
    _, site_id = make_site(client, owner_headers)
    material = make_material(
        client, owner_headers, site_id, quantity_on_hand=50, reorder_level=20
    )
    assert float(material["quantity_on_hand"]) == 50
    assert material["is_low_stock"] is False


def test_material_on_nonexistent_site_is_404(client, owner_headers):
    response = client.post(
        "/api/v1/materials",
        json={"site_id": 99999, "name": "Cement", "unit": "bags"},
        headers=owner_headers,
    )
    assert response.status_code == 404


def test_material_on_other_users_site_is_404(client, owner_headers, other_headers):
    _, site_id = make_site(client, owner_headers)
    response = client.post(
        "/api/v1/materials",
        json={"site_id": site_id, "name": "Cement", "unit": "bags"},
        headers=other_headers,
    )
    assert response.status_code == 404


def test_preferred_supplier_must_be_own(client, owner_headers, other_headers):
    _, site_id = make_site(client, owner_headers)
    foreign_supplier = make_supplier(client, other_headers, name="Foreign Co")
    response = client.post(
        "/api/v1/materials",
        json={
            "site_id": site_id, "name": "Cement", "unit": "bags",
            "preferred_supplier_id": foreign_supplier,
        },
        headers=owner_headers,
    )
    assert response.status_code == 404  # cross-user reference rejected


def test_negative_quantities_are_422(client, owner_headers):
    _, site_id = make_site(client, owner_headers)
    for field in ("quantity_on_hand", "reorder_level"):
        response = client.post(
            "/api/v1/materials",
            json={"site_id": site_id, "name": "Cement", "unit": "bags", field: -5},
            headers=owner_headers,
        )
        assert response.status_code == 422, field


def test_duplicate_material_name_on_same_site_is_409(client, owner_headers):
    _, site_id = make_site(client, owner_headers)
    make_material(client, owner_headers, site_id)
    again = client.post(
        "/api/v1/materials",
        json={"site_id": site_id, "name": "Cement", "unit": "bags"},
        headers=owner_headers,
    )
    assert again.status_code == 409


def test_same_material_name_on_different_sites_is_allowed(client, owner_headers):
    _, site1 = make_site(client, owner_headers, site_name="Tower A")
    # second site on a second project for simplicity of helper
    _, site2 = make_site(client, owner_headers, project_name="Second Project", site_name="Tower B")
    make_material(client, owner_headers, site1)
    make_material(client, owner_headers, site2)  # 201 asserted by helper


def test_other_users_material_is_404(client, owner_headers, other_headers):
    _, site_id = make_site(client, owner_headers)
    material_id = make_material(client, owner_headers, site_id)["id"]
    assert client.get(f"/api/v1/materials/{material_id}", headers=other_headers).status_code == 404
    assert client.patch(
        f"/api/v1/materials/{material_id}", json={"name": "Hijack"}, headers=other_headers
    ).status_code == 404
    assert client.delete(
        f"/api/v1/materials/{material_id}", headers=other_headers
    ).status_code == 404


def test_stock_cannot_be_changed_via_material_update(client, owner_headers):
    _, site_id = make_site(client, owner_headers)
    material_id = make_material(
        client, owner_headers, site_id, quantity_on_hand=40
    )["id"]
    client.patch(
        f"/api/v1/materials/{material_id}",
        json={"quantity_on_hand": 9999},
        headers=owner_headers,
    )
    # quantity_on_hand is not an updatable field — stock is unchanged.
    assert stock(client, owner_headers, material_id) == 40


def test_update_material_reorder_level_and_delete(client, owner_headers):
    _, site_id = make_site(client, owner_headers)
    material_id = make_material(client, owner_headers, site_id)["id"]
    updated = client.patch(
        f"/api/v1/materials/{material_id}",
        json={"reorder_level": 15},
        headers=owner_headers,
    )
    assert updated.status_code == 200
    assert float(updated.json()["reorder_level"]) == 15
    assert client.delete(f"/api/v1/materials/{material_id}", headers=owner_headers).status_code == 204


def test_list_materials_filter_by_site(client, owner_headers):
    _, site1 = make_site(client, owner_headers, site_name="Tower A")
    _, site2 = make_site(client, owner_headers, project_name="P2", site_name="Tower B")
    make_material(client, owner_headers, site1, name="Cement")
    make_material(client, owner_headers, site2, name="Steel")
    filtered = client.get(f"/api/v1/materials?site_id={site1}", headers=owner_headers)
    assert [m["name"] for m in filtered.json()] == ["Cement"]
    foreign = client.get(f"/api/v1/materials?site_id={site2}", headers=owner_headers)
    assert len(foreign.json()) == 1  # own second site is fine


# ---- Stock alerts ----------------------------------------------------------

def test_low_stock_alert_boundary(client, owner_headers):
    """Alert when quantity <= reorder level (at the level counts as low)."""
    _, site_id = make_site(client, owner_headers)
    make_material(client, owner_headers, site_id, name="Cement",
                  quantity_on_hand=20, reorder_level=20)   # at level -> alert
    make_material(client, owner_headers, site_id, name="Steel",
                  quantity_on_hand=21, reorder_level=20)   # above -> no alert
    make_material(client, owner_headers, site_id, name="Sand",
                  quantity_on_hand=0, reorder_level=5)     # below -> alert
    alerts = client.get("/api/v1/materials/alerts/stock", headers=owner_headers)
    assert alerts.status_code == 200
    assert sorted(m["name"] for m in alerts.json()) == ["Cement", "Sand"]
    assert all(m["is_low_stock"] for m in alerts.json())


def test_stock_alerts_show_only_own_materials(client, owner_headers, other_headers):
    _, site_id = make_site(client, owner_headers)
    make_material(client, owner_headers, site_id, quantity_on_hand=0, reorder_level=5)
    alerts = client.get("/api/v1/materials/alerts/stock", headers=other_headers)
    assert alerts.json() == []
