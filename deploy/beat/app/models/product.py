from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import Boolean, Column, Numeric, String, UniqueConstraint
from sqlmodel import Field, SQLModel


class Product(SQLModel, table=True):
    __tablename__ = "products"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    tenant_id: uuid.UUID = Field(foreign_key="tenants.id", nullable=False, index=True)
    name: str = Field(sa_column=Column(String(255), nullable=False))
    category: str | None = Field(default=None, sa_column=Column(String(100), nullable=True))
    unit_of_measure: str = Field(
        default="pcs",
        sa_column=Column(String(20), nullable=False, default="pcs"),
    )
    is_active: bool = Field(default=True, sa_column=Column(Boolean, nullable=False, default=True))


class ProductVariant(SQLModel, table=True):
    __tablename__ = "product_variants"
    __table_args__ = (UniqueConstraint("tenant_id", "sku", name="uq_product_variant_tenant_sku"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    product_id: uuid.UUID = Field(foreign_key="products.id", nullable=False, index=True)
    tenant_id: uuid.UUID = Field(foreign_key="tenants.id", nullable=False, index=True)
    sku: str = Field(sa_column=Column(String(100), nullable=False, index=True))
    color: str | None = Field(default=None, sa_column=Column(String(50), nullable=True))
    size: str | None = Field(default=None, sa_column=Column(String(50), nullable=True))
    barcode: str | None = Field(default=None, sa_column=Column(String(50), nullable=True, index=True))
    cost_price: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    selling_price: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    liquidation_floor_price: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
