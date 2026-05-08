from __future__ import annotations

import uuid
from urllib.parse import quote

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.models.email import EmailJob, EmailJobStatus
from app.models.transfer import StockTransfer
from app.models.user import User
from app.pagination import decode_cursor, encode_cursor
from app.schemas import EmailJobPageResponse, EmailJobResponse
from app.tasks.celery_app import celery_app


def _value(value: object) -> str:
    return value.value if hasattr(value, "value") else str(value)


async def create_email_job(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    recipient_email: str,
    subject: str,
    body_text: str,
    purpose: str,
    body_html: str | None = None,
    enqueue: bool = True,
) -> EmailJob:
    job = EmailJob(
        tenant_id=tenant_id,
        recipient_email=recipient_email,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        purpose=purpose,
        status=EmailJobStatus.QUEUED,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    if enqueue:
        try:
            celery_app.send_task("app.tasks.email_task.send_email_job", args=[str(job.id)])
        except Exception as exc:
            job.status = EmailJobStatus.FAILED.value
            job.error_message = f"Failed to enqueue email task: {exc}"[:1000]
            session.add(job)
            await session.commit()
            await session.refresh(job)
    return job


def _base_url(settings: Settings) -> str:
    return (settings.frontend_base_url or settings.api_base_url).rstrip("/")


async def queue_verification_email(
    *,
    session: AsyncSession,
    settings: Settings,
    user: User,
    token: str,
) -> EmailJob:
    verification_link = f"{_base_url(settings)}/verify-email?token={quote(token)}"
    subject = "Verify your LeanStock email"
    body_text = (
        f"Hello {user.name},\n\n"
        "Welcome to LeanStock. Verify your email to unlock warehouse, product, "
        "inventory, and transfer routes.\n\n"
        f"Verification link: {verification_link}\n"
        f"Verification token: {token}\n\n"
        "This link expires automatically."
    )
    body_html = (
        f"<p>Hello {user.name},</p>"
        "<p>Welcome to LeanStock. Verify your email to unlock warehouse, product, "
        "inventory, and transfer routes.</p>"
        f'<p><a href="{verification_link}">Verify email</a></p>'
        f"<p>Token: <code>{token}</code></p>"
    )
    return await create_email_job(
        session=session,
        tenant_id=user.tenant_id,
        recipient_email=user.email,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        purpose="email_verification",
    )


async def queue_password_reset_email(
    *,
    session: AsyncSession,
    settings: Settings,
    user: User,
    token: str,
) -> EmailJob:
    reset_link = f"{_base_url(settings)}/password-reset/confirm?token={quote(token)}"
    subject = "Reset your LeanStock password"
    body_text = (
        f"Hello {user.name},\n\n"
        "Use this link to reset your LeanStock password. If you did not request it, "
        "you can ignore this email.\n\n"
        f"Reset link: {reset_link}\n"
        f"Reset token: {token}\n\n"
        "This link expires automatically."
    )
    body_html = (
        f"<p>Hello {user.name},</p>"
        "<p>Use this link to reset your LeanStock password. If you did not request it, "
        "you can ignore this email.</p>"
        f'<p><a href="{reset_link}">Reset password</a></p>'
        f"<p>Token: <code>{token}</code></p>"
    )
    return await create_email_job(
        session=session,
        tenant_id=user.tenant_id,
        recipient_email=user.email,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        purpose="password_reset",
    )


async def queue_transfer_email(
    *,
    session: AsyncSession,
    recipient: User,
    transfer: StockTransfer,
    event: str,
) -> EmailJob:
    status_label = "created" if event == "created" else "completed"
    subject = f"LeanStock transfer {transfer.request_id} {status_label}"
    body_text = (
        f"Hello {recipient.name},\n\n"
        f"Transfer {transfer.request_id} was {status_label}.\n"
        f"Quantity: {transfer.quantity}\n"
        f"Status: {_value(transfer.status)}\n"
        f"Transfer ID: {transfer.id}\n"
    )
    body_html = (
        f"<p>Hello {recipient.name},</p>"
        f"<p>Transfer <strong>{transfer.request_id}</strong> was {status_label}.</p>"
        f"<p>Quantity: {transfer.quantity}<br>Status: {_value(transfer.status)}<br>"
        f"Transfer ID: {transfer.id}</p>"
    )
    return await create_email_job(
        session=session,
        tenant_id=recipient.tenant_id,
        recipient_email=recipient.email,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        purpose=f"transfer_{event}",
    )


async def list_email_jobs(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    cursor: str | None,
    limit: int,
) -> EmailJobPageResponse:
    decoded_cursor = decode_cursor(cursor)
    filters = [EmailJob.tenant_id == tenant_id]
    if decoded_cursor is not None:
        filters.append(EmailJob.id > decoded_cursor)

    total_count = (await session.exec(select(func.count(EmailJob.id)).where(*filters))).one()
    jobs = (
        await session.exec(
            select(EmailJob).where(*filters).order_by(EmailJob.id.asc()).limit(limit + 1)
        )
    ).all()
    has_more = len(jobs) > limit
    jobs = jobs[:limit]
    next_cursor = encode_cursor(jobs[-1].id) if has_more and jobs else None
    return EmailJobPageResponse(
        next_cursor=next_cursor,
        has_more=has_more,
        total_count=total_count,
        data=[EmailJobResponse.model_validate(job) for job in jobs],
    )
