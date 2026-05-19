from __future__ import annotations

import uuid

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.errors import AppException
from app.models.common import utcnow
from app.models.product import ProductVariant
from app.models.transfer import StockTransfer, TransferStatus
from app.models.user import User
from app.models.warehouse import InventoryItem, Warehouse
from app.pagination import decode_cursor, encode_cursor
from app.schemas import (
    TransferConfirmRequest,
    TransferCreateRequest,
    TransferPageResponse,
    TransferResponse,
)
from app.services.audit_service import build_audit_log
from app.services.email_job_service import queue_transfer_email


async def _get_transfer(
    session: AsyncSession, tenant_id: uuid.UUID, transfer_id: uuid.UUID, *, lock: bool
) -> StockTransfer:
    statement = select(StockTransfer).where(
        StockTransfer.id == transfer_id,
        StockTransfer.tenant_id == tenant_id,
    )
    if lock:
        statement = statement.with_for_update()
    transfer = (await session.exec(statement)).one_or_none()
    if transfer is None:
        raise AppException(status_code=404, code="NOT_FOUND", message="Transfer not found.")
    return transfer


async def _assert_tenant_entities_exist(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request: TransferCreateRequest,
) -> None:
    source = (
        await session.exec(
            select(Warehouse).where(
                Warehouse.id == request.from_warehouse_id,
                Warehouse.tenant_id == tenant_id,
                Warehouse.is_active.is_(True),
            )
        )
    ).one_or_none()
    destination = (
        await session.exec(
            select(Warehouse).where(
                Warehouse.id == request.to_warehouse_id,
                Warehouse.tenant_id == tenant_id,
                Warehouse.is_active.is_(True),
            )
        )
    ).one_or_none()
    variant = (
        await session.exec(
            select(ProductVariant).where(
                ProductVariant.id == request.variant_id,
                ProductVariant.tenant_id == tenant_id,
            )
        )
    ).one_or_none()
    if source is None or destination is None or variant is None:
        raise AppException(
            status_code=404,
            code="NOT_FOUND",
            message="Warehouse or variant was not found in this tenant.",
        )


async def create_transfer(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    actor: User,
    request: TransferCreateRequest,
) -> tuple[TransferResponse, bool]:
    if request.from_warehouse_id == request.to_warehouse_id:
        raise AppException(
            status_code=400,
            code="INVALID_TRANSFER",
            message="Source and destination warehouses must be different.",
        )

    existing = (
        await session.exec(
            select(StockTransfer).where(
                StockTransfer.tenant_id == tenant_id,
                StockTransfer.request_id == request.request_id,
            )
        )
    ).one_or_none()
    if existing is not None:
        return TransferResponse.model_validate(existing), False

    await _assert_tenant_entities_exist(session, tenant_id, request)

    transfer = StockTransfer(
        request_id=request.request_id,
        tenant_id=tenant_id,
        from_warehouse_id=request.from_warehouse_id,
        to_warehouse_id=request.to_warehouse_id,
        variant_id=request.variant_id,
        quantity=request.quantity,
        note=request.note,
        status=TransferStatus.IN_TRANSIT,
        initiated_by=actor.id,
    )

    try:
        source_inventory = (
            await session.exec(
                select(InventoryItem)
                .where(
                    InventoryItem.tenant_id == tenant_id,
                    InventoryItem.variant_id == request.variant_id,
                    InventoryItem.warehouse_id == request.from_warehouse_id,
                )
                .with_for_update()
            )
        ).one_or_none()
        if source_inventory is None or source_inventory.quantity < request.quantity:
            available = 0 if source_inventory is None else source_inventory.quantity
            raise AppException(
                status_code=409,
                code="INSUFFICIENT_STOCK",
                message=f"Source warehouse has {available} units, transfer requested {request.quantity}.",
            )

        before = source_inventory.model_dump()
        source_inventory.quantity -= request.quantity
        session.add(source_inventory)
        session.add(transfer)
        session.add(
            build_audit_log(
                tenant_id=tenant_id,
                user_id=actor.id,
                action="TRANSFER_CREATED",
                entity_type="stock_transfer",
                entity_id=transfer.id,
                before_state=None,
                after_state=transfer.model_dump(),
            )
        )
        session.add(
            build_audit_log(
                tenant_id=tenant_id,
                user_id=actor.id,
                action="TRANSFER_SOURCE_DEBIT",
                entity_type="inventory_item",
                entity_id=source_inventory.id,
                before_state=before,
                after_state=source_inventory.model_dump(),
            )
        )
        await session.commit()
    except AppException:
        await session.rollback()
        raise
    except IntegrityError:
        await session.rollback()
        existing = (
            await session.exec(
                select(StockTransfer).where(
                    StockTransfer.tenant_id == tenant_id,
                    StockTransfer.request_id == request.request_id,
                )
            )
        ).one_or_none()
        if existing is None:
            raise
        return TransferResponse.model_validate(existing), False

    await session.refresh(transfer)
    await queue_transfer_email(session=session, recipient=actor, transfer=transfer, event="created")
    return TransferResponse.model_validate(transfer), True


