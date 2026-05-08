from __future__ import annotations

import asyncio
import uuid

from sqlmodel import select

from app.config import get_settings
from app.database import async_session_factory
from app.models.common import utcnow
from app.models.email import EmailJob, EmailJobStatus
from app.services.email_service import GmailOAuth2EmailService
from app.tasks.celery_app import celery_app


def _status_value(status: EmailJobStatus | str) -> str:
    return status.value if hasattr(status, "value") else str(status)


@celery_app.task(
    bind=True,
    name="app.tasks.email_task.send_email_job",
    max_retries=3,
    default_retry_delay=60,
)
def send_email_job(self, email_job_id: str) -> dict[str, str]:
    try:
        return asyncio.run(_send_email_job(email_job_id))
    except Exception as exc:
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc) from exc
        raise


async def _send_email_job(email_job_id: str) -> dict[str, str]:
    settings = get_settings()
    async with async_session_factory() as session:
        job = (
            await session.exec(
                select(EmailJob)
                .where(EmailJob.id == uuid.UUID(email_job_id))
                .with_for_update()
            )
        ).one_or_none()
        if job is None:
            return {"status": "missing"}
        if _status_value(job.status) == EmailJobStatus.SENT.value:
            return {"status": "already_sent"}

        job.retry_count += 1
        job.last_attempt_at = utcnow()
        session.add(job)
        await session.commit()

    try:
        await GmailOAuth2EmailService(settings).send_email(
            recipient_email=job.recipient_email,
            subject=job.subject,
            body_text=job.body_text,
            body_html=job.body_html,
        )
    except Exception as exc:
        async with async_session_factory() as session:
            failed_job = (
                await session.exec(
                    select(EmailJob)
                    .where(EmailJob.id == uuid.UUID(email_job_id))
                    .with_for_update()
                )
            ).one_or_none()
            if failed_job is not None:
                failed_job.status = EmailJobStatus.FAILED.value
                failed_job.error_message = str(exc)[:1000]
                failed_job.last_attempt_at = utcnow()
                session.add(failed_job)
                await session.commit()
        raise

    async with async_session_factory() as session:
        sent_job = (
            await session.exec(
                select(EmailJob)
                .where(EmailJob.id == uuid.UUID(email_job_id))
                .with_for_update()
            )
        ).one_or_none()
        if sent_job is not None:
            sent_job.status = EmailJobStatus.SENT.value
            sent_job.sent_at = utcnow()
            sent_job.error_message = None
            session.add(sent_job)
            await session.commit()
    return {"status": "sent"}
