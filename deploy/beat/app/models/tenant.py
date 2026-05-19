from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, String
from sqlmodel import Field, SQLModel

from app.models.common import utcnow


class Tenant(SQLModel, table=True):
    __tablename__ = "tenants"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(sa_column=Column(String(255), nullable=False, index=True))
    slug: str = Field(sa_column=Column(String(100), nullable=False, unique=True, index=True))
    plan: str = Field(default="starter", sa_column=Column(String(50), nullable=False, default="starter"))
    is_active: bool = Field(default=True, sa_column=Column(Boolean, nullable=False, default=True))
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, default=utcnow),
    )

