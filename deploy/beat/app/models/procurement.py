from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, String, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.common import utcnow


class PurchaseOrderStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"
    RECEIVED = "received"
    CANCELLED = "cancelled"


class Supplier(SQLModel, table=True):
    __tablename__ = "suppliers"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_supplier_tenant_name"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    tenant_id: uuid.UUID = Field(foreign_key="tenants.id", nullable=False, index=True)
    name: str = Field(sa_column=Column(String(255), nullable=False))
    contact_email: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    phone: str | None = Field(default=None, sa_column=Column(String(50), nullable=True))
    lead_time_days: int = Field(default=7, sa_column=Column(Integer, nullable=False, default=7))
    is_active: bool = Field(default=True, sa_column=Column(Boolean, nullable=False, default=True))
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, default=utcnow),
    )


class PurchaseOrder(SQLModel, table=True):
    __tablename__ = "purchase_orders"
    __table_args__ = (UniqueConstraint("tenant_id", "po_number", name="uq_po_tenant_number"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    tenant_id: uuid.UUID = Field(foreign_key="tenants.id", nullable=False, index=True)
    po_number: str = Field(sa_column=Column(String(100), nullable=False, index=True))
    supplier_id: uuid.UUID = Field(foreign_key="suppliers.id", nullable=False, index=True)
    warehouse_id: uuid.UUID = Field(foreign_key="warehouses.id", nullable=False, index=True)
    variant_id: uuid.UUID = Field(foreign_key="product_variants.id", nullable=False, index=True)
    quantity: int = Field(sa_column=Column(Integer, nullable=False))
    expected_unit_cost: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    status: PurchaseOrderStatus = Field(
        default=PurchaseOrderStatus.DRAFT,
        sa_column=Column(String(20), nullable=False, default=PurchaseOrderStatus.DRAFT.value),
    )
    created_by: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    submitted_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    confirmed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    received_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, default=utcnow),
    )
