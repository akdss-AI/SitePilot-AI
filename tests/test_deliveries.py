"""Phase 3 — deliveries: creation rules, receiving, stock, rollback."""
import pytest

from tests.conftest import make_material, make_site, make_supplier
from tests.test_materials import stock


def setup_inventory(client, headers, opening=10):
    _, site_id = make_site(client, headers)
    supplier_id = make_supplier(client, headers)
    material = make_material(
        client, headers, site_id, quantity_on_hand=opening, reorder_level=5
    )
    return site_id, supplier_id, material["id"]


def make_delivery(client, headers, material_id, supplier_id, quantity=200, **kw):
    payload = {
        "material_id": material_id, "supplier_id": supplier_id,
        "quantity": quantity, **kw,
    }
    return client.post("/api/v1/deliveries", json=payload, headers=headers)


def test_create_delivery_is_pending_and_does_not_change_stock(client, owner_headers):
    _, supplier_id, material_id = setup_inventory(client, owner_headers)
    response = make_delivery(client, owner_headers, material_id, supplier_id)
    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    assert stock(client, owner_headers, material_id) == 10  # unchanged


def test_receive_delivery_updates_stock_once(client, owner_headers):
    _, supplier_id, material_id = setup_inventory(client, owner_headers)
    delivery_id = make_delivery(client, owner_headers, material_id, supplier_id).json()["id"]
    received = client.post(f"/api/v1/deliveries/{delivery_id}/receive", headers=owner_headers)
    assert received.status_code == 200
    assert received.json()["status"] == "received"
    assert received.json()["received_date"] is not None
    assert stock(client, owner_headers, material_id) == 210  # 10 + 200


def test_receiving_twice_is_409_and_stock_counted_once(client, owner_headers):
    _, supplier_id, material_id = setup_inventory(client, owner_headers)
    delivery_id = make_delivery(client, owner_headers, material_id, supplier_id).json()["id"]
    assert client.post(f"/api/v1/deliveries/{delivery_id}/receive", headers=owner_headers).status_code == 200
    again = client.post(f"/api/v1/deliveries/{delivery_id}/receive", headers=owner_headers)
    assert again.status_code == 409
    assert stock(client, owner_headers, material_id) == 210  # not 410


