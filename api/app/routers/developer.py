"""Developer API (Business): personal API keys, webhooks, and a clips listing handy for automations."""

from __future__ import annotations

import secrets
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from studio_shared import apikeys, crypto, db, storage, webhooks

from ..access import project_for
from ..auth import CurrentMember, SessionMember, audit
from ..plans import require_feature

router = APIRouter(tags=["developer"])
MAX_KEYS = 10
MAX_HOOKS = 5


# ---------------------------------------------------------------- API keys
@router.get("/api-keys")
def list_keys(m: SessionMember) -> list[dict]:
    return db.fetch_all(
        "select id, name, prefix, created_at, last_used_at from api_keys where user_id = %s and revoked_at is null "
        "order by created_at desc",
        [m.user_id],
    )


class KeyIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)


@router.post("/api-keys", status_code=201)
def create_key(body: KeyIn, m: SessionMember) -> dict:
    require_feature(m, "api_access")
    n = db.fetch_one(
        "select count(*) as n from api_keys where user_id = %s and revoked_at is null", [m.user_id]
    )["n"]
    if n >= MAX_KEYS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"You can have up to {MAX_KEYS} keys. Revoke one first."
        )
    key = apikeys.generate()
    row = db.fetch_one(
        "insert into api_keys (user_id, name, prefix, key_hash) values (%s,%s,%s,%s) "
        "returning id, name, prefix, created_at",
        [m.user_id, body.name.strip(), apikeys.display_prefix(key), apikeys.hash_key(key)],
    )
    audit(m, "apikey.create", "api_key", str(row["id"]), name=body.name)
    return {**row, "key": key}  # the only time the full key is shown


@router.delete("/api-keys/{key_id}")
def revoke_key(key_id: str, m: SessionMember) -> dict:
    try:
        row = db.fetch_one(
            "update api_keys set revoked_at = now() where id = %s and user_id = %s and revoked_at is null returning id",
            [key_id, m.user_id],
        )
    except Exception as e:  # noqa: BLE001 - bad uuid
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Key not found") from e
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Key not found")
    audit(m, "apikey.revoke", "api_key", key_id)
    return {"ok": True}


# ---------------------------------------------------------------- webhooks
Event = Literal["job.succeeded", "job.failed"]


class HookIn(BaseModel):
    url: str = Field(max_length=2048)
    events: list[Event] = Field(default_factory=lambda: ["job.succeeded", "job.failed"], min_length=1)


def _hook_view(h: dict) -> dict:
    return {
        k: h[k]
        for k in (
            "id",
            "url",
            "events",
            "active",
            "failures",
            "last_status",
            "last_delivery_at",
            "created_at",
        )
    }


@router.get("/webhooks")
def list_hooks(m: SessionMember) -> list[dict]:
    rows = db.fetch_all("select * from webhooks where user_id = %s order by created_at", [m.user_id])
    out = []
    for h in rows:
        v = _hook_view(h)
        v["recent"] = db.fetch_all(
            "select event, attempt, status_code, ok, error, duration_ms, created_at from webhook_deliveries "
            "where webhook_id = %s order by created_at desc limit 10",
            [h["id"]],
        )
        out.append(v)
    return out


@router.post("/webhooks", status_code=201)
def create_hook(body: HookIn, m: SessionMember) -> dict:
    require_feature(m, "api_access")
    if db.fetch_one("select count(*) as n from webhooks where user_id = %s", [m.user_id])["n"] >= MAX_HOOKS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"You can have up to {MAX_HOOKS} webhooks.")
    url = webhooks.check_url(body.url)
    secret = "whsec_" + secrets.token_urlsafe(24)
    row = db.fetch_one(
        "insert into webhooks (user_id, url, secret_enc, events) values (%s,%s,%s,%s) returning *",
        [m.user_id, url, crypto.encrypt(secret), list(dict.fromkeys(body.events))],
    )
    audit(m, "webhook.create", "webhook", str(row["id"]), url=url)
    return {**_hook_view(row), "secret": secret}  # shown once: used to check the signature


class HookPatch(BaseModel):
    active: bool


def _own_hook(hook_id: str, m) -> dict:
    try:
        h = db.fetch_one("select * from webhooks where id = %s and user_id = %s", [hook_id, m.user_id])
    except Exception as e:  # noqa: BLE001 - bad uuid
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Webhook not found") from e
    if not h:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Webhook not found")
    return h


@router.patch("/webhooks/{hook_id}")
def update_hook(hook_id: str, body: HookPatch, m: SessionMember) -> dict:
    _own_hook(hook_id, m)
    row = db.fetch_one(
        "update webhooks set active = %s, failures = case when %s then 0 else failures end where id = %s returning *",
        [body.active, body.active, hook_id],
    )
    return _hook_view(row)


@router.delete("/webhooks/{hook_id}")
def delete_hook(hook_id: str, m: SessionMember) -> dict:
    _own_hook(hook_id, m)
    db.execute("delete from webhooks where id = %s", [hook_id])
    return {"ok": True}


@router.post("/webhooks/{hook_id}/test")
def test_hook(hook_id: str, m: SessionMember) -> dict:
    """Send a `ping` event right now and report what the URL answered."""
    _own_hook(hook_id, m)
    return webhooks.deliver(hook_id, "ping", {"message": "Webhook test from Shorts Studio"})


# ---------------------------------------------------------------- handy for automations
@router.get("/projects/{project_id}/clips")
def project_clips(project_id: str, m: CurrentMember) -> list[dict]:
    """Finished clips with download links (valid 24 hours)."""
    project_for(project_id, m)
    rows = db.fetch_all(
        "select id, idx, title, description, hashtags, duration_s, aspect, status, video_key, thumb_key, filename "
        "from clips where project_id = %s order by idx",
        [project_id],
    )
    out = []
    for c in rows:
        ready = c["status"] == "ready" and c["video_key"]
        out.append(
            {
                "id": c["id"],
                "index": c["idx"],
                "title": c["title"],
                "description": c["description"],
                "hashtags": c["hashtags"],
                "duration": float(c["duration_s"] or 0),
                "aspect": c["aspect"],
                "status": c["status"],
                "video_url": storage.presign_get(c["video_key"], expires=86400, filename=c["filename"])
                if ready
                else None,
                "thumbnail_url": storage.presign_get(c["thumb_key"], expires=86400)
                if ready and c["thumb_key"]
                else None,
            }
        )
    return out
