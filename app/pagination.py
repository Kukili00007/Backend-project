from __future__ import annotations

import base64
import json
import uuid


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
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid cursor.") from exc

