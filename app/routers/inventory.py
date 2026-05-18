from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.core.rbac import require_roles
from app.core.redis_client import get_redis
from app.database import get_session
from app.dependencies import get_settings_dependency
from app.models.user import User, UserRole
from app.schemas import (
    ForecastPageResponse,
    InventoryAdjustRequest,
    InventoryItemResponse,
    InventoryPageResponse,
    ReservationRequest,
    ReservationResponse,
)
from app.services.inventory_service import (
    adjust_inventory,
    forecast_reorder_suggestions,
    list_inventory,
    reserve_stock,
)

router = APIRouter(prefix="/inventory", tags=["Inventory"])


@router.get("", response_model=InventoryPageResponse)
async def read_inventory(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    warehouse_id: uuid.UUID | None = Query(default=None),
    decay_status: str | None = Query(default=None, pattern="^(normal|liquidating)$"),
    low_stock_only: bool = Query(default=False),
    sku: str | None = Query(default=None),
    current_user: User = Depends(
        require_roles(UserRole.TENANT_ADMIN, UserRole.WAREHOUSE_MANAGER, UserRole.ANALYST)
    ),
    session: AsyncSession = Depends(get_session),
) -> InventoryPageResponse:
    return await list_inventory(
        session=session,
        tenant_id=current_user.tenant_id,
        current_role=current_user.role,
        cursor=cursor,
        limit=limit,
        warehouse_id=warehouse_id,
        decay_status=decay_status,
        low_stock_only=low_stock_only,
        sku=sku,
    )


@router.get("/forecast", response_model=ForecastPageResponse)
async def read_reorder_forecast(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    warehouse_id: uuid.UUID | None = Query(default=None),
    forecast_window_days: int = Query(default=30, ge=1, le=365),
    lead_time_days: int = Query(default=7, ge=1, le=120),
    reorder_only: bool = Query(default=False),
    current_user: User = Depends(
        require_roles(UserRole.TENANT_ADMIN, UserRole.WAREHOUSE_MANAGER, UserRole.ANALYST)
    ),
    session: AsyncSession = Depends(get_session),
) -> ForecastPageResponse:
    return await forecast_reorder_suggestions(
        session=session,
        tenant_id=current_user.tenant_id,
        cursor=cursor,
        limit=limit,
        warehouse_id=warehouse_id,
        forecast_window_days=forecast_window_days,
        lead_time_days=lead_time_days,
        reorder_only=reorder_only,
    )


@router.post("/adjust", response_model=InventoryItemResponse)
async def adjust_inventory_endpoint(
    payload: InventoryAdjustRequest,
    current_user: User = Depends(require_roles(UserRole.TENANT_ADMIN, UserRole.WAREHOUSE_MANAGER)),
    session: AsyncSession = Depends(get_session),
) -> InventoryItemResponse:
    return await adjust_inventory(
        session=session,
        tenant_id=current_user.tenant_id,
        actor=current_user,
        request=payload,
    )


@router.post("/reserve", response_model=ReservationResponse)
async def reserve_inventory_endpoint(
    payload: ReservationRequest,
    current_user: User = Depends(require_roles(UserRole.TENANT_ADMIN, UserRole.WAREHOUSE_MANAGER)),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings_dependency),
) -> ReservationResponse:
    return await reserve_stock(
        session=session,
        redis=redis,
        settings=settings,
        tenant_id=current_user.tenant_id,
        request=payload,
    )
