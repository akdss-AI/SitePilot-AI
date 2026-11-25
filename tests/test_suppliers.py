"""Phase 3 — supplier CRUD, duplicates, ownership."""
from tests.conftest import make_supplier


def test_create_and_read_supplier(client, owner_headers):
    supplier_id = make_supplier(client, owner_headers)
    fetched = client.get(f"/api/v1/suppliers/{supplier_id}", headers=owner_headers)
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Ali Traders"


def test_unauthenticated_is_401(client):
    assert client.get("/api/v1/suppliers").status_code == 401
    assert client.post("/api/v1/suppliers", json={"name": "X"}).status_code == 401


def test_duplicate_name_same_owner_is_409(client, owner_headers):
    make_supplier(client, owner_headers)
    again = client.post(
        "/api/v1/suppliers", json={"name": "Ali Traders"}, headers=owner_headers
    )
    assert again.status_code == 409


def test_same_name_different_owner_is_allowed(client, owner_headers, other_headers):
    make_supplier(client, owner_headers)
    assert make_supplier(client, other_headers)  # no exception = 201


def test_list_shows_only_own_suppliers(client, owner_headers, other_headers):
    make_supplier(client, owner_headers)
    make_supplier(client, other_headers, name="Other Supplier")
    mine = client.get("/api/v1/suppliers", headers=owner_headers)
    assert [s["name"] for s in mine.json()] == ["Ali Traders"]


def test_other_users_supplier_is_404_for_read_update_delete(client, owner_headers, other_headers):
    supplier_id = make_supplier(client, owner_headers)
    assert client.get(f"/api/v1/suppliers/{supplier_id}", headers=other_headers).status_code == 404
    assert client.patch(
        f"/api/v1/suppliers/{supplier_id}", json={"name": "Hijack"}, headers=other_headers
    ).status_code == 404
    assert client.delete(
        f"/api/v1/suppliers/{supplier_id}", headers=other_headers
    ).status_code == 404


def test_update_and_delete_supplier(client, owner_headers):
    supplier_id = make_supplier(client, owner_headers)
    updated = client.patch(
        f"/api/v1/suppliers/{supplier_id}",
        json={"phone": "0300-0000000"},
        headers=owner_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["phone"] == "0300-0000000"
    assert client.delete(f"/api/v1/suppliers/{supplier_id}", headers=owner_headers).status_code == 204
    assert client.get(f"/api/v1/suppliers/{supplier_id}", headers=owner_headers).status_code == 404


def test_invalid_supplier_email_is_422(client, owner_headers):
    response = client.post(
        "/api/v1/suppliers",
        json={"name": "Bad Email Co", "email": "nope"},
        headers=owner_headers,
    )
    assert response.status_code == 422
