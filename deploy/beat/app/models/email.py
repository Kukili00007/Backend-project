from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer, String, Text
from sqlmodel import Field, SQLModel

from app.models.common import utcnow


class EmailJobStatus(str, enum.Enum):
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"


class EmailVerificationToken(SQLModel, table=True):
    __tablename__ = "email_verification_tokens"
    __table_args__ = (
        Index("ix_email_verification_user_active", "user_id", "consumed_at"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    tenant_id: uuid.UUID = Field(foreign_key="tenants.id", nullable=False, index=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False, index=True)
    token_hash: str = Field(sa_column=Column(String(64), nullable=False, unique=True, index=True))
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    consumed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, default=utcnow),
    )


class PasswordResetToken(SQLModel, table=True):
    __tablename__ = "password_reset_tokens"
    __table_args__ = (
        Index("ix_password_reset_user_active", "user_id", "consumed_at"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    tenant_id: uuid.UUID = Field(foreign_key="tenants.id", nullable=False, index=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False, index=True)
    token_hash: str = Field(sa_column=Column(String(64), nullable=False, unique=True, index=True))
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    consumed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, default=utcnow),
    )


class EmailJob(SQLModel, table=True):
    __tablename__ = "email_jobs"
    __table_args__ = (
        Index("ix_email_jobs_tenant_created", "tenant_id", "created_at"),
        Index("ix_email_jobs_status_created", "status", "created_at"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    tenant_id: uuid.UUID = Field(foreign_key="tenants.id", nullable=False, index=True)
    recipient_email: str = Field(sa_column=Column(String(255), nullable=False, index=True))
    subject: str = Field(sa_column=Column(String(255), nullable=False))
    body_text: str = Field(sa_column=Column(Text, nullable=False))
    body_html: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    purpose: str = Field(sa_column=Column(String(50), nullable=False, index=True))
    status: EmailJobStatus = Field(
        default=EmailJobStatus.QUEUED,
        sa_column=Column(String(20), nullable=False, default=EmailJobStatus.QUEUED.value),
    )
    retry_count: int = Field(default=0, sa_column=Column(Integer, nullable=False, default=0))
    error_message: str | None = Field(default=None, sa_column=Column(String(1000), nullable=True))
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, default=utcnow),
    )
    sent_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    last_attempt_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
