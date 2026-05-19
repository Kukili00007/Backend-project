from __future__ import annotations

import uuid

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.errors import AppException
from app.models.common import utcnow
from app.models.procurement import PurchaseOrder, PurchaseOrderStatus, Supplier
from app.models.product import ProductVariant
from app.models.user import User
from app.models.warehouse import InventoryItem, Warehouse
from app.pagination import decode_cursor, encode_cursor
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
from app.services.audit_service import build_audit_log
from app.services.email_job_service import queue_purchase_order_confirmation_email


async def create_supplier(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request: SupplierCreateRequest,
) -> SupplierResponse:
    supplier = Supplier(
        tenant_id=tenant_id,
        name=request.name,
        contact_email=str(request.contact_email) if request.contact_email else None,
        phone=request.phone,
        lead_time_days=request.lead_time_days,
    )
    try:
        session.add(supplier)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AppException(
            status_code=409,
            code="SUPPLIER_CONFLICT",
            message="A supplier with this name already exists for this tenant.",
        ) from exc
    await session.refresh(supplier)
    return SupplierResponse.model_validate(supplier)


async def list_suppliers(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    cursor: str | None,
    limit: int,
    active_only: bool,
) -> SupplierPageResponse:
    decoded_cursor = decode_cursor(cursor)
    filters = [Supplier.tenant_id == tenant_id]
    if decoded_cursor is not None:
        filters.append(Supplier.id > decoded_cursor)
    if active_only:
        filters.append(Supplier.is_active.is_(True))

    total_count = (await session.exec(select(func.count(Supplier.id)).where(*filters))).one()
    suppliers = (
        await session.exec(
            select(Supplier).where(*filters).order_by(Supplier.id.asc()).limit(limit + 1)
        )
    ).all()
    has_more = len(suppliers) > limit
    suppliers = suppliers[:limit]
    next_cursor = encode_cursor(suppliers[-1].id) if has_more and suppliers else None
    return SupplierPageResponse(
        next_cursor=next_cursor,
        has_more=has_more,
        total_count=total_count,
        data=[SupplierResponse.model_validate(supplier) for supplier in suppliers],
    )


async def update_supplier(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supplier_id: uuid.UUID,
    request: SupplierUpdateRequest,
) -> SupplierResponse:
    supplier = (
        await session.exec(
            select(Supplier).where(Supplier.id == supplier_id, Supplier.tenant_id == tenant_id)
        )
    ).one_or_none()
    if supplier is None:
        raise AppException(status_code=404, code="NOT_FOUND", message="Supplier not found.")

    updates = request.model_dump(exclude_unset=True)
    if "contact_email" in updates and updates["contact_email"] is not None:
        updates["contact_email"] = str(updates["contact_email"])
    for field, value in updates.items():
        setattr(supplier, field, value)

    try:
        session.add(supplier)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AppException(
            status_code=409,
            code="SUPPLIER_CONFLICT",
            message="A supplier with this name already exists for this tenant.",
        ) from exc
    await session.refresh(supplier)
    return SupplierResponse.model_validate(supplier)


async def get_supplier_detail(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supplier_id: uuid.UUID,
) -> SupplierResponse:
    supplier = (
        await session.exec(
            select(Supplier).where(Supplier.id == supplier_id, Supplier.tenant_id == tenant_id)
        )
    ).one_or_none()
    if supplier is None:
        raise AppException(status_code=404, code="NOT_FOUND", message="Supplier not found.")
    return SupplierResponse.model_validate(supplier)


async def deactivate_supplier(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supplier_id: uuid.UUID,
) -> SupplierResponse:
    return await update_supplier(
        session=session,
        tenant_id=tenant_id,
        supplier_id=supplier_id,
        request=SupplierUpdateRequest(is_active=False),
    )


async def _get_supplier(session: AsyncSession, tenant_id: uuid.UUID, supplier_id: uuid.UUID) -> Supplier:
    supplier = (
        await session.exec(
            select(Supplier).where(
                Supplier.id == supplier_id,
                Supplier.tenant_id == tenant_id,
                Supplier.is_active.is_(True),
            )
        )
    ).one_or_none()
    if supplier is None:
        raise AppException(status_code=404, code="NOT_FOUND", message="Supplier not found.")
    return supplier


async def _get_warehouse(session: AsyncSession, tenant_id: uuid.UUID, warehouse_id: uuid.UUID) -> Warehouse:
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


async def _get_variant(session: AsyncSession, tenant_id: uuid.UUID, variant_id: uuid.UUID) -> ProductVariant:
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


