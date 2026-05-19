from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Index, String
from sqlmodel import Field, SQLModel

from app.models.common import utcnow


class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    TENANT_ADMIN = "tenant_admin"
    WAREHOUSE_MANAGER = "warehouse_manager"
    ANALYST = "analyst"


class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (Index("ix_users_tenant_email", "tenant_id", "email"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    tenant_id: uuid.UUID = Field(foreign_key="tenants.id", nullable=False, index=True)
    email: str = Field(sa_column=Column(String(255), nullable=False, unique=True, index=True))
    name: str = Field(sa_column=Column(String(255), nullable=False))
    hashed_password: str = Field(sa_column=Column(String, nullable=False))
    role: UserRole = Field(
        default=UserRole.ANALYST,
        sa_column=Column(String(50), nullable=False, default=UserRole.ANALYST.value),
    )
    is_active: bool = Field(default=True, sa_column=Column(Boolean, nullable=False, default=True))
    email_verified_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, default=utcnow),
    )
