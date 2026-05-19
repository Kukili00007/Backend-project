from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.models.common import utcnow


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_tenant_created", "tenant_id", "created_at"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    tenant_id: uuid.UUID = Field(foreign_key="tenants.id", nullable=False)
    user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    action: str = Field(sa_column=Column(String(100), nullable=False))
    entity_type: str = Field(sa_column=Column(String(50), nullable=False))
    entity_id: uuid.UUID = Field(nullable=False)
    before_state: dict | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    after_state: dict | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, default=utcnow),
    )

