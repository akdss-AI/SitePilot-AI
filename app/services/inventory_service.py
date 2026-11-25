"""Inventory business logic — Phase 3. No HTTP code here.

Ownership (same rule as Phase 2, extended through the relationship chain):
- Supplier:  supplier.owner_id == current user
- Material:  material.site.project.owner_id == current user
- Delivery:  delivery.material.site.project.owner_id == current user
Anything outside that chain is "not found" (404) — including when a user
references *another user's* supplier/material while creating a record.
That is what prevents cross-user references.

Stock integrity:
- Stock changes only in receive_delivery(): delivery status change and
  the stock increase are committed in ONE transaction. Any failure rolls
  both back. A delivery can leave 'pending' exactly once.
"""
from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.inventory import Delivery, DeliveryStatus, Material, Supplier
from app.models.project import Project, Site
from app.models.user import User
from app.schemas.inventory import (
    DeliveryCreate,
    DeliveryUpdate,
    MaterialCreate,
    MaterialUpdate,
    SupplierCreate,
    SupplierUpdate,
)
from app.services.project_service import get_owned_site


# ---- Suppliers -----------------------------------------------------------

def create_supplier(db: Session, owner: User, data: SupplierCreate) -> Supplier:
    duplicate = db.scalar(
        select(Supplier).where(
            Supplier.owner_id == owner.id, Supplier.name == data.name
        )
    )
    if duplicate is not None:
        raise AppError("You already have a supplier with this name.", 409)
    supplier = Supplier(owner_id=owner.id, **data.model_dump())
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


def list_suppliers(db: Session, owner: User) -> list[Supplier]:
    return list(
        db.scalars(
            select(Supplier).where(Supplier.owner_id == owner.id).order_by(Supplier.id)
        )
    )


def get_owned_supplier(db: Session, owner: User, supplier_id: int) -> Supplier:
    supplier = db.scalar(
        select(Supplier).where(
            Supplier.id == supplier_id, Supplier.owner_id == owner.id
        )
    )
    if supplier is None:
        raise AppError("Supplier not found.", 404)
    return supplier


def update_supplier(
    db: Session, owner: User, supplier_id: int, data: SupplierUpdate
) -> Supplier:
    supplier = get_owned_supplier(db, owner, supplier_id)
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] != supplier.name:
        duplicate = db.scalar(
            select(Supplier).where(
                Supplier.owner_id == owner.id,
                Supplier.name == changes["name"],
                Supplier.id != supplier.id,
            )
        )
        if duplicate is not None:
            raise AppError("You already have a supplier with this name.", 409)
    for field, value in changes.items():
        setattr(supplier, field, value)
    db.commit()
    db.refresh(supplier)
    return supplier


def delete_supplier(db: Session, owner: User, supplier_id: int) -> None:
    supplier = get_owned_supplier(db, owner, supplier_id)
    db.delete(supplier)
    try:
        db.commit()
    except IntegrityError:
        # Deliveries reference this supplier with a RESTRICT foreign key.
        db.rollback()
        raise AppError(
            "This supplier has deliveries and cannot be deleted.", 409
        )


# ---- Materials -----------------------------------------------------------

def _validate_preferred_supplier(db: Session, owner: User, supplier_id: int | None):
    """A preferred supplier, if given, must exist and belong to the user."""
    if supplier_id is not None:
        get_owned_supplier(db, owner, supplier_id)  # raises 404 otherwise


def create_material(db: Session, owner: User, data: MaterialCreate) -> Material:
    site = get_owned_site(db, owner, data.site_id)  # 404: bad/foreign site
    _validate_preferred_supplier(db, owner, data.preferred_supplier_id)
    duplicate = db.scalar(
        select(Material).where(
            Material.site_id == site.id, Material.name == data.name
        )
    )
    if duplicate is not None:
        raise AppError("This site already has a material with this name.", 409)
    material = Material(**data.model_dump())
    db.add(material)
    db.commit()
    db.refresh(material)
    return material


def list_materials(
    db: Session, owner: User, site_id: int | None = None
) -> list[Material]:
    query = (
        select(Material)
        .join(Site, Material.site_id == Site.id)
        .join(Project, Site.project_id == Project.id)
        .where(Project.owner_id == owner.id)
        .order_by(Material.id)
    )
    if site_id is not None:
        get_owned_site(db, owner, site_id)  # filtering by a foreign site is 404
        query = query.where(Material.site_id == site_id)
    return list(db.scalars(query))


def get_owned_material(db: Session, owner: User, material_id: int) -> Material:
    material = db.scalar(
        select(Material)
        .join(Site, Material.site_id == Site.id)
        .join(Project, Site.project_id == Project.id)
        .where(Material.id == material_id, Project.owner_id == owner.id)
    )
    if material is None:
        raise AppError("Material not found.", 404)
    return material


