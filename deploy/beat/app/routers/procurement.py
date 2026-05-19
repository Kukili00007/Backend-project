from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.rbac import require_roles
from app.database import get_session
from app.models.procurement import PurchaseOrderStatus
from app.models.user import User, UserRole
from app.schemas import (
    PurchaseOrderCreateRequest,
    PurchaseOrderPageResponse,
    PurchaseOrderReceiveRequest,
    PurchaseOrderResponse,
    SupplierCreateRequest,
    SupplierPageResponse,
    SupplierResponse,
    SupplierUpdateRequest,
)
from app.services.procurement_service import (
    cancel_purchase_order,
    confirm_purchase_order,
    create_purchase_order,
    create_supplier,
    deactivate_supplier,
    get_purchase_order,
    get_supplier_detail,
    list_purchase_orders,
    list_suppliers,
    receive_purchase_order,
    submit_purchase_order,
    update_supplier,
)

router = APIRouter(tags=["Procurement"])


@router.get("/suppliers", response_model=SupplierPageResponse)
async def read_suppliers(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    active_only: bool = Query(default=True),
    current_user: User = Depends(
        require_roles(UserRole.TENANT_ADMIN, UserRole.WAREHOUSE_MANAGER, UserRole.ANALYST)
    ),
    session: AsyncSession = Depends(get_session),
) -> SupplierPageResponse:
    return await list_suppliers(
        session=session,
        tenant_id=current_user.tenant_id,
        cursor=cursor,
        limit=limit,
        active_only=active_only,
    )


@router.post("/suppliers", response_model=SupplierResponse, status_code=status.HTTP_201_CREATED)
async def create_supplier_endpoint(
    payload: SupplierCreateRequest,
    current_user: User = Depends(require_roles(UserRole.TENANT_ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> SupplierResponse:
    return await create_supplier(
        session=session,
        tenant_id=current_user.tenant_id,
        request=payload,
    )


@router.get("/suppliers/{supplier_id}", response_model=SupplierResponse)
async def read_supplier(
    supplier_id: uuid.UUID,
    current_user: User = Depends(
        require_roles(UserRole.TENANT_ADMIN, UserRole.WAREHOUSE_MANAGER, UserRole.ANALYST)
    ),
    session: AsyncSession = Depends(get_session),
) -> SupplierResponse:
    return await get_supplier_detail(
        session=session,
        tenant_id=current_user.tenant_id,
        supplier_id=supplier_id,
    )


@router.patch("/suppliers/{supplier_id}", response_model=SupplierResponse)
async def update_supplier_endpoint(
    supplier_id: uuid.UUID,
    payload: SupplierUpdateRequest,
    current_user: User = Depends(require_roles(UserRole.TENANT_ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> SupplierResponse:
    return await update_supplier(
        session=session,
        tenant_id=current_user.tenant_id,
        supplier_id=supplier_id,
        request=payload,
    )


@router.delete("/suppliers/{supplier_id}", response_model=SupplierResponse)
async def delete_supplier_endpoint(
    supplier_id: uuid.UUID,
    current_user: User = Depends(require_roles(UserRole.TENANT_ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> SupplierResponse:
    return await deactivate_supplier(
        session=session,
        tenant_id=current_user.tenant_id,
        supplier_id=supplier_id,
    )


@router.get("/purchase-orders", response_model=PurchaseOrderPageResponse)
async def read_purchase_orders(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    status_filter: PurchaseOrderStatus | None = Query(default=None, alias="status"),
    current_user: User = Depends(
        require_roles(UserRole.TENANT_ADMIN, UserRole.WAREHOUSE_MANAGER, UserRole.ANALYST)
    ),
    session: AsyncSession = Depends(get_session),
) -> PurchaseOrderPageResponse:
    return await list_purchase_orders(
        session=session,
        tenant_id=current_user.tenant_id,
        cursor=cursor,
        limit=limit,
        status=status_filter,
    )


@router.post("/purchase-orders", response_model=PurchaseOrderResponse, status_code=status.HTTP_201_CREATED)
async def create_purchase_order_endpoint(
    payload: PurchaseOrderCreateRequest,
    current_user: User = Depends(require_roles(UserRole.TENANT_ADMIN, UserRole.WAREHOUSE_MANAGER)),
    session: AsyncSession = Depends(get_session),
) -> PurchaseOrderResponse:
    return await create_purchase_order(
        session=session,
        tenant_id=current_user.tenant_id,
        actor=current_user,
        request=payload,
    )


@router.get("/purchase-orders/{purchase_order_id}", response_model=PurchaseOrderResponse)
async def read_purchase_order(
    purchase_order_id: uuid.UUID,
    current_user: User = Depends(
        require_roles(UserRole.TENANT_ADMIN, UserRole.WAREHOUSE_MANAGER, UserRole.ANALYST)
    ),
    session: AsyncSession = Depends(get_session),
) -> PurchaseOrderResponse:
    return await get_purchase_order(
        session=session,
        tenant_id=current_user.tenant_id,
        purchase_order_id=purchase_order_id,
    )


@router.post("/purchase-orders/{purchase_order_id}/submit", response_model=PurchaseOrderResponse)
async def submit_purchase_order_endpoint(
    purchase_order_id: uuid.UUID,
    current_user: User = Depends(require_roles(UserRole.TENANT_ADMIN, UserRole.WAREHOUSE_MANAGER)),
    session: AsyncSession = Depends(get_session),
) -> PurchaseOrderResponse:
    return await submit_purchase_order(
        session=session,
        tenant_id=current_user.tenant_id,
        actor=current_user,
        purchase_order_id=purchase_order_id,
    )


@router.post("/purchase-orders/{purchase_order_id}/confirm", response_model=PurchaseOrderResponse)
async def confirm_purchase_order_endpoint(
    purchase_order_id: uuid.UUID,
    current_user: User = Depends(require_roles(UserRole.TENANT_ADMIN, UserRole.WAREHOUSE_MANAGER)),
    session: AsyncSession = Depends(get_session),
) -> PurchaseOrderResponse:
    return await confirm_purchase_order(
        session=session,
        tenant_id=current_user.tenant_id,
        actor=current_user,
        purchase_order_id=purchase_order_id,
    )


@router.post("/purchase-orders/{purchase_order_id}/receive", response_model=PurchaseOrderResponse)
async def receive_purchase_order_endpoint(
    purchase_order_id: uuid.UUID,
    payload: PurchaseOrderReceiveRequest,
    current_user: User = Depends(require_roles(UserRole.TENANT_ADMIN, UserRole.WAREHOUSE_MANAGER)),
    session: AsyncSession = Depends(get_session),
) -> PurchaseOrderResponse:
    return await receive_purchase_order(
        session=session,
        tenant_id=current_user.tenant_id,
        actor=current_user,
        purchase_order_id=purchase_order_id,
        request=payload,
    )


@router.post("/purchase-orders/{purchase_order_id}/cancel", response_model=PurchaseOrderResponse)
async def cancel_purchase_order_endpoint(
    purchase_order_id: uuid.UUID,
    current_user: User = Depends(require_roles(UserRole.TENANT_ADMIN, UserRole.WAREHOUSE_MANAGER)),
    session: AsyncSession = Depends(get_session),
) -> PurchaseOrderResponse:
    return await cancel_purchase_order(
        session=session,
        tenant_id=current_user.tenant_id,
        actor=current_user,
        purchase_order_id=purchase_order_id,
    )
