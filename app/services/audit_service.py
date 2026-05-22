from __future__ import annotations

import uuid

from fastapi.encoders import jsonable_encoder
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.audit import AuditLog
from app.pagination import decode_cursor, encode_cursor
from app.schemas import AuditLogPageResponse, AuditLogResponse


def build_audit_log(
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    before_state: dict | None = None,
    after_state: dict | None = None,
) -> AuditLog:
    return AuditLog(
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_state=jsonable_encoder(before_state) if before_state is not None else None,
        after_state=jsonable_encoder(after_state) if after_state is not None else None,
    )


async def list_audit_logs(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    cursor: str | None,
    limit: int,
    entity_type: str | None = None,
    action: str | None = None,
) -> AuditLogPageResponse:
    decoded_cursor = decode_cursor(cursor)
    filters = [AuditLog.tenant_id == tenant_id]
    if entity_type is not None:
        filters.append(AuditLog.entity_type == entity_type)
    if action is not None:
        filters.append(AuditLog.action == action)
    if decoded_cursor is not None:
        filters.append(AuditLog.id < decoded_cursor)

    total_count = (await session.exec(select(func.count(AuditLog.id)).where(*filters))).one()
    rows = (
        await session.exec(
            select(AuditLog)
            .where(*filters)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit + 1)
        )
    ).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor(rows[-1].id) if has_more and rows else None
    return AuditLogPageResponse(
        next_cursor=next_cursor,
        has_more=has_more,
        total_count=total_count,
        data=[AuditLogResponse.model_validate(row) for row in rows],
    )

