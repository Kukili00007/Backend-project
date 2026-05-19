from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import token_urlsafe
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jose import JWTError, jwt

from app.config import Settings
from app.errors import AppException
from app.models.user import User

password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)


def role_value(role: Any) -> str:
    return role.value if hasattr(role, "value") else str(role)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return password_hasher.verify(hashed_password, password)
    except VerifyMismatchError:
        return False


def generate_secure_token() -> str:
    return token_urlsafe(32)


def hash_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def _build_token(
    *,
    subject: str,
    tenant_id: str,
    role: str,
    token_type: str,
    secret_key: str,
    algorithm: str,
    expires_delta: timedelta,
    extra: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "tenant_id": tenant_id,
        "role": role,
        "typ": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, secret_key, algorithm=algorithm)


def create_access_token(user: User, settings: Settings) -> str:
    return _build_token(
        subject=str(user.id),
        tenant_id=str(user.tenant_id),
        role=role_value(user.role),
        token_type="access",
        secret_key=settings.secret_key,
        algorithm=settings.algorithm,
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(user: User, settings: Settings, token_id: uuid.UUID | None = None) -> tuple[str, str]:
    jti = str(token_id or uuid.uuid4())
    token = _build_token(
        subject=str(user.id),
        tenant_id=str(user.tenant_id),
        role=role_value(user.role),
        token_type="refresh",
        secret_key=settings.effective_refresh_secret_key,
        algorithm=settings.algorithm,
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
        extra={"jti": jti},
    )
    return token, jti


def decode_token(token: str, settings: Settings, *, token_type: str = "access") -> dict[str, Any]:
    secret_key = settings.effective_refresh_secret_key if token_type == "refresh" else settings.secret_key
    try:
        return jwt.decode(token, secret_key, algorithms=[settings.algorithm])
    except JWTError as exc:
        raise AppException(
            status_code=401,
            code="INVALID_TOKEN",
            message="Token is invalid or expired.",
        ) from exc
