from __future__ import annotations

import uuid

from fastapi.encoders import jsonable_encoder

from app.models.audit import AuditLog


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

