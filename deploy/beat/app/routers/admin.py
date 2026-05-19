from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.core.rbac import require_roles
from app.database import get_session
from app.dependencies import get_settings_dependency
from app.models.user import User, UserRole
from app.schemas import DecayRunResponse, EmailJobPageResponse
from app.services.decay_service import run_decay_cycle
from app.services.email_job_service import list_email_jobs

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/email-jobs", response_model=EmailJobPageResponse)
async def read_email_jobs(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.TENANT_ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> EmailJobPageResponse:
    return await list_email_jobs(
        session=session,
        tenant_id=current_user.tenant_id,
        cursor=cursor,
        limit=limit,
    )


@router.post("/decay/run", response_model=DecayRunResponse)
async def run_decay_now(
    current_user: User = Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.TENANT_ADMIN)),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dependency),
) -> DecayRunResponse:
    result = await run_decay_cycle(
        session=session,
        settings=settings,
        tenant_id=current_user.tenant_id,
    )
    return DecayRunResponse(
        marked_liquidating=result.marked_liquidating,
        discounted=result.discounted,
    )
