from __future__ import annotations

import uuid
from datetime import timedelta, timezone

from redis.asyncio import Redis
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_secure_token,
    hash_password,
    hash_token,
    role_value,
    verify_password,
)
from app.dependencies import serialize_refresh_session
from app.errors import AppException
from app.models.common import utcnow
from app.models.email import EmailVerificationToken, PasswordResetToken
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.schemas import (
    LoginRequest,
    MessageResponse,
    PasswordResetConfirmRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.email_job_service import queue_password_reset_email, queue_verification_email


def _role_creation_forbidden(actor: User | None, requested_role: UserRole) -> bool:
    if actor is None and requested_role not in {UserRole.TENANT_ADMIN, UserRole.SUPER_ADMIN}:
        return True
    if (
        actor is not None
        and requested_role == UserRole.SUPER_ADMIN
        and role_value(actor.role) != UserRole.SUPER_ADMIN.value
    ):
        return True
    return False


def _is_email_verified(user: User) -> bool:
    return user.email_verified_at is not None


def _is_expired(expires_at) -> bool:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= utcnow()


async def _create_email_verification_token(
    *,
    session: AsyncSession,
    user: User,
    settings: Settings,
) -> str:
    now = utcnow()
    active_tokens = (
        await session.exec(
            select(EmailVerificationToken).where(
                EmailVerificationToken.user_id == user.id,
                EmailVerificationToken.consumed_at.is_(None),
            )
        )
    ).all()
    for active_token in active_tokens:
        active_token.consumed_at = now
        session.add(active_token)

    token = generate_secure_token()
    session.add(
        EmailVerificationToken(
            tenant_id=user.tenant_id,
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=now + timedelta(hours=settings.email_verification_token_expire_hours),
        )
    )
    await session.commit()
    return token


async def _create_password_reset_token(
    *,
    session: AsyncSession,
    user: User,
    settings: Settings,
) -> str:
    now = utcnow()
    active_tokens = (
        await session.exec(
            select(PasswordResetToken).where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.consumed_at.is_(None),
            )
        )
    ).all()
    for active_token in active_tokens:
        active_token.consumed_at = now
        session.add(active_token)

    token = generate_secure_token()
    session.add(
        PasswordResetToken(
            tenant_id=user.tenant_id,
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=now + timedelta(minutes=settings.password_reset_token_expire_minutes),
        )
    )
    await session.commit()
    return token


async def register_user(
    *,
    session: AsyncSession,
    request: RegisterRequest,
    current_user: User | None,
    settings: Settings,
) -> UserResponse:
    if _role_creation_forbidden(current_user, request.role):
        raise AppException(
            status_code=403,
            code="FORBIDDEN",
            message="This registration flow cannot create the requested role.",
        )
    if current_user is not None and not _is_email_verified(current_user):
        raise AppException(
            status_code=403,
            code="EMAIL_NOT_VERIFIED",
            message="Verify your email before creating staff accounts.",
        )

    existing_user = (await session.exec(select(User).where(User.email == request.email))).one_or_none()
    if existing_user is not None:
        raise AppException(
            status_code=409,
            code="EMAIL_CONFLICT",
            message="A user with this email already exists.",
        )

    if current_user is None:
        if request.role == UserRole.SUPER_ADMIN:
            user_count = (await session.exec(select(func.count(User.id)))).one()
            if user_count > 0:
                raise AppException(
                    status_code=403,
                    code="FORBIDDEN",
                    message="Super admin bootstrap is only allowed before any users exist.",
                )
        if not request.tenant_name or not request.tenant_slug:
            raise AppException(
                status_code=400,
                code="TENANT_REQUIRED",
                message="tenant_name and tenant_slug are required for bootstrap registration.",
            )
        existing_tenant = (
            await session.exec(select(Tenant).where(Tenant.slug == request.tenant_slug))
        ).one_or_none()
        if existing_tenant is not None:
            raise AppException(
                status_code=409,
                code="TENANT_SLUG_CONFLICT",
                message="A tenant with this slug already exists.",
            )

        tenant = Tenant(name=request.tenant_name, slug=request.tenant_slug)
        user = User(
            tenant_id=tenant.id,
            email=str(request.email),
            name=request.name,
            hashed_password=hash_password(request.password),
            role=request.role,
        )
        try:
            session.add(tenant)
            session.add(user)
            await session.commit()
            await session.refresh(user)
        except IntegrityError as exc:
            await session.rollback()
            raise AppException(
                status_code=409,
                code="TENANT_SLUG_CONFLICT",
                message="A tenant with this slug already exists.",
            ) from exc
        token = await _create_email_verification_token(
            session=session,
            user=user,
            settings=settings,
        )
        await queue_verification_email(session=session, settings=settings, user=user, token=token)
        return UserResponse.model_validate(user)

    if role_value(current_user.role) not in {UserRole.TENANT_ADMIN.value, UserRole.SUPER_ADMIN.value}:
        raise AppException(
            status_code=403,
            code="FORBIDDEN",
            message="Only tenant admins can register staff accounts.",
        )

    user = User(
        tenant_id=current_user.tenant_id,
        email=str(request.email),
        name=request.name,
        hashed_password=hash_password(request.password),
        role=request.role,
    )
    try:
        session.add(user)
        await session.commit()
        await session.refresh(user)
    except IntegrityError as exc:
        await session.rollback()
        raise AppException(
            status_code=409,
            code="EMAIL_CONFLICT",
            message="A user with this email already exists.",
        ) from exc

    token = await _create_email_verification_token(session=session, user=user, settings=settings)
    await queue_verification_email(session=session, settings=settings, user=user, token=token)
    return UserResponse.model_validate(user)


