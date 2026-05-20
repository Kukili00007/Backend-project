from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from redis.asyncio import Redis
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.core.redis_client import get_redis
from app.database import get_session
from app.dependencies import (
    get_current_user,
    get_optional_current_user,
    get_settings_dependency,
    rate_limit_dependency,
)
from app.models.user import User
from app.schemas import (
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RefreshRequest,
    RegisterRequest,
    ResendVerificationRequest,
    TokenResponse,
    UserResponse,
    VerifyEmailRequest,
)
from app.services.auth_service import (
    confirm_password_reset,
    login_user,
    logout_user,
    refresh_access_token,
    register_user,
    request_password_reset,
    resend_verification_email,
    verify_email,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_dependency("auth-register"))],
)
async def register(
    payload: RegisterRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User | None = Depends(get_optional_current_user),
    settings: Settings = Depends(get_settings_dependency),
) -> UserResponse:
    return await register_user(
        session=session,
        request=payload,
        current_user=current_user,
        settings=settings,
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit_dependency("auth-login"))],
)
async def login(
    payload: LoginRequest,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings_dependency),
) -> TokenResponse:
    return await login_user(session=session, redis=redis, request=payload, settings=settings)


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit_dependency("auth-refresh"))],
)
async def refresh(
    payload: RefreshRequest,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings_dependency),
) -> TokenResponse:
    return await refresh_access_token(
        session=session,
        redis=redis,
        refresh_token=payload.refresh_token,
        settings=settings,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit_dependency("auth-logout"))],
)
async def logout(
    payload: LogoutRequest,
    current_user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings_dependency),
) -> Response:
    await logout_user(
        redis=redis,
        refresh_token=payload.refresh_token,
        current_user=current_user,
        settings=settings,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/verify-email",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit_dependency("auth-verify-email"))],
)
async def verify_email_endpoint(
    payload: VerifyEmailRequest,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dependency),
) -> MessageResponse:
    return await verify_email(
        session=session,
        token=payload.token,
        request_email=str(payload.email) if payload.email else None,
        settings=settings,
    )


@router.post(
    "/resend-verification",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit_dependency("auth-resend-verification"))],
)
async def resend_verification_endpoint(
    payload: ResendVerificationRequest,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dependency),
) -> MessageResponse:
    return await resend_verification_email(
        session=session,
        request_email=str(payload.email),
        settings=settings,
    )


@router.post(
    "/password-reset/request",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit_dependency("auth-password-reset-request"))],
)
async def password_reset_request_endpoint(
    payload: PasswordResetRequest,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dependency),
) -> MessageResponse:
    return await request_password_reset(
        session=session,
        request_email=str(payload.email),
        settings=settings,
    )


@router.post(
    "/password-reset/confirm",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit_dependency("auth-password-reset-confirm"))],
)
async def password_reset_confirm_endpoint(
    payload: PasswordResetConfirmRequest,
    session: AsyncSession = Depends(get_session),
) -> MessageResponse:
    return await confirm_password_reset(session=session, request=payload)
