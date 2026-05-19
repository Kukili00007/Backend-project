from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.rbac import require_roles
from app.database import get_session
from app.models.transfer import TransferStatus
from app.models.user import User, UserRole
from app.schemas import (
    TransferConfirmRequest,
    TransferCreateRequest,
    TransferPageResponse,
    TransferResponse,
)
from app.services.transfer_service import (
    cancel_transfer,
    confirm_transfer,
    create_transfer,
    list_transfers,
)

router = APIRouter(prefix="/transfers", tags=["Transfers"])


@router.get("", response_model=TransferPageResponse)
async def read_transfers(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    status_filter: TransferStatus | None = Query(default=None, alias="status"),
    warehouse_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(
        require_roles(UserRole.TENANT_ADMIN, UserRole.WAREHOUSE_MANAGER, UserRole.ANALYST)
    ),
    session: AsyncSession = Depends(get_session),
) -> TransferPageResponse:
    return await list_transfers(
        session=session,
        tenant_id=current_user.tenant_id,
        cursor=cursor,
        limit=limit,
        status=status_filter,
        warehouse_id=warehouse_id,
    )


@router.post("", response_model=TransferResponse, status_code=status.HTTP_201_CREATED)
async def create_transfer_endpoint(
    payload: TransferCreateRequest,
    response: Response,
    current_user: User = Depends(require_roles(UserRole.TENANT_ADMIN, UserRole.WAREHOUSE_MANAGER)),
    session: AsyncSession = Depends(get_session),
) -> TransferResponse:
    transfer, created = await create_transfer(
        session=session,
        tenant_id=current_user.tenant_id,
        actor=current_user,
        request=payload,
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return transfer


@router.post("/{transfer_id}/confirm", response_model=TransferResponse)
async def confirm_transfer_endpoint(
    transfer_id: uuid.UUID,
    payload: TransferConfirmRequest,
    current_user: User = Depends(require_roles(UserRole.TENANT_ADMIN, UserRole.WAREHOUSE_MANAGER)),
    session: AsyncSession = Depends(get_session),
) -> TransferResponse:
    return await confirm_transfer(
        session=session,
        tenant_id=current_user.tenant_id,
        actor=current_user,
        transfer_id=transfer_id,
        request=payload,
    )


@router.post("/{transfer_id}/cancel", response_model=TransferResponse)
async def cancel_transfer_endpoint(
    transfer_id: uuid.UUID,
    current_user: User = Depends(require_roles(UserRole.TENANT_ADMIN, UserRole.WAREHOUSE_MANAGER)),
    session: AsyncSession = Depends(get_session),
) -> TransferResponse:
    return await cancel_transfer(
        session=session,
        tenant_id=current_user.tenant_id,
        actor=current_user,
        transfer_id=transfer_id,
    )
