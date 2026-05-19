from __future__ import annotations

import json
import math
import uuid
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from redis.asyncio import Redis
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.core.security import role_value
from app.errors import AppException
from app.models.audit import AuditLog
from app.models.common import utcnow
from app.models.product import Product, ProductVariant
from app.models.user import User, UserRole
from app.models.warehouse import InventoryItem, Warehouse
from app.pagination import decode_cursor, encode_cursor
from app.schemas import (
    ForecastPageResponse,
    ForecastSuggestionResponse,
    InventoryAdjustRequest,
    InventoryItemResponse,
    InventoryPageResponse,
    InventoryVariantView,
    ReservationRequest,
    ReservationResponse,
)
from app.services.audit_service import build_audit_log


def _can_view_cost(role: UserRole) -> bool:
    return role_value(role) in {UserRole.SUPER_ADMIN.value, UserRole.TENANT_ADMIN.value}


def _discount_pct(current_price: Decimal, original_price: Decimal) -> Decimal:
    if original_price == 0:
        return Decimal("0.00")
    pct = (Decimal("1") - (current_price / original_price)) * Decimal("100")
    return max(pct, Decimal("0.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _serialize_inventory_row(
    inventory_item: InventoryItem,
    variant: ProductVariant,
    product: Product,
    role: UserRole,
) -> InventoryItemResponse:
    return InventoryItemResponse(
        id=inventory_item.id,
        warehouse_id=inventory_item.warehouse_id,
        quantity=inventory_item.quantity,
        reorder_threshold=inventory_item.reorder_threshold,
        is_low_stock=inventory_item.quantity <= inventory_item.reorder_threshold,
        decay_status=inventory_item.decay_status,
        current_price=inventory_item.current_price,
        discount_pct=_discount_pct(inventory_item.current_price, variant.selling_price),
        last_sold_at=inventory_item.last_sold_at,
        variant=InventoryVariantView(
            id=variant.id,
            product_id=product.id,
            product_name=product.name,
            sku=variant.sku,
            color=variant.color,
            size=variant.size,
            barcode=variant.barcode,
            selling_price=variant.selling_price,
            liquidation_floor_price=variant.liquidation_floor_price,
            cost_price=variant.cost_price if _can_view_cost(role) else None,
        ),
    )


async def _get_variant_for_tenant(
    session: AsyncSession, tenant_id: uuid.UUID, variant_id: uuid.UUID
) -> ProductVariant:
    variant = (
        await session.exec(
            select(ProductVariant).where(
                ProductVariant.id == variant_id,
                ProductVariant.tenant_id == tenant_id,
            )
        )
    ).one_or_none()
    if variant is None:
        raise AppException(status_code=404, code="NOT_FOUND", message="Variant not found.")
    return variant


async def _get_warehouse_for_tenant(
    session: AsyncSession, tenant_id: uuid.UUID, warehouse_id: uuid.UUID
) -> Warehouse:
    warehouse = (
        await session.exec(
            select(Warehouse).where(
                Warehouse.id == warehouse_id,
                Warehouse.tenant_id == tenant_id,
                Warehouse.is_active.is_(True),
            )
        )
    ).one_or_none()
    if warehouse is None:
        raise AppException(status_code=404, code="NOT_FOUND", message="Warehouse not found.")
    return warehouse


async def adjust_inventory(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    actor: User,
    request: InventoryAdjustRequest,
) -> InventoryItemResponse:
    variant = await _get_variant_for_tenant(session, tenant_id, request.variant_id)
    warehouse = await _get_warehouse_for_tenant(session, tenant_id, request.warehouse_id)
    product = (
        await session.exec(select(Product).where(Product.id == variant.product_id, Product.tenant_id == tenant_id))
    ).one()

    should_alert_low_stock = False
    try:
        inventory_item = (
            await session.exec(
                select(InventoryItem)
                .where(
                    InventoryItem.tenant_id == tenant_id,
                    InventoryItem.variant_id == request.variant_id,
                    InventoryItem.warehouse_id == request.warehouse_id,
                )
                .with_for_update()
            )
        ).one_or_none()

        if inventory_item is None:
            if request.quantity_delta < 0:
                raise AppException(
                    status_code=409,
                    code="INSUFFICIENT_STOCK",
                    message="Cannot remove stock from a non-existent inventory row.",
                )
            inventory_item = InventoryItem(
                tenant_id=tenant_id,
                variant_id=request.variant_id,
                warehouse_id=request.warehouse_id,
                quantity=0,
                current_price=variant.selling_price,
            )
            session.add(inventory_item)

        before = inventory_item.model_dump()
        before_quantity = inventory_item.quantity
        next_quantity = inventory_item.quantity + request.quantity_delta
        if next_quantity < 0:
            raise AppException(
                status_code=409,
                code="INSUFFICIENT_STOCK",
                message=f"Only {inventory_item.quantity} units available, cannot remove {abs(request.quantity_delta)}.",
            )

        inventory_item.quantity = next_quantity
        should_alert_low_stock = (
            before_quantity > inventory_item.reorder_threshold
            and inventory_item.quantity <= inventory_item.reorder_threshold
        )
        session.add(
            build_audit_log(
                tenant_id=tenant_id,
                user_id=actor.id,
                action=f"STOCK_ADJUSTMENT_{request.reason.upper()}",
                entity_type="inventory_item",
                entity_id=inventory_item.id,
                before_state=before,
                after_state=inventory_item.model_dump(),
            )
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    await session.refresh(inventory_item)
    if should_alert_low_stock:
        await _queue_low_stock_alerts(
            session=session,
            tenant_id=tenant_id,
            inventory_item=inventory_item,
            variant=variant,
            product=product,
            warehouse=warehouse,
        )
    return _serialize_inventory_row(inventory_item, variant, product, actor.role)


async def _queue_low_stock_alerts(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    inventory_item: InventoryItem,
    variant: ProductVariant,
    product: Product,
    warehouse: Warehouse,
) -> None:
    from app.services.email_job_service import queue_low_stock_alert_email

    recipients = (
        await session.exec(
            select(User).where(
                User.tenant_id == tenant_id,
                User.is_active.is_(True),
                User.email_verified_at.is_not(None),
            )
        )
    ).all()
    allowed_roles = {UserRole.TENANT_ADMIN.value, UserRole.WAREHOUSE_MANAGER.value}
    for recipient in recipients:
        if role_value(recipient.role) in allowed_roles:
            await queue_low_stock_alert_email(
                session=session,
                recipient=recipient,
                inventory_item=inventory_item,
                variant=variant,
                product=product,
                warehouse=warehouse,
            )


async def list_inventory(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    current_role: UserRole,
    cursor: str | None,
    limit: int,
    warehouse_id: uuid.UUID | None,
    decay_status: str | None,
    low_stock_only: bool,
    sku: str | None,
) -> InventoryPageResponse:
    decoded_cursor = decode_cursor(cursor)
    filters = [InventoryItem.tenant_id == tenant_id, Product.tenant_id == tenant_id, ProductVariant.tenant_id == tenant_id]
    if decoded_cursor is not None:
        filters.append(InventoryItem.id > decoded_cursor)
    if warehouse_id is not None:
        filters.append(InventoryItem.warehouse_id == warehouse_id)
    if decay_status is not None:
        filters.append(InventoryItem.decay_status == decay_status)
    if low_stock_only:
        filters.append(InventoryItem.quantity <= InventoryItem.reorder_threshold)
    if sku:
        filters.append(ProductVariant.sku.ilike(f"%{sku}%"))

    total_count = (
        await session.exec(
            select(func.count(InventoryItem.id))
            .select_from(InventoryItem)
            .join(ProductVariant, InventoryItem.variant_id == ProductVariant.id)
            .join(Product, ProductVariant.product_id == Product.id)
            .where(*filters)
        )
    ).one()

    rows = (
        await session.exec(
            select(InventoryItem, ProductVariant, Product)
            .join(ProductVariant, InventoryItem.variant_id == ProductVariant.id)
            .join(Product, ProductVariant.product_id == Product.id)
            .where(*filters)
            .order_by(InventoryItem.id.asc())
            .limit(limit + 1)
        )
    ).all()

    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor(rows[-1][0].id) if has_more and rows else None

    data = [
        _serialize_inventory_row(inventory_item, variant, product, current_role)
        for inventory_item, variant, product in rows
    ]
    return InventoryPageResponse(
        next_cursor=next_cursor,
        has_more=has_more,
        total_count=total_count,
        data=data,
    )


async def forecast_reorder_suggestions(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    cursor: str | None,
    limit: int,
    warehouse_id: uuid.UUID | None,
    forecast_window_days: int,
    lead_time_days: int,
    reorder_only: bool,
) -> ForecastPageResponse:
    decoded_cursor = decode_cursor(cursor)
    filters = [InventoryItem.tenant_id == tenant_id]
    if decoded_cursor is not None:
        filters.append(InventoryItem.id > decoded_cursor)
    if warehouse_id is not None:
        filters.append(InventoryItem.warehouse_id == warehouse_id)

    total_count = (await session.exec(select(func.count(InventoryItem.id)).where(*filters))).one()
    inventory_rows = (
        await session.exec(
            select(InventoryItem, ProductVariant, Product)
            .join(ProductVariant, InventoryItem.variant_id == ProductVariant.id)
            .join(Product, ProductVariant.product_id == Product.id)
            .where(*filters, ProductVariant.tenant_id == tenant_id, Product.tenant_id == tenant_id)
            .order_by(InventoryItem.id.asc())
            .limit(limit + 1)
        )
    ).all()

    has_more = len(inventory_rows) > limit
    inventory_rows = inventory_rows[:limit]
    inventory_ids = [row[0].id for row in inventory_rows]
    cutoff = utcnow() - timedelta(days=forecast_window_days)
    audit_logs = []
    if inventory_ids:
        audit_logs = (
            await session.exec(
                select(AuditLog).where(
                    AuditLog.tenant_id == tenant_id,
                    AuditLog.entity_type == "inventory_item",
                    AuditLog.entity_id.in_(inventory_ids),
                    AuditLog.created_at >= cutoff,
                )
            )
        ).all()

    outgoing_by_inventory: dict[uuid.UUID, int] = {inventory_id: 0 for inventory_id in inventory_ids}
    for log in audit_logs:
        before_quantity = (log.before_state or {}).get("quantity")
        after_quantity = (log.after_state or {}).get("quantity")
        if isinstance(before_quantity, int) and isinstance(after_quantity, int):
            outgoing_by_inventory[log.entity_id] += max(before_quantity - after_quantity, 0)

    data: list[ForecastSuggestionResponse] = []
    for inventory_item, variant, product in inventory_rows:
        outgoing_units = outgoing_by_inventory.get(inventory_item.id, 0)
        average_daily_demand = (
            Decimal(outgoing_units) / Decimal(forecast_window_days)
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        target_stock = average_daily_demand * Decimal(lead_time_days) + Decimal(
            inventory_item.reorder_threshold
        )
        recommended_quantity = max(
            0,
            math.ceil(target_stock - Decimal(inventory_item.quantity)),
        )
        if inventory_item.quantity <= inventory_item.reorder_threshold:
            urgency = "reorder_now"
        elif recommended_quantity > 0:
            urgency = "watch"
        else:
            urgency = "none"
        if reorder_only and recommended_quantity == 0 and urgency == "none":
            continue
        data.append(
            ForecastSuggestionResponse(
                inventory_item_id=inventory_item.id,
                warehouse_id=inventory_item.warehouse_id,
                variant_id=variant.id,
                sku=variant.sku,
                product_name=product.name,
                current_quantity=inventory_item.quantity,
                reorder_threshold=inventory_item.reorder_threshold,
                forecast_window_days=forecast_window_days,
                lead_time_days=lead_time_days,
                observed_outgoing_units=outgoing_units,
                average_daily_demand=average_daily_demand,
                recommended_reorder_quantity=recommended_quantity,
                urgency=urgency,
            )
        )

    next_cursor = encode_cursor(inventory_rows[-1][0].id) if has_more and inventory_rows else None
    return ForecastPageResponse(
        next_cursor=next_cursor,
        has_more=has_more,
        total_count=total_count,
        data=data,
    )


async def _reserved_quantity(redis: Redis, tenant_id: uuid.UUID, warehouse_id: uuid.UUID, variant_id: uuid.UUID) -> int:
    prefix = f"reservation:{tenant_id}:{warehouse_id}:{variant_id}:"
    total = 0
    async for key in redis.scan_iter(match=f"{prefix}*"):
        payload = await redis.get(key)
        if payload:
            total += int(json.loads(payload)["quantity"])
    return total


async def reserve_stock(
    *,
    session: AsyncSession,
    redis: Redis,
    settings: Settings,
    tenant_id: uuid.UUID,
    request: ReservationRequest,
) -> ReservationResponse:
    await _get_variant_for_tenant(session, tenant_id, request.variant_id)
    await _get_warehouse_for_tenant(session, tenant_id, request.warehouse_id)

    lock = redis.lock(
        f"lock:reserve:{tenant_id}:{request.warehouse_id}:{request.variant_id}",
        timeout=10,
        blocking_timeout=5,
    )
    async with lock:
        inventory_item = (
            await session.exec(
                select(InventoryItem).where(
                    InventoryItem.tenant_id == tenant_id,
                    InventoryItem.variant_id == request.variant_id,
                    InventoryItem.warehouse_id == request.warehouse_id,
                )
            )
        ).one_or_none()
        if inventory_item is None:
            raise AppException(
                status_code=409,
                code="INSUFFICIENT_STOCK",
                message="Inventory item does not exist.",
            )

        reserved_total = await _reserved_quantity(
            redis, tenant_id, request.warehouse_id, request.variant_id
        )
        available = inventory_item.quantity - reserved_total
        if available < request.quantity:
            raise AppException(
                status_code=409,
                code="INSUFFICIENT_STOCK",
                message=f"Only {available} units are available for reservation.",
            )

        reservation_id = uuid.uuid4().hex[:12]
        expires_at = utcnow() + timedelta(seconds=settings.reservation_ttl_seconds)
        await redis.setex(
            f"reservation:{tenant_id}:{request.warehouse_id}:{request.variant_id}:{reservation_id}",
            settings.reservation_ttl_seconds,
            json.dumps({"quantity": request.quantity, "order_reference": request.order_reference}),
        )
        return ReservationResponse(reservation_id=reservation_id, expires_at=expires_at)
