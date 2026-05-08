from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.rbac import require_roles
from app.database import get_session
from app.models.user import User, UserRole
from app.schemas import ProductCreateRequest, ProductPageResponse, ProductResponse
from app.services.catalog_service import create_product, get_product, list_products

router = APIRouter(prefix="/products", tags=["Products"])


@router.get("", response_model=ProductPageResponse)
async def read_products(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    category: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    current_user: User = Depends(
        require_roles(UserRole.TENANT_ADMIN, UserRole.WAREHOUSE_MANAGER, UserRole.ANALYST)
    ),
    session: AsyncSession = Depends(get_session),
) -> ProductPageResponse:
    return await list_products(
        session=session,
        tenant_id=current_user.tenant_id,
        current_role=current_user.role,
        cursor=cursor,
        limit=limit,
        category=category,
        is_active=is_active,
    )


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product_endpoint(
    payload: ProductCreateRequest,
    current_user: User = Depends(require_roles(UserRole.TENANT_ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> ProductResponse:
    return await create_product(
        session=session,
        tenant_id=current_user.tenant_id,
        request=payload,
        current_role=current_user.role,
    )


@router.get("/{product_id}", response_model=ProductResponse)
async def read_product(
    product_id: uuid.UUID,
    current_user: User = Depends(
        require_roles(UserRole.TENANT_ADMIN, UserRole.WAREHOUSE_MANAGER, UserRole.ANALYST)
    ),
    session: AsyncSession = Depends(get_session),
) -> ProductResponse:
    return await get_product(
        session=session,
        tenant_id=current_user.tenant_id,
        product_id=product_id,
        current_role=current_user.role,
    )

