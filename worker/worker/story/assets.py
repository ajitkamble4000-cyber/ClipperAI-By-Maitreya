"""Content-addressed cache for generated story assets: same inputs -> same R2 object, no re-paying."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from studio_shared import db


def key_for(**parts: Any) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:40]


def get(h: str) -> str | None:
    row = db.fetch_one("select r2_key from assets where hash = %s", [h])
    return row["r2_key"] if row else None


def put(h: str, kind: str, r2_key: str, meta: dict[str, Any] | None = None) -> None:
    db.execute(
        "insert into assets (hash, kind, r2_key, meta) values (%s,%s,%s,%s) on conflict (hash) do update set r2_key = excluded.r2_key",
        [h, kind, r2_key, meta or {}],
    )
