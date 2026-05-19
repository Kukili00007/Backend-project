from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends

from app.dependencies import get_current_user
from app.errors import AppException
from app.models.user import User, UserRole


def require_roles(*roles: UserRole) -> Callable[[User], User]:
    async def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.email_verified_at is None:
            raise AppException(
                status_code=403,
                code="EMAIL_NOT_VERIFIED",
                message="Verify your email before accessing business resources.",
            )
        allowed_roles = {role.value for role in roles}
        current_role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
        if current_role not in allowed_roles:
            raise AppException(
                status_code=403,
                code="FORBIDDEN",
                message="You do not have permission to access this resource.",
            )
        return current_user

    return dependency