async def login_user(
    *,
    session: AsyncSession,
    redis: Redis,
    request: LoginRequest,
    settings: Settings,
) -> TokenResponse:
    user = (await session.exec(select(User).where(User.email == str(request.email)))).one_or_none()
    if user is None or not user.is_active or not verify_password(request.password, user.hashed_password):
        raise AppException(
            status_code=401,
            code="INVALID_CREDENTIALS",
            message="Email or password is incorrect.",
        )

    tenant = (await session.exec(select(Tenant).where(Tenant.id == user.tenant_id))).one_or_none()
    if tenant is None or not tenant.is_active:
        raise AppException(
            status_code=401,
            code="TENANT_INACTIVE",
            message="Tenant is suspended.",
        )

    access_token = create_access_token(user, settings)
    refresh_token, refresh_jti = create_refresh_token(user, settings)
    await redis.setex(
        f"refresh:{refresh_jti}",
        settings.refresh_token_expire_seconds,
        serialize_refresh_session(user),
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_seconds,
    )


async def refresh_access_token(
    *,
    session: AsyncSession,
    redis: Redis,
    refresh_token: str,
    settings: Settings,
) -> TokenResponse:
    payload = decode_token(refresh_token, settings, token_type="refresh")
    if payload.get("typ") != "refresh":
        raise AppException(
            status_code=401,
            code="INVALID_TOKEN",
            message="Refresh token required.",
        )

    refresh_jti = payload.get("jti")
    stored = await redis.get(f"refresh:{refresh_jti}")
    if not refresh_jti or stored is None:
        raise AppException(
            status_code=401,
            code="REFRESH_TOKEN_REVOKED",
            message="Refresh token is invalid or revoked.",
        )

    user = (
        await session.exec(
            select(User).where(
                User.id == uuid.UUID(payload["sub"]),
                User.tenant_id == uuid.UUID(payload["tenant_id"]),
                User.is_active.is_(True),
            )
        )
    ).one_or_none()
    if user is None:
        raise AppException(
            status_code=401,
            code="UNAUTHORIZED",
            message="User account is inactive.",
        )

    access_token = create_access_token(user, settings)
    new_refresh_token, new_refresh_jti = create_refresh_token(user, settings)
    await redis.delete(f"refresh:{refresh_jti}")
    await redis.setex(
        f"refresh:{new_refresh_jti}",
        settings.refresh_token_expire_seconds,
        serialize_refresh_session(user),
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.access_token_expire_seconds,
    )


async def logout_user(
    *,
    redis: Redis,
    refresh_token: str,
    current_user: User,
    settings: Settings,
) -> None:
    payload = decode_token(refresh_token, settings, token_type="refresh")
    if payload.get("typ") != "refresh":
        raise AppException(
            status_code=401,
            code="INVALID_TOKEN",
            message="Refresh token required.",
        )
    if payload.get("sub") != str(current_user.id):
        raise AppException(
            status_code=403,
            code="FORBIDDEN",
            message="Refresh token does not belong to the authenticated user.",
        )

    refresh_jti = payload.get("jti")
    deleted = await redis.delete(f"refresh:{refresh_jti}")
    if deleted == 0:
        raise AppException(
            status_code=401,
            code="REFRESH_TOKEN_REVOKED",
            message="Refresh token is already invalidated.",
        )