async def list_transfers(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    cursor: str | None,
    limit: int,
    status: TransferStatus | None,
    warehouse_id: uuid.UUID | None,
) -> TransferPageResponse:
    decoded_cursor = decode_cursor(cursor)
    filters = [StockTransfer.tenant_id == tenant_id]
    if decoded_cursor is not None:
        filters.append(StockTransfer.id > decoded_cursor)
    if status is not None:
        filters.append(StockTransfer.status == status)
    if warehouse_id is not None:
        filters.append(
            or_(
                StockTransfer.from_warehouse_id == warehouse_id,
                StockTransfer.to_warehouse_id == warehouse_id,
            )
        )

    total_count = (await session.exec(select(func.count(StockTransfer.id)).where(*filters))).one()
    transfers = (
        await session.exec(
            select(StockTransfer).where(*filters).order_by(StockTransfer.id.asc()).limit(limit + 1)
        )
    ).all()
    has_more = len(transfers) > limit
    transfers = transfers[:limit]
    next_cursor = encode_cursor(transfers[-1].id) if has_more and transfers else None
    return TransferPageResponse(
        next_cursor=next_cursor,
        has_more=has_more,
        total_count=total_count,
        data=[TransferResponse.model_validate(transfer) for transfer in transfers],
    )


async def confirm_transfer(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    actor: User,
    transfer_id: uuid.UUID,
    request: TransferConfirmRequest,
) -> TransferResponse:
    try:
        transfer = await _get_transfer(session, tenant_id, transfer_id, lock=True)
        if transfer.status != TransferStatus.IN_TRANSIT:
            raise AppException(
                status_code=400,
                code="INVALID_TRANSFER_STATE",
                message="Only in-transit transfers can be confirmed.",
            )

        received_quantity = request.received_quantity or transfer.quantity
        if received_quantity > transfer.quantity:
            raise AppException(
                status_code=409,
                code="TRANSFER_OVER_RECEIVED",
                message=(
                    "Received quantity cannot be greater than the quantity that was "
                    f"sent. Sent {transfer.quantity}, received {received_quantity}."
                ),
            )
        destination_inventory = (
            await session.exec(
                select(InventoryItem)
                .where(
                    InventoryItem.tenant_id == tenant_id,
                    InventoryItem.variant_id == transfer.variant_id,
                    InventoryItem.warehouse_id == transfer.to_warehouse_id,
                )
                .with_for_update()
            )
        ).one_or_none()
        variant = (
            await session.exec(
                select(ProductVariant).where(
                    ProductVariant.id == transfer.variant_id,
                    ProductVariant.tenant_id == tenant_id,
                )
            )
        ).one()

        if destination_inventory is None:
            destination_inventory = InventoryItem(
                tenant_id=tenant_id,
                variant_id=transfer.variant_id,
                warehouse_id=transfer.to_warehouse_id,
                quantity=0,
                current_price=variant.selling_price,
            )
            session.add(destination_inventory)

        before_inventory = destination_inventory.model_dump()
        destination_inventory.quantity += received_quantity
        transfer.status = TransferStatus.COMPLETED
        transfer.confirmed_by = actor.id
        transfer.completed_at = utcnow()
        session.add(destination_inventory)
        session.add(transfer)
        session.add(
            build_audit_log(
                tenant_id=tenant_id,
                user_id=actor.id,
                action="TRANSFER_COMPLETED",
                entity_type="stock_transfer",
                entity_id=transfer.id,
                before_state=None,
                after_state=transfer.model_dump(),
            )
        )
        session.add(
            build_audit_log(
                tenant_id=tenant_id,
                user_id=actor.id,
                action="TRANSFER_DESTINATION_CREDIT",
                entity_type="inventory_item",
                entity_id=destination_inventory.id,
                before_state=before_inventory,
                after_state=destination_inventory.model_dump(),
            )
        )
        if received_quantity != transfer.quantity:
            session.add(
                build_audit_log(
                    tenant_id=tenant_id,
                    user_id=actor.id,
                    action="TRANSFER_DISCREPANCY_REPORTED",
                    entity_type="stock_transfer",
                    entity_id=transfer.id,
                    before_state={"expected_quantity": transfer.quantity},
                    after_state={"received_quantity": received_quantity},
                )
            )
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    await session.refresh(transfer)
    await queue_transfer_email(session=session, recipient=actor, transfer=transfer, event="completed")
    return TransferResponse.model_validate(transfer)


async def cancel_transfer(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    actor: User,
    transfer_id: uuid.UUID,
) -> TransferResponse:
    try:
        transfer = await _get_transfer(session, tenant_id, transfer_id, lock=True)
        if transfer.status != TransferStatus.IN_TRANSIT:
            raise AppException(
                status_code=400,
                code="INVALID_TRANSFER_STATE",
                message="Only in-transit transfers can be cancelled.",
            )

        source_inventory = (
            await session.exec(
                select(InventoryItem)
                .where(
                    InventoryItem.tenant_id == tenant_id,
                    InventoryItem.variant_id == transfer.variant_id,
                    InventoryItem.warehouse_id == transfer.from_warehouse_id,
                )
                .with_for_update()
            )
        ).one()
        before_inventory = source_inventory.model_dump()
        source_inventory.quantity += transfer.quantity
        transfer.status = TransferStatus.CANCELLED
        transfer.completed_at = utcnow()
        session.add(source_inventory)
        session.add(transfer)
        session.add(
            build_audit_log(
                tenant_id=tenant_id,
                user_id=actor.id,
                action="TRANSFER_CANCELLED",
                entity_type="stock_transfer",
                entity_id=transfer.id,
                before_state=None,
                after_state=transfer.model_dump(),
            )
        )
        session.add(
            build_audit_log(
                tenant_id=tenant_id,
                user_id=actor.id,
                action="TRANSFER_SOURCE_RESTORE",
                entity_type="inventory_item",
                entity_id=source_inventory.id,
                before_state=before_inventory,
                after_state=source_inventory.model_dump(),
            )
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    await session.refresh(transfer)
    return TransferResponse.model_validate(transfer)
