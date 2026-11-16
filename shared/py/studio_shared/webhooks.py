"""Webhooks: when a user's job finishes, POST a signed JSON event to their URL.

Signature: header `X-Studio-Signature: sha256=<hex HMAC of the raw body with the webhook secret>`.
Only public https URLs are called (private/loopback addresses are refused at save time and again at delivery,
after DNS resolution) unless WEBHOOK_ALLOW_PRIVATE is set for local development and tests."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import socket
import time
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from . import crypto, db, storage
from .config import get_settings
from .errors import UserError

EVENTS = ("job.succeeded", "job.failed")
DISABLE_AFTER = 20  # consecutive failures


def check_url(url: str) -> str:
    url = url.strip()
    p = urlparse(url)
    allow_private = get_settings().webhook_allow_private
    if p.scheme != "https" and not (allow_private and p.scheme == "http"):
        raise UserError("Webhook URLs must start with https://")
    if not p.hostname or p.username or p.password:
        raise UserError("That webhook URL isn't valid")
    if not allow_private:
        _public_or_raise(p.hostname)
    return url


def _public_or_raise(host: str) -> None:
    if host.lower() in ("localhost",) or host.lower().endswith((".local", ".internal", ".localhost")):
        raise UserError("Webhook URLs must be public addresses")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise UserError("That webhook host can't be found") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise UserError("Webhook URLs must be public addresses")


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def targets(user_id: str, event: str) -> list[dict[str, Any]]:
    return db.fetch_all(
        "select id from webhooks where user_id = %s and active and %s = any(events)", [user_id, event]
    )


def job_payload(job: dict[str, Any], status: str, error: str | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {
        "job": {
            "id": str(job["id"]),
            "kind": job["kind"],
            "status": status,
            "error": error,
            "project_id": str(job["project_id"]) if job.get("project_id") else None,
            "tokens_charged": int(job.get("tokens_charged") or 0),
            "finished_at": datetime.now(UTC).isoformat(),
        }
    }
    if job.get("project_id"):
        p = db.fetch_one("select id, type, title from projects where id = %s", [job["project_id"]])
        if p:
            origin = get_settings().origins[0] if get_settings().origins else ""
            path = "clipper" if p["type"] == "clip" else "story"
            data["project"] = {
                "id": str(p["id"]),
                "type": p["type"],
                "title": p["title"],
                "url": f"{origin}/{path}/{p['id']}",
            }
            if status == "succeeded" and p["type"] == "clip":
                clips = db.fetch_all(
                    "select id, idx, title, duration_s, aspect, video_key, thumb_key, filename from clips "
                    "where project_id = %s and status = 'ready' and video_key is not null order by idx",
                    [p["id"]],
                )
                data["clips"] = [
                    {
                        "id": str(c["id"]),
                        "index": c["idx"],
                        "title": c["title"],
                        "aspect": c["aspect"],
                        "duration": float(c["duration_s"] or 0),
                        "video_url": storage.presign_get(
                            c["video_key"], expires=86400, filename=c["filename"]
                        ),
                        "thumbnail_url": storage.presign_get(c["thumb_key"], expires=86400)
                        if c["thumb_key"]
                        else None,
                    }
                    for c in clips
                ]
    return data


def deliver(hook_id: str, event: str, data: dict[str, Any], attempt: int = 1) -> dict[str, Any]:
    """Send one event now. Records the attempt; returns {ok, status, error}."""
    h = db.fetch_one("select * from webhooks where id = %s", [hook_id])
    if not h or not h["active"]:
        return {"ok": False, "status": None, "error": "webhook is off"}
    body = json.dumps(
        {"id": str(uuid.uuid4()), "event": event, "created_at": datetime.now(UTC).isoformat(), "data": data},
        separators=(",", ":"),
    ).encode()
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "ShortsStudio-Webhooks/1.0",
        "X-Studio-Event": event,
        "X-Studio-Signature": sign(crypto.decrypt(h["secret_enc"]), body),
    }
    started = time.monotonic()
    status_code: int | None = None
    error: str | None = None
    try:
        host = urlparse(h["url"]).hostname or ""
        if not get_settings().webhook_allow_private:
            _public_or_raise(host)
        with httpx.Client(timeout=10.0, follow_redirects=False) as c:
            r = c.post(h["url"], content=body, headers=headers)
        status_code = r.status_code
        ok = 200 <= r.status_code < 300
        if not ok:
            error = f"HTTP {r.status_code}"
    except UserError as e:
        ok, error = False, str(e)
    except httpx.HTTPError as e:
        ok, error = False, type(e).__name__
    ms = int((time.monotonic() - started) * 1000)
    db.execute(
        "insert into webhook_deliveries (webhook_id, event, attempt, status_code, ok, error, duration_ms) "
        "values (%s,%s,%s,%s,%s,%s,%s)",
        [hook_id, event, attempt, status_code, ok, error, ms],
    )
    db.execute(
        """update webhooks set last_status = %s, last_delivery_at = now(),
                  failures = case when %s then 0 else failures + 1 end,
                  active = case when not %s and failures + 1 >= %s then false else active end
            where id = %s""",
        [status_code, ok, ok, DISABLE_AFTER, hook_id],
    )
    return {"ok": ok, "status": status_code, "error": error}
