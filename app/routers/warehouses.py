from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.rbac import require_roles
from app.database import get_session
from app.models.user import User, UserRole
from app.schemas import (
    WarehouseCreateRequest,
    WarehousePageResponse,
    WarehouseResponse,
    WarehouseUpdateRequest,
)
from app.services.catalog_service import (
    create_warehouse,
    deactivate_warehouse,
    list_warehouses,
    update_warehouse,
)

router = APIRouter(prefix="/warehouses", tags=["Warehouses"])


@router.get("", response_model=WarehousePageResponse)
async def read_warehouses(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(require_roles(UserRole.TENANT_ADMIN, UserRole.WAREHOUSE_MANAGER, UserRole.ANALYST)),
    session: AsyncSession = Depends(get_session),
) -> WarehousePageResponse:
    return await list_warehouses(
        session=session,
        tenant_id=current_user.tenant_id,
        cursor=cursor,
        limit=limit,
    )


@router.post("", response_model=WarehouseResponse, status_code=status.HTTP_201_CREATED)
async def create_warehouse_endpoint(
    payload: WarehouseCreateRequest,
    current_user: User = Depends(require_roles(UserRole.TENANT_ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> WarehouseResponse:
    return await create_warehouse(session=session, tenant_id=current_user.tenant_id, request=payload)


@router.patch("/{warehouse_id}", response_model=WarehouseResponse)
async def update_warehouse_endpoint(
    warehouse_id: uuid.UUID,
    payload: WarehouseUpdateRequest,
    current_user: User = Depends(require_roles(UserRole.TENANT_ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> WarehouseResponse:
    return await update_warehouse(
        session=session,
        tenant_id=current_user.tenant_id,
        warehouse_id=warehouse_id,
        request=payload,
    )


@router.delete("/{warehouse_id}", response_model=WarehouseResponse)
async def delete_warehouse_endpoint(
    warehouse_id: uuid.UUID,
    current_user: User = Depends(require_roles(UserRole.TENANT_ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> WarehouseResponse:
    return await deactivate_warehouse(
        session=session,
        tenant_id=current_user.tenant_id,
        warehouse_id=warehouse_id,
    )