def update_material(
    db: Session, owner: User, material_id: int, data: MaterialUpdate
) -> Material:
    material = get_owned_material(db, owner, material_id)
    changes = data.model_dump(exclude_unset=True)
    if "preferred_supplier_id" in changes:
        _validate_preferred_supplier(db, owner, changes["preferred_supplier_id"])
    if "name" in changes and changes["name"] != material.name:
        duplicate = db.scalar(
            select(Material).where(
                Material.site_id == material.site_id,
                Material.name == changes["name"],
                Material.id != material.id,
            )
        )
        if duplicate is not None:
            raise AppError("This site already has a material with this name.", 409)
    for field, value in changes.items():
        setattr(material, field, value)
    db.commit()
    db.refresh(material)
    return material


def delete_material(db: Session, owner: User, material_id: int) -> None:
    material = get_owned_material(db, owner, material_id)
    db.delete(material)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError(
            "This material has deliveries and cannot be deleted.", 409
        )


def list_stock_alerts(db: Session, owner: User) -> list[Material]:
    """Materials at or below their reorder level, across all the user's sites."""
    return [
        m for m in list_materials(db, owner) if m.is_low_stock
    ]


# ---- Deliveries -----------------------------------------------------------

def create_delivery(db: Session, owner: User, data: DeliveryCreate) -> Delivery:
    # Both references must belong to the caller — a foreign or missing
    # material/supplier is a 404, and no delivery row is created.
    get_owned_material(db, owner, data.material_id)
    get_owned_supplier(db, owner, data.supplier_id)
    delivery = Delivery(**data.model_dump())  # status defaults to pending
    db.add(delivery)
    db.commit()
    db.refresh(delivery)
    return delivery


def list_deliveries(
    db: Session,
    owner: User,
    material_id: int | None = None,
    status: DeliveryStatus | None = None,
) -> list[Delivery]:
    query = (
        select(Delivery)
        .join(Material, Delivery.material_id == Material.id)
        .join(Site, Material.site_id == Site.id)
        .join(Project, Site.project_id == Project.id)
        .where(Project.owner_id == owner.id)
        .order_by(Delivery.id)
    )
    if material_id is not None:
        get_owned_material(db, owner, material_id)
        query = query.where(Delivery.material_id == material_id)
    if status is not None:
        query = query.where(Delivery.status == status)
    return list(db.scalars(query))


def get_owned_delivery(db: Session, owner: User, delivery_id: int) -> Delivery:
    delivery = db.scalar(
        select(Delivery)
        .join(Material, Delivery.material_id == Material.id)
        .join(Site, Material.site_id == Site.id)
        .join(Project, Site.project_id == Project.id)
        .where(Delivery.id == delivery_id, Project.owner_id == owner.id)
    )
    if delivery is None:
        raise AppError("Delivery not found.", 404)
    return delivery


def update_delivery(
    db: Session, owner: User, delivery_id: int, data: DeliveryUpdate
) -> Delivery:
    delivery = get_owned_delivery(db, owner, delivery_id)
    if delivery.status != DeliveryStatus.PENDING:
        raise AppError(
            f"A {delivery.status.value} delivery can no longer be modified.", 409
        )
    changes = data.model_dump(exclude_unset=True)
    target_status = changes.pop("status", None)
    if target_status == DeliveryStatus.RECEIVED:
        # Receiving must go through the receive endpoint so stock is
        # updated transactionally — never as a plain field edit.
        raise AppError(
            "Use POST /deliveries/{id}/receive to receive a delivery.", 422
        )
    if "supplier_id" in changes:
        get_owned_supplier(db, owner, changes["supplier_id"])
    for field, value in changes.items():
        setattr(delivery, field, value)
    if target_status == DeliveryStatus.CANCELLED:
        delivery.status = DeliveryStatus.CANCELLED  # no stock change, ever
    db.commit()
    db.refresh(delivery)
    return delivery


def delete_delivery(db: Session, owner: User, delivery_id: int) -> None:
    delivery = get_owned_delivery(db, owner, delivery_id)
    if delivery.status == DeliveryStatus.RECEIVED:
        raise AppError(
            "A received delivery is a stock record and cannot be deleted.", 409
        )
    db.delete(delivery)
    db.commit()


def receive_delivery(db: Session, owner: User, delivery_id: int) -> Delivery:
    """THE stock-changing operation.

    State machine: pending -> received, exactly once.
    - already received -> 409, stock untouched (no double counting)
    - cancelled        -> 409, stock untouched
    The status change and the stock increase share one commit: if either
    fails, the transaction rolls back and neither is saved.
    """
    delivery = get_owned_delivery(db, owner, delivery_id)
    if delivery.status == DeliveryStatus.RECEIVED:
        raise AppError("This delivery has already been received.", 409)
    if delivery.status == DeliveryStatus.CANCELLED:
        raise AppError("A cancelled delivery cannot be received.", 409)

    material = delivery.material
    try:
        delivery.status = DeliveryStatus.RECEIVED
        delivery.received_date = date.today()
        material.quantity_on_hand = material.quantity_on_hand + delivery.quantity
        db.commit()
    except Exception:
        db.rollback()
        raise AppError("Receiving the delivery failed; nothing was changed.", 500)
    db.refresh(delivery)
    db.refresh(material)
    return delivery
