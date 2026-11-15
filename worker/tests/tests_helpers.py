"""Small DB helpers shared by worker integration tests."""

from __future__ import annotations

import uuid
from pathlib import Path

from studio_shared import db, storage


def make_member(plan: str = "free", role: str = "user") -> str:
    uid = str(uuid.uuid4())
    email = f"wk-{uid[:8]}@example.com"
    db.execute(
        "insert into auth.users (id, email, aud, role) values (%s, %s, 'authenticated', 'authenticated')",
        [uid, email],
    )
    db.execute(
        "insert into members (user_id, email, role) values (%s, %s, %s) on conflict (user_id) do nothing",
        [uid, email, role],
    )
    db.execute("update members set plan_id = %s, role = %s where user_id = %s", [plan, role, uid])
    return uid


def upload_source(path: Path, uid: str) -> str:
    up = str(uuid.uuid4())
    key = f"uploads/{uid}/{up}/{path.name}"
    storage.upload_file(path, key, "video/mp4")
    db.execute(
        "insert into uploads (id, user_id, purpose, r2_key, filename, content_type, size_bytes, part_size, status) "
        "values (%s,%s,'source',%s,%s,'video/mp4',%s,%s,'complete')",
        [up, uid, key, path.name, path.stat().st_size, path.stat().st_size],
    )
    return up