async def verify_email(
    *,
    session: AsyncSession,
    token: str,
) -> MessageResponse:
    token_hash = hash_token(token)
    verification_token = (
        await session.exec(
            select(EmailVerificationToken).where(
                EmailVerificationToken.token_hash == token_hash,
                EmailVerificationToken.consumed_at.is_(None),
            )
        )
    ).one_or_none()
    if verification_token is None:
        raise AppException(
            status_code=400,
            code="INVALID_VERIFICATION_TOKEN",
            message="Verification token is invalid or already used.",
        )
    if _is_expired(verification_token.expires_at):
        verification_token.consumed_at = utcnow()
        session.add(verification_token)
        await session.commit()
        raise AppException(
            status_code=400,
            code="VERIFICATION_TOKEN_EXPIRED",
            message="Verification token has expired. Request a new verification email.",
        )

    user = (
        await session.exec(
            select(User).where(
                User.id == verification_token.user_id,
                User.tenant_id == verification_token.tenant_id,
                User.is_active.is_(True),
            )
        )
    ).one_or_none()
    if user is None:
        raise AppException(
            status_code=400,
            code="INVALID_VERIFICATION_TOKEN",
            message="Verification token does not match an active user.",
        )

    now = utcnow()
    user.email_verified_at = user.email_verified_at or now
    verification_token.consumed_at = now
    session.add(user)
    session.add(verification_token)
    await session.commit()
    return MessageResponse(message="Email verified successfully.")


async def resend_verification_email(
    *,
    session: AsyncSession,
    request_email: str,
    settings: Settings,
) -> MessageResponse:
    user = (
        await session.exec(
            select(User).where(
                User.email == request_email,
                User.is_active.is_(True),
            )
        )
    ).one_or_none()
    if user is not None and not _is_email_verified(user):
        token = await _create_email_verification_token(
            session=session,
            user=user,
            settings=settings,
        )
        await queue_verification_email(session=session, settings=settings, user=user, token=token)
    return MessageResponse(message="If the account exists, a verification email has been queued.")


async def request_password_reset(
    *,
    session: AsyncSession,
    request_email: str,
    settings: Settings,
) -> MessageResponse:
    user = (
        await session.exec(
            select(User).where(
                User.email == request_email,
                User.is_active.is_(True),
            )
        )
    ).one_or_none()
    if user is not None:
        token = await _create_password_reset_token(session=session, user=user, settings=settings)
        await queue_password_reset_email(session=session, settings=settings, user=user, token=token)
    return MessageResponse(message="If the account exists, a password reset email has been queued.")


async def confirm_password_reset(
    *,
    session: AsyncSession,
    request: PasswordResetConfirmRequest,
) -> MessageResponse:
    token_hash = hash_token(request.token)
    reset_token = (
        await session.exec(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash == token_hash,
                PasswordResetToken.consumed_at.is_(None),
            )
        )
    ).one_or_none()
    if reset_token is None:
        raise AppException(
            status_code=400,
            code="INVALID_RESET_TOKEN",
            message="Password reset token is invalid or already used.",
        )
    if _is_expired(reset_token.expires_at):
        reset_token.consumed_at = utcnow()
        session.add(reset_token)
        await session.commit()
        raise AppException(
            status_code=400,
            code="RESET_TOKEN_EXPIRED",
            message="Password reset token has expired. Request a new password reset email.",
        )

    user = (
        await session.exec(
            select(User).where(
                User.id == reset_token.user_id,
                User.tenant_id == reset_token.tenant_id,
                User.is_active.is_(True),
            )
        )
    ).one_or_none()
    if user is None:
        raise AppException(
            status_code=400,
            code="INVALID_RESET_TOKEN",
            message="Password reset token does not match an active user.",
        )

    user.hashed_password = hash_password(request.new_password)
    reset_token.consumed_at = utcnow()
    session.add(user)
    session.add(reset_token)
    await session.commit()
    return MessageResponse(message="Password has been reset successfully.")
