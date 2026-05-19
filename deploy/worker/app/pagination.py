from __future__ import annotations

import base64
import binascii
import json
import uuid

from app.errors import AppException


def encode_cursor(entity_id: uuid.UUID) -> str:
    raw = json.dumps({"id": str(entity_id)}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8")


def decode_cursor(cursor: str | None) -> uuid.UUID | None:
    if not cursor:
        return None
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        payload = json.loads(decoded)
        return uuid.UUID(payload["id"])
    except (binascii.Error, UnicodeDecodeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise AppException(
            status_code=400,
            code="INVALID_CURSOR",
            message="Cursor is invalid or expired. Restart pagination from the first page.",
        ) from exc