def test_cancelled_delivery_cannot_be_received_and_never_affects_stock(client, owner_headers):
    _, supplier_id, material_id = setup_inventory(client, owner_headers)
    delivery_id = make_delivery(client, owner_headers, material_id, supplier_id).json()["id"]
    cancelled = client.patch(
        f"/api/v1/deliveries/{delivery_id}", json={"status": "cancelled"}, headers=owner_headers
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert client.post(f"/api/v1/deliveries/{delivery_id}/receive", headers=owner_headers).status_code == 409
    assert stock(client, owner_headers, material_id) == 10


def test_pending_delivery_status_cannot_jump_to_received_via_patch(client, owner_headers):
    _, supplier_id, material_id = setup_inventory(client, owner_headers)
    delivery_id = make_delivery(client, owner_headers, material_id, supplier_id).json()["id"]
    response = client.patch(
        f"/api/v1/deliveries/{delivery_id}", json={"status": "received"}, headers=owner_headers
    )
    assert response.status_code == 422  # must use the receive endpoint
    assert stock(client, owner_headers, material_id) == 10


def test_received_delivery_cannot_be_modified_or_deleted(client, owner_headers):
    _, supplier_id, material_id = setup_inventory(client, owner_headers)
    delivery_id = make_delivery(client, owner_headers, material_id, supplier_id).json()["id"]
    client.post(f"/api/v1/deliveries/{delivery_id}/receive", headers=owner_headers)
    assert client.patch(
        f"/api/v1/deliveries/{delivery_id}", json={"quantity": 1}, headers=owner_headers
    ).status_code == 409
    assert client.delete(f"/api/v1/deliveries/{delivery_id}", headers=owner_headers).status_code == 409


def test_invalid_references_are_404(client, owner_headers, other_headers):
    _, supplier_id, material_id = setup_inventory(client, owner_headers)
    # nonexistent material / supplier
    assert make_delivery(client, owner_headers, 99999, supplier_id).status_code == 404
    assert make_delivery(client, owner_headers, material_id, 99999).status_code == 404
    # another user's material / supplier (cross-user references)
    assert make_delivery(client, other_headers, material_id, supplier_id).status_code == 404
    foreign_supplier = make_supplier(client, other_headers, name="Foreign Co")
    assert make_delivery(client, owner_headers, material_id, foreign_supplier).status_code == 404


def test_invalid_quantities_and_price_are_422(client, owner_headers):
    _, supplier_id, material_id = setup_inventory(client, owner_headers)
    assert make_delivery(client, owner_headers, material_id, supplier_id, quantity=0).status_code == 422
    assert make_delivery(client, owner_headers, material_id, supplier_id, quantity=-50).status_code == 422
    assert make_delivery(client, owner_headers, material_id, supplier_id, unit_price=-1).status_code == 422


def test_other_user_cannot_receive_or_read_delivery(client, owner_headers, other_headers):
    _, supplier_id, material_id = setup_inventory(client, owner_headers)
    delivery_id = make_delivery(client, owner_headers, material_id, supplier_id).json()["id"]
    assert client.get(f"/api/v1/deliveries/{delivery_id}", headers=other_headers).status_code == 404
    assert client.post(f"/api/v1/deliveries/{delivery_id}/receive", headers=other_headers).status_code == 404
    assert stock(client, owner_headers, material_id) == 10


def test_fractional_quantities_use_exact_decimal_math(client, owner_headers):
    _, supplier_id, material_id = setup_inventory(client, owner_headers, opening=0)
    delivery_id = make_delivery(
        client, owner_headers, material_id, supplier_id, quantity=12.5
    ).json()["id"]
    client.post(f"/api/v1/deliveries/{delivery_id}/receive", headers=owner_headers)
    assert stock(client, owner_headers, material_id) == 12.5  # no float drift


def test_supplier_or_material_with_deliveries_cannot_be_deleted(client, owner_headers):
    _, supplier_id, material_id = setup_inventory(client, owner_headers)
    make_delivery(client, owner_headers, material_id, supplier_id)
    assert client.delete(f"/api/v1/suppliers/{supplier_id}", headers=owner_headers).status_code == 409
    assert client.delete(f"/api/v1/materials/{material_id}", headers=owner_headers).status_code == 409


def test_deleting_supplier_clears_it_as_preferred_supplier(client, owner_headers):
    _, site_id = make_site(client, owner_headers)
    supplier_id = make_supplier(client, owner_headers)
    material = make_material(client, owner_headers, site_id, preferred_supplier_id=supplier_id)
    assert material["preferred_supplier_id"] == supplier_id
    assert client.delete(f"/api/v1/suppliers/{supplier_id}", headers=owner_headers).status_code == 204
    after = client.get(f"/api/v1/materials/{material['id']}", headers=owner_headers)
    assert after.json()["preferred_supplier_id"] is None  # SET NULL worked


# ---- Transaction rollback ---------------------------------------------------

def test_failed_receive_rolls_back_status_and_stock(client, owner_headers, monkeypatch):
    """If the commit fails mid-receive, neither the delivery status nor
    the stock may change — the transaction must roll back atomically."""
    from sqlalchemy.orm import Session

    from app.core.errors import AppError
    from app.db.session import SessionLocal
    from app.models.user import User
    from app.services import inventory_service

    _, supplier_id, material_id = setup_inventory(client, owner_headers)
    delivery_id = make_delivery(client, owner_headers, material_id, supplier_id).json()["id"]

    db = SessionLocal()
    try:
        owner = db.query(User).first()
        real_commit = Session.commit
        monkeypatch.setattr(
            Session, "commit",
            lambda self: (_ for _ in ()).throw(RuntimeError("simulated DB failure")),
        )
        with pytest.raises(AppError):
            inventory_service.receive_delivery(
                db, owner, delivery_id
            )
        monkeypatch.setattr(Session, "commit", real_commit)
    finally:
        db.close()

    # Re-read through the API (fresh session): nothing may have changed.
    delivery = client.get(f"/api/v1/deliveries/{delivery_id}", headers=owner_headers)
    assert delivery.json()["status"] == "pending"
    assert stock(client, owner_headers, material_id) == 10

    # And the delivery is still receivable afterwards — state is consistent.
    assert client.post(
        f"/api/v1/deliveries/{delivery_id}/receive", headers=owner_headers
    ).status_code == 200
    assert stock(client, owner_headers, material_id) == 210