async def _get_purchase_order(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    purchase_order_id: uuid.UUID,
    *,
    lock: bool = False,
) -> PurchaseOrder:
    statement = select(PurchaseOrder).where(
        PurchaseOrder.id == purchase_order_id,
        PurchaseOrder.tenant_id == tenant_id,
    )
    if lock:
        statement = statement.with_for_update()
    purchase_order = (await session.exec(statement)).one_or_none()
    if purchase_order is None:
        raise AppException(status_code=404, code="NOT_FOUND", message="Purchase order not found.")
    return purchase_order


async def create_purchase_order(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    actor: User,
    request: PurchaseOrderCreateRequest,
) -> PurchaseOrderResponse:
    await _get_supplier(session, tenant_id, request.supplier_id)
    await _get_warehouse(session, tenant_id, request.warehouse_id)
    await _get_variant(session, tenant_id, request.variant_id)

    purchase_order = PurchaseOrder(
        tenant_id=tenant_id,
        po_number=request.po_number,
        supplier_id=request.supplier_id,
        warehouse_id=request.warehouse_id,
        variant_id=request.variant_id,
        quantity=request.quantity,
        expected_unit_cost=request.expected_unit_cost,
        created_by=actor.id,
    )
    try:
        session.add(purchase_order)
        session.add(
            build_audit_log(
                tenant_id=tenant_id,
                user_id=actor.id,
                action="PURCHASE_ORDER_CREATED",
                entity_type="purchase_order",
                entity_id=purchase_order.id,
                before_state=None,
                after_state=purchase_order.model_dump(),
            )
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AppException(
            status_code=409,
            code="PURCHASE_ORDER_CONFLICT",
            message="A purchase order with this number already exists for this tenant.",
        ) from exc
    await session.refresh(purchase_order)
    return PurchaseOrderResponse.model_validate(purchase_order)


async def list_purchase_orders(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    cursor: str | None,
    limit: int,
    status: PurchaseOrderStatus | None,
) -> PurchaseOrderPageResponse:
    decoded_cursor = decode_cursor(cursor)
    filters = [PurchaseOrder.tenant_id == tenant_id]
    if decoded_cursor is not None:
        filters.append(PurchaseOrder.id > decoded_cursor)
    if status is not None:
        filters.append(PurchaseOrder.status == status)

    total_count = (await session.exec(select(func.count(PurchaseOrder.id)).where(*filters))).one()
    purchase_orders = (
        await session.exec(
            select(PurchaseOrder)
            .where(*filters)
            .order_by(PurchaseOrder.id.asc())
            .limit(limit + 1)
        )
    ).all()
    has_more = len(purchase_orders) > limit
    purchase_orders = purchase_orders[:limit]
    next_cursor = encode_cursor(purchase_orders[-1].id) if has_more and purchase_orders else None
    return PurchaseOrderPageResponse(
        next_cursor=next_cursor,
        has_more=has_more,
        total_count=total_count,
        data=[PurchaseOrderResponse.model_validate(po) for po in purchase_orders],
    )


async def get_purchase_order(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    purchase_order_id: uuid.UUID,
) -> PurchaseOrderResponse:
    purchase_order = await _get_purchase_order(session, tenant_id, purchase_order_id)
    return PurchaseOrderResponse.model_validate(purchase_order)


async def submit_purchase_order(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    actor: User,
    purchase_order_id: uuid.UUID,
) -> PurchaseOrderResponse:
    purchase_order = await _get_purchase_order(session, tenant_id, purchase_order_id, lock=True)
    if purchase_order.status != PurchaseOrderStatus.DRAFT:
        raise AppException(
            status_code=400,
            code="INVALID_PURCHASE_ORDER_STATE",
            message="Only draft purchase orders can be submitted.",
        )
    supplier = await _get_supplier(session, tenant_id, purchase_order.supplier_id)
    warehouse = await _get_warehouse(session, tenant_id, purchase_order.warehouse_id)
    variant = await _get_variant(session, tenant_id, purchase_order.variant_id)

    before = purchase_order.model_dump()
    purchase_order.status = PurchaseOrderStatus.SUBMITTED
    purchase_order.submitted_at = utcnow()
    session.add(purchase_order)
    session.add(
        build_audit_log(
            tenant_id=tenant_id,
            user_id=actor.id,
            action="PURCHASE_ORDER_SUBMITTED",
            entity_type="purchase_order",
            entity_id=purchase_order.id,
            before_state=before,
            after_state=purchase_order.model_dump(),
        )
    )
    await session.commit()
    await session.refresh(purchase_order)
    await queue_purchase_order_confirmation_email(
        session=session,
        supplier=supplier,
        purchase_order=purchase_order,
        variant=variant,
        warehouse=warehouse,
    )
    return PurchaseOrderResponse.model_validate(purchase_order)


async def confirm_purchase_order(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    actor: User,
    purchase_order_id: uuid.UUID,
) -> PurchaseOrderResponse:
    purchase_order = await _get_purchase_order(session, tenant_id, purchase_order_id, lock=True)
    if purchase_order.status != PurchaseOrderStatus.SUBMITTED:
        raise AppException(
            status_code=400,
            code="INVALID_PURCHASE_ORDER_STATE",
            message="Only submitted purchase orders can be confirmed.",
        )
    before = purchase_order.model_dump()
    purchase_order.status = PurchaseOrderStatus.CONFIRMED
    purchase_order.confirmed_at = utcnow()
    session.add(purchase_order)
    session.add(
        build_audit_log(
            tenant_id=tenant_id,
            user_id=actor.id,
            action="PURCHASE_ORDER_CONFIRMED",
            entity_type="purchase_order",
            entity_id=purchase_order.id,
            before_state=before,
            after_state=purchase_order.model_dump(),
        )
    )
    await session.commit()
    await session.refresh(purchase_order)
    return PurchaseOrderResponse.model_validate(purchase_order)


async def receive_purchase_order(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    actor: User,
    purchase_order_id: uuid.UUID,
    request: PurchaseOrderReceiveRequest,
) -> PurchaseOrderResponse:
    try:
        purchase_order = await _get_purchase_order(session, tenant_id, purchase_order_id, lock=True)
        if purchase_order.status not in {
            PurchaseOrderStatus.SUBMITTED,
            PurchaseOrderStatus.CONFIRMED,
        }:
            raise AppException(
                status_code=400,
                code="INVALID_PURCHASE_ORDER_STATE",
                message="Only submitted or confirmed purchase orders can be received.",
            )
        received_quantity = request.received_quantity or purchase_order.quantity
        if received_quantity > purchase_order.quantity:
            raise AppException(
                status_code=409,
                code="PURCHASE_ORDER_OVER_RECEIVED",
                message=(
                    "Received quantity cannot be greater than ordered quantity. "
                    f"Ordered {purchase_order.quantity}, received {received_quantity}."
                ),
            )
        variant = await _get_variant(session, tenant_id, purchase_order.variant_id)
        await _get_warehouse(session, tenant_id, purchase_order.warehouse_id)
        inventory_item = (
            await session.exec(
                select(InventoryItem)
                .where(
                    InventoryItem.tenant_id == tenant_id,
                    InventoryItem.variant_id == purchase_order.variant_id,
                    InventoryItem.warehouse_id == purchase_order.warehouse_id,
                )
                .with_for_update()
            )
        ).one_or_none()
        if inventory_item is None:
            inventory_item = InventoryItem(
                tenant_id=tenant_id,
                variant_id=purchase_order.variant_id,
                warehouse_id=purchase_order.warehouse_id,
                quantity=0,
                current_price=variant.selling_price,
            )
            session.add(inventory_item)

        before_inventory = inventory_item.model_dump()
        before_po = purchase_order.model_dump()
        inventory_item.quantity += received_quantity
        purchase_order.status = PurchaseOrderStatus.RECEIVED
        purchase_order.received_at = utcnow()
        session.add(inventory_item)
        session.add(purchase_order)
        session.add(
            build_audit_log(
                tenant_id=tenant_id,
                user_id=actor.id,
                action="PURCHASE_ORDER_RECEIVED",
                entity_type="purchase_order",
                entity_id=purchase_order.id,
                before_state=before_po,
                after_state=purchase_order.model_dump(),
            )
        )
        session.add(
            build_audit_log(
                tenant_id=tenant_id,
                user_id=actor.id,
                action="PURCHASE_ORDER_INVENTORY_CREDIT",
                entity_type="inventory_item",
                entity_id=inventory_item.id,
                before_state=before_inventory,
                after_state=inventory_item.model_dump(),
            )
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    await session.refresh(purchase_order)
    return PurchaseOrderResponse.model_validate(purchase_order)


async def cancel_purchase_order(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    actor: User,
    purchase_order_id: uuid.UUID,
) -> PurchaseOrderResponse:
    purchase_order = await _get_purchase_order(session, tenant_id, purchase_order_id, lock=True)
    if purchase_order.status == PurchaseOrderStatus.RECEIVED:
        raise AppException(
            status_code=400,
            code="INVALID_PURCHASE_ORDER_STATE",
            message="Received purchase orders cannot be cancelled.",
        )
    before = purchase_order.model_dump()
    purchase_order.status = PurchaseOrderStatus.CANCELLED
    session.add(purchase_order)
    session.add(
        build_audit_log(
            tenant_id=tenant_id,
            user_id=actor.id,
            action="PURCHASE_ORDER_CANCELLED",
            entity_type="purchase_order",
            entity_id=purchase_order.id,
            before_state=before,
            after_state=purchase_order.model_dump(),
        )
    )
    await session.commit()
    await session.refresh(purchase_order)
    return PurchaseOrderResponse.model_validate(purchase_order)
