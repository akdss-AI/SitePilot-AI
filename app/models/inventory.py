"""Inventory models — Phase 3: Supplier, Material, Delivery.

Relationships
-------------
Supplier   belongs to one User (owner). Referenced by materials (as
           preferred supplier) and by deliveries.
Material   belongs to one Site (and therefore, through the site, to one
           Project and one owner). Stock lives here as quantity_on_hand.
Delivery   belongs to one Material and one Supplier. A delivery's site
           and project are reached through its material — a separate
           site_id column was deliberately NOT added, because a stored
           copy could disagree with material.site_id.

Ownership chain used by every service query in this phase:
    delivery -> material -> site -> project -> owner
    material -> site -> project -> owner
    supplier -> owner

Stock model
-----------
quantity_on_hand is a stored column, changed in exactly two ways:
  1. set as the opening quantity when a material is created;
  2. increased by receive_delivery(), in the same transaction that marks
     the delivery received.
It is NOT editable through the material update API — that keeps a single,
auditable path for stock increases in v1. (Stock decreases / usage
arrive with site updates in later phases.)
"""
import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Supplier(Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_supplier_owner_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_person: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    owner: Mapped["User"] = relationship()  # noqa: F821


class Material(Base):
    __tablename__ = "materials"
    __table_args__ = (
        UniqueConstraint("site_id", "name", name="uq_material_site_name"),
        CheckConstraint("quantity_on_hand >= 0", name="ck_material_stock_nonnegative"),
        CheckConstraint("reorder_level >= 0", name="ck_material_reorder_nonnegative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(
        ForeignKey("sites.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # If the supplier is deleted, the material simply loses its preference.
    preferred_supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("suppliers.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)  # bags, kg, pcs…
    quantity_on_hand: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), nullable=False
    )
    reorder_level: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    site: Mapped["Site"] = relationship(back_populates="materials")  # noqa: F821
    preferred_supplier: Mapped["Supplier | None"] = relationship()
    deliveries: Mapped[list["Delivery"]] = relationship(back_populates="material")

    @property
    def is_low_stock(self) -> bool:
        """The low-stock rule, in exactly one place."""
        return self.quantity_on_hand <= self.reorder_level


class DeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    RECEIVED = "received"
    CANCELLED = "cancelled"


class Delivery(Base):
    __tablename__ = "deliveries"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_delivery_quantity_positive"),
        CheckConstraint(
            "unit_price IS NULL OR unit_price >= 0", name="ck_delivery_price_nonnegative"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # RESTRICT (the database default when no ondelete is given, enforced at
    # the DB level): a material or supplier that has deliveries cannot be
    # deleted, so delivery history can never be silently orphaned.
    material_id: Mapped[int] = mapped_column(
        ForeignKey("materials.id"), index=True, nullable=False
    )
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id"), index=True, nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    status: Mapped[DeliveryStatus] = mapped_column(
        Enum(DeliveryStatus, name="delivery_status"),
        default=DeliveryStatus.PENDING,
        nullable=False,
    )
    expected_date: Mapped[date | None] = mapped_column(Date)
    received_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    material: Mapped["Material"] = relationship(back_populates="deliveries")
    supplier: Mapped["Supplier"] = relationship()
