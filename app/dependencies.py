from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings, get_settings
from app.core.redis_client import get_redis
from app.core.security import decode_token, role_value
from app.database import get_session
from app.errors import AppException
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


async def get_settings_dependency() -> Settings:
    return get_settings()


async def _resolve_user_from_credentials(
    credentials: HTTPAuthorizationCredentials | None,
    session: AsyncSession,
    settings: Settings,
    *,
    optional: bool,
) -> User | None:
    if credentials is None:
        if optional:
            return None
        raise AppException(status_code=401, code="UNAUTHORIZED", message="Missing bearer token.")

    payload = decode_token(credentials.credentials, settings)
    if payload.get("typ") != "access":
        raise AppException(status_code=401, code="INVALID_TOKEN", message="Access token required.")

    user_id = payload.get("sub")
    tenant_id = payload.get("tenant_id")
    if not user_id or not tenant_id:
        raise AppException(status_code=401, code="INVALID_TOKEN", message="Token payload is invalid.")

    statement = select(User).where(
        User.id == uuid.UUID(user_id),
        User.tenant_id == uuid.UUID(tenant_id),
        User.is_active.is_(True),
    )
    user = (await session.exec(statement)).one_or_none()
    if user is None:
        raise AppException(status_code=401, code="UNAUTHORIZED", message="User account is inactive.")
    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dependency),
) -> User:
    user = await _resolve_user_from_credentials(credentials, session, settings, optional=False)
    assert user is not None
    return user


async def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dependency),
) -> User | None:
    return await _resolve_user_from_credentials(credentials, session, settings, optional=True)


def rate_limit_dependency(scope: str) -> Callable[[Request, Redis, Settings], Awaitable[None]]:
    async def dependency(
        request: Request,
        redis: Redis = Depends(get_redis),
        settings: Settings = Depends(get_settings_dependency),
    ) -> None:
        client_ip = request.client.host if request.client else "unknown"
        key = f"rate-limit:{scope}:{client_ip}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 60)
        if count > settings.auth_rate_limit_per_minute:
            ttl = await redis.ttl(key)
            raise AppException(
                status_code=429,
                code="RATE_LIMIT_EXCEEDED",
                message=f"Too many attempts. Try again in {max(ttl, 1)} seconds.",
                details={"retry_after": max(ttl, 1)},
            )

    return dependency


def serialize_refresh_session(user: User) -> str:
    import json

    return json.dumps(
        {
            "user_id": str(user.id),
            "tenant_id": str(user.tenant_id),
            "role": role_value(user.role),
        }
    )
