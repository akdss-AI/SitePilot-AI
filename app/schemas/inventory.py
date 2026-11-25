"""Inventory schemas — Phase 3 validation boundary.

Quantities and prices are Decimal, never float: floats cannot represent
money/stock values exactly (0.1 + 0.2 != 0.3), Decimals can.
"""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.inventory import DeliveryStatus


def _clean_name(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("name must not be blank")
    return v


# ---- Suppliers ----------------------------------------------------------

class SupplierCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    contact_person: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=50)
    email: EmailStr | None = None
    notes: str | None = None

    _name = field_validator("name")(_clean_name)


class SupplierUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    contact_person: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=50)
    email: EmailStr | None = None
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, v):
        return _clean_name(v) if v is not None else v


class SupplierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    name: str
    contact_person: str | None
    phone: str | None
    email: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


# ---- Materials ----------------------------------------------------------

class MaterialCreate(BaseModel):
    site_id: int
    name: str = Field(min_length=1, max_length=200)
    unit: str = Field(min_length=1, max_length=30)
    # Opening stock. After creation, stock changes only via deliveries.
    quantity_on_hand: Decimal = Field(default=Decimal("0"), ge=0)
    reorder_level: Decimal = Field(default=Decimal("0"), ge=0)
    preferred_supplier_id: int | None = None

    _name = field_validator("name")(_clean_name)

    @field_validator("unit")
    @classmethod
    def clean_unit(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("unit must not be blank")
        return v


class MaterialUpdate(BaseModel):
    """Deliberately has NO quantity_on_hand field: stock may only change
    through the transactional delivery-receive path (see inventory model)."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    unit: str | None = Field(default=None, min_length=1, max_length=30)
    reorder_level: Decimal | None = Field(default=None, ge=0)
    preferred_supplier_id: int | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, v):
        return _clean_name(v) if v is not None else v


class MaterialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    site_id: int
    preferred_supplier_id: int | None
    name: str
    unit: str
    quantity_on_hand: Decimal
    reorder_level: Decimal
    is_low_stock: bool  # read from the model property of the same name
    created_at: datetime
    updated_at: datetime


# ---- Deliveries -----------------------------------------------------------

class DeliveryCreate(BaseModel):
    """No status field on purpose: a delivery is always created pending.
    It can only become 'received' through POST /deliveries/{id}/receive,
    which is the single path that updates stock."""

    material_id: int
    supplier_id: int
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal | None = Field(default=None, ge=0)
    expected_date: date | None = None
    notes: str | None = None


class DeliveryUpdate(BaseModel):
    """Editable only while the delivery is pending (enforced in service).
    Setting status='received' here is rejected — use the receive endpoint."""

    quantity: Decimal | None = Field(default=None, gt=0)
    unit_price: Decimal | None = Field(default=None, ge=0)
    supplier_id: int | None = None
    expected_date: date | None = None
    notes: str | None = None
    status: DeliveryStatus | None = None


class DeliveryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    material_id: int
    supplier_id: int
    quantity: Decimal
    unit_price: Decimal | None
    status: DeliveryStatus
    expected_date: date | None
    received_date: date | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
