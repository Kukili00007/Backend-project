from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.models.product import ProductVariant
from app.models.user import User
from app.models.warehouse import InventoryItem
from app.services.audit_service import build_audit_log


@dataclass
class DecayRunResult:
    marked_liquidating: int = 0
    discounted: int = 0


def calculate_decay_price(
    current_price: Decimal,
    floor_price: Decimal,
    discount_pct: Decimal,
) -> Decimal:
    multiplier = Decimal("1") - (discount_pct / Decimal("100"))
    next_price = (current_price * multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return max(next_price, floor_price)


async def run_decay_cycle(
    *,
    session: AsyncSession,
    settings: Settings,
    now: datetime | None = None,
    tenant_id: uuid.UUID | None = None,
) -> DecayRunResult:
    now = now or datetime.now(timezone.utc)
    mark_before = now - timedelta(days=settings.decay_start_days)
    discount_before = now - timedelta(hours=settings.decay_interval_hours)
    result = DecayRunResult()

    variant_filters = []
    if tenant_id is not None:
        variant_filters.append(ProductVariant.tenant_id == tenant_id)
    variants = {
        variant.id: variant
        for variant in (
            await session.exec(select(ProductVariant).where(*variant_filters))
        ).all()
    }
    actor_map: dict = {}
    user_filters = [User.is_active.is_(True)]
    if tenant_id is not None:
        user_filters.append(User.tenant_id == tenant_id)
    for user in (await session.exec(select(User).where(*user_filters))).all():
        actor_map.setdefault(user.tenant_id, user.id)

    try:
        mark_filters = [
            InventoryItem.decay_status == "normal",
            InventoryItem.last_sold_at.is_not(None),
            InventoryItem.last_sold_at < mark_before,
        ]
        if tenant_id is not None:
            mark_filters.append(InventoryItem.tenant_id == tenant_id)
        to_mark = (
            await session.exec(
                select(InventoryItem).where(*mark_filters)
            )
        ).all()
        for item in to_mark:
            before = item.model_dump()
            item.decay_status = "liquidating"
            item.decay_started_at = now
            session.add(item)
            actor_id = actor_map.get(item.tenant_id)
            if actor_id is not None:
                session.add(
                    build_audit_log(
                        tenant_id=item.tenant_id,
                        user_id=actor_id,
                        action="DECAY_MARKED_LIQUIDATING",
                        entity_type="inventory_item",
                        entity_id=item.id,
                        before_state=before,
                        after_state=item.model_dump(),
                    )
                )
            result.marked_liquidating += 1

        discount_filters = [
            InventoryItem.decay_status == "liquidating",
            InventoryItem.decay_started_at.is_not(None),
            InventoryItem.decay_started_at <= discount_before,
        ]
        if tenant_id is not None:
            discount_filters.append(InventoryItem.tenant_id == tenant_id)
        to_discount = (
            await session.exec(
                select(InventoryItem).where(*discount_filters)
            )
        ).all()
        for item in to_discount:
            if item.variant_id not in variants:
                continue
            variant = variants[item.variant_id]
            before = item.model_dump()
            item.current_price = calculate_decay_price(
                item.current_price,
                variant.liquidation_floor_price,
                settings.decay_discount_pct,
            )
            item.decay_started_at = now
            session.add(item)
            actor_id = actor_map.get(item.tenant_id)
            if actor_id is not None:
                session.add(
                    build_audit_log(
                        tenant_id=item.tenant_id,
                        user_id=actor_id,
                        action="DECAY_DISCOUNT_APPLIED",
                        entity_type="inventory_item",
                        entity_id=item.id,
                        before_state=before,
                        after_state=item.model_dump(),
                    )
                )
            result.discounted += 1
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    return result
