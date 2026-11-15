"""Health, public plan list, active announcements."""

from __future__ import annotations

from fastapi import APIRouter
from studio_shared import db

from ..auth import CurrentMember

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict:
    db.fetch_one("select 1 as ok")
    return {"ok": True}


@router.get("/plans")
def public_plans() -> list[dict]:
    """Plans for the public pricing page (no sign-in needed)."""
    rows = db.fetch_all(
        "select id, name, description, daily_tokens, price_usd_month, features, limits, highlight "
        "from plans where public order by sort"
    )
    return [{**r, "price_usd_month": float(r["price_usd_month"])} for r in rows]


@router.get("/announcements")
def announcements(_: CurrentMember) -> list[dict]:
    return db.fetch_all(
        "select id, message, level, created_at from announcements "
        "where active and (expires_at is null or expires_at > now()) order by created_at desc limit 3"
    )
