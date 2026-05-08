from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.rbac import require_roles
from app.database import get_session
from app.models.user import User, UserRole
from app.schemas import WarehouseCreateRequest, WarehouseResponse
from app.services.catalog_service import create_warehouse, list_warehouses

router = APIRouter(prefix="/warehouses", tags=["Warehouses"])


@router.get("", response_model=list[WarehouseResponse])
async def read_warehouses(
    current_user: User = Depends(require_roles(UserRole.TENANT_ADMIN, UserRole.WAREHOUSE_MANAGER, UserRole.ANALYST)),
    session: AsyncSession = Depends(get_session),
) -> list[WarehouseResponse]:
    return await list_warehouses(session=session, tenant_id=current_user.tenant_id)


@router.post("", response_model=WarehouseResponse, status_code=status.HTTP_201_CREATED)
async def create_warehouse_endpoint(
    payload: WarehouseCreateRequest,
    current_user: User = Depends(require_roles(UserRole.TENANT_ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> WarehouseResponse:
    return await create_warehouse(session=session, tenant_id=current_user.tenant_id, request=payload)

