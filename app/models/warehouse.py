from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlmodel import Field, SQLModel


class Warehouse(SQLModel, table=True):
    __tablename__ = "warehouses"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    tenant_id: uuid.UUID = Field(foreign_key="tenants.id", nullable=False, index=True)
    name: str = Field(sa_column=Column(String(255), nullable=False))
    location: str | None = Field(default=None, sa_column=Column(String(500), nullable=True))
    is_active: bool = Field(default=True, sa_column=Column(Boolean, nullable=False, default=True))


class InventoryItem(SQLModel, table=True):
    __tablename__ = "inventory_items"
    __table_args__ = (
        UniqueConstraint("variant_id", "warehouse_id", name="uq_variant_warehouse"),
        CheckConstraint("quantity >= 0", name="ck_quantity_non_negative"),
        Index("ix_inventory_tenant_warehouse", "tenant_id", "warehouse_id"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    tenant_id: uuid.UUID = Field(foreign_key="tenants.id", nullable=False)
    variant_id: uuid.UUID = Field(foreign_key="product_variants.id", nullable=False, index=True)
    warehouse_id: uuid.UUID = Field(foreign_key="warehouses.id", nullable=False, index=True)
    quantity: int = Field(default=0, sa_column=Column(Integer, nullable=False, default=0))
    reorder_threshold: int = Field(default=5, sa_column=Column(Integer, nullable=False, default=5))
    last_sold_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    decay_status: str = Field(
        default="normal",
        sa_column=Column(String(20), nullable=False, default="normal"),
    )
    decay_started_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    current_price: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
