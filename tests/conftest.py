from __future__ import annotations

import asyncio
import os
import re
import sys
import uuid
from collections.abc import AsyncIterator

import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from redis.asyncio import from_url
from sqlmodel import SQLModel

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

os.environ["APP_ENV"] = "test"
os.environ["SECRET_KEY"] = "test-secret-key-with-at-least-32-chars"
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5433/leanstock_test"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ["CORS_ORIGINS"] = "http://localhost:3000"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"
os.environ["REFRESH_TOKEN_EXPIRE_DAYS"] = "7"
os.environ["RESERVATION_TTL_SECONDS"] = "900"
os.environ["AUTH_RATE_LIMIT_PER_MINUTE"] = "5"
os.environ["DECAY_START_DAYS"] = "30"
os.environ["DECAY_INTERVAL_HOURS"] = "72"
os.environ["DECAY_DISCOUNT_PCT"] = "10"
os.environ["EMAIL_ENABLED"] = "false"
os.environ["EMAIL_PROVIDER"] = "gmail_oauth2"
os.environ["GMAIL_SENDER_EMAIL"] = "tests@example.com"
os.environ["API_BASE_URL"] = "http://testserver"

from app.config import get_settings

get_settings.cache_clear()

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import engine
from app.main import app
from app.models.email import EmailJob


@pytest_asyncio.fixture
async def reset_state() -> AsyncIterator[None]:
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.drop_all)
        await connection.run_sync(SQLModel.metadata.create_all)

    redis = from_url(os.environ["REDIS_URL"], decode_responses=True)
    await redis.flushdb()
    try:
        yield
    finally:
        await redis.flushdb()
        await redis.close()


@pytest_asyncio.fixture
async def client(reset_state: None) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with LifespanManager(app):
        async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
            yield async_client


async def bootstrap_tenant_admin(
    client: AsyncClient,
    *,
    email: str = "owner@arzanshop.kz",
    password: str = "Secur3P@ss!",
    tenant_slug: str = "arzan-shop",
    verify_email: bool = True,
) -> dict:
    response = await client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "name": "Aibek Dzhaksybekov",
            "role": "tenant_admin",
            "tenant_name": "Arzan Shop",
            "tenant_slug": tenant_slug,
        },
    )
    assert response.status_code == 201, response.text
    if verify_email:
        await verify_latest_email_token(
            client,
            recipient_email=email,
            purpose="email_verification",
            token_label="Verification token",
            endpoint="/v1/auth/verify-email",
        )
    return response.json()


async def login_user(client: AsyncClient, *, email: str, password: str) -> dict:
    response = await client.post(
        "/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()


def auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


async def latest_email_job(recipient_email: str, purpose: str) -> EmailJob:
    async with AsyncSession(engine) as session:
        job = (
            await session.exec(
                select(EmailJob)
                .where(
                    EmailJob.recipient_email == recipient_email,
                    EmailJob.purpose == purpose,
                )
                .order_by(EmailJob.created_at.desc())
            )
        ).first()
        assert job is not None
        return job


def extract_token_from_email(job: EmailJob, token_label: str) -> str:
    match = re.search(rf"{re.escape(token_label)}:\s*(\S+)", job.body_text)
    assert match is not None, job.body_text
    return match.group(1)


async def verify_latest_email_token(
    client: AsyncClient,
    *,
    recipient_email: str,
    purpose: str,
    token_label: str,
    endpoint: str,
) -> str:
    job = await latest_email_job(recipient_email, purpose)
    token = extract_token_from_email(job, token_label)
    response = await client.post(endpoint, json={"token": token})
    assert response.status_code == 200, response.text
    return token
