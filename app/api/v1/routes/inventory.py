"""Inventory routes — Phase 3. Thin: all rules live in inventory_service.

Route order matters: /materials/alerts/stock is declared BEFORE
/materials/{material_id}, otherwise "alerts" would be treated as an id.
"""
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.inventory import DeliveryStatus
from app.models.user import User
from app.schemas.inventory import (
    DeliveryCreate,
    DeliveryOut,
    DeliveryUpdate,
    MaterialCreate,
    MaterialOut,
    MaterialUpdate,
    SupplierCreate,
    SupplierOut,
    SupplierUpdate,
)
from app.services import inventory_service

router = APIRouter(tags=["inventory"])


# ---- Suppliers ----------------------------------------------------------

@router.post("/suppliers", response_model=SupplierOut, status_code=201)
def create_supplier(data: SupplierCreate, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    return inventory_service.create_supplier(db, current_user, data)


@router.get("/suppliers", response_model=list[SupplierOut])
def list_suppliers(db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    return inventory_service.list_suppliers(db, current_user)


@router.get("/suppliers/{supplier_id}", response_model=SupplierOut)
def get_supplier(supplier_id: int, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    return inventory_service.get_owned_supplier(db, current_user, supplier_id)


@router.patch("/suppliers/{supplier_id}", response_model=SupplierOut)
def update_supplier(supplier_id: int, data: SupplierUpdate,
                    db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    return inventory_service.update_supplier(db, current_user, supplier_id, data)


@router.delete("/suppliers/{supplier_id}", status_code=204)
def delete_supplier(supplier_id: int, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    inventory_service.delete_supplier(db, current_user, supplier_id)
    return Response(status_code=204)


# ---- Materials ------------------------------------------------------------

@router.post("/materials", response_model=MaterialOut, status_code=201)
def create_material(data: MaterialCreate, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    return inventory_service.create_material(db, current_user, data)


@router.get("/materials/alerts/stock", response_model=list[MaterialOut])
def stock_alerts(db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    return inventory_service.list_stock_alerts(db, current_user)


@router.get("/materials", response_model=list[MaterialOut])
def list_materials(site_id: int | None = None, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    return inventory_service.list_materials(db, current_user, site_id)


@router.get("/materials/{material_id}", response_model=MaterialOut)
def get_material(material_id: int, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    return inventory_service.get_owned_material(db, current_user, material_id)


@router.patch("/materials/{material_id}", response_model=MaterialOut)
def update_material(material_id: int, data: MaterialUpdate,
                    db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    return inventory_service.update_material(db, current_user, material_id, data)


@router.delete("/materials/{material_id}", status_code=204)
def delete_material(material_id: int, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    inventory_service.delete_material(db, current_user, material_id)
    return Response(status_code=204)


# ---- Deliveries -----------------------------------------------------------

@router.post("/deliveries", response_model=DeliveryOut, status_code=201)
def create_delivery(data: DeliveryCreate, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    return inventory_service.create_delivery(db, current_user, data)


@router.get("/deliveries", response_model=list[DeliveryOut])
def list_deliveries(material_id: int | None = None,
                    status: DeliveryStatus | None = None,
                    db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    return inventory_service.list_deliveries(db, current_user, material_id, status)


@router.get("/deliveries/{delivery_id}", response_model=DeliveryOut)
def get_delivery(delivery_id: int, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    return inventory_service.get_owned_delivery(db, current_user, delivery_id)


@router.patch("/deliveries/{delivery_id}", response_model=DeliveryOut)
def update_delivery(delivery_id: int, data: DeliveryUpdate,
                    db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    return inventory_service.update_delivery(db, current_user, delivery_id, data)


@router.delete("/deliveries/{delivery_id}", status_code=204)
def delete_delivery(delivery_id: int, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    inventory_service.delete_delivery(db, current_user, delivery_id)
    return Response(status_code=204)


@router.post("/deliveries/{delivery_id}/receive", response_model=DeliveryOut)
def receive_delivery(delivery_id: int, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    return inventory_service.receive_delivery(db, current_user, delivery_id)
