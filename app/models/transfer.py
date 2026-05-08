from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String
from sqlmodel import Field, SQLModel

from app.models.common import utcnow


class TransferStatus(str, enum.Enum):
    PENDING = "pending"
    IN_TRANSIT = "in_transit"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class StockTransfer(SQLModel, table=True):
    __tablename__ = "stock_transfers"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    request_id: str = Field(sa_column=Column(String(100), nullable=False, unique=True, index=True))
    tenant_id: uuid.UUID = Field(foreign_key="tenants.id", nullable=False, index=True)
    from_warehouse_id: uuid.UUID = Field(foreign_key="warehouses.id", nullable=False)
    to_warehouse_id: uuid.UUID = Field(foreign_key="warehouses.id", nullable=False)
    variant_id: uuid.UUID = Field(foreign_key="product_variants.id", nullable=False)
    quantity: int = Field(sa_column=Column(Integer, nullable=False))
    note: str | None = Field(default=None, sa_column=Column(String(500), nullable=True))
    status: TransferStatus = Field(
        default=TransferStatus.PENDING,
        sa_column=Column(String(20), nullable=False, default=TransferStatus.PENDING.value),
    )
    initiated_by: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    confirmed_by: uuid.UUID | None = Field(foreign_key="users.id", default=None)
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, default=utcnow),
    )
    completed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
