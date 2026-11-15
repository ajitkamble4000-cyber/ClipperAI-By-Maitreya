"""Transcript cache keyed by source content hash + model, stored in R2."""

from __future__ import annotations

import json

from studio_shared import db, storage

from .base import Transcript


def get(content_hash: str, model: str) -> Transcript | None:
    row = db.fetch_one(
        "select r2_key from transcripts where content_hash = %s and model = %s", [content_hash, model]
    )
    if not row:
        return None
    try:
        return Transcript.from_json(json.loads(storage.get_bytes(row["r2_key"])))
    except Exception:  # noqa: BLE001 - a missing cache object just means re-transcribe
        return None


def put(content_hash: str, model: str, t: Transcript) -> str:
    key = f"cache/transcripts/{content_hash}-{model}.json"
    storage.put_bytes(key, json.dumps(t.to_json()).encode(), "application/json")
    db.execute(
        "insert into transcripts (content_hash, model, language, r2_key) values (%s,%s,%s,%s) "
        "on conflict (content_hash, model) do update set r2_key = excluded.r2_key, language = excluded.language",
        [content_hash, model, t.language, key],
    )
    return key
