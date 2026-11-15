"""Tokens for users (balance, history, prices, quotes, notifications) and token/plan controls for admins."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from studio_shared import db, tokens

from ..auth import AdminMember, CurrentMember, OwnerMember, audit

router = APIRouter(tags=["tokens"])


@router.get("/tokens")
def my_wallet(m: CurrentMember) -> dict:
    return tokens.get_wallet(m.user_id).to_json()


@router.get("/tokens/ledger")
def my_ledger(m: CurrentMember, limit: int = Query(default=50, ge=1, le=200)) -> list[dict]:
    return tokens.ledger(m.user_id, limit)


@router.get("/tokens/prices")
def token_prices() -> list[dict]:
    return db.fetch_all("select action, label, tokens, unit, description from token_prices order by sort")


@router.get("/tokens/quote")
def quote(
    m: CurrentMember,
    kind: str = Query(max_length=40),
    num_clips: int = 1,
    visual_analysis: bool = False,
    force_basic: bool = False,
    mode: str | None = None,
    count: int = 1,
    seconds: float = 30,
    translate: int = 0,
    jump_cuts: bool = False,
    links: int = Query(default=1, ge=1, le=50),
) -> dict:
    params: dict[str, Any] = {
        "num_clips": num_clips,
        "visual_analysis": visual_analysis,
        "force_basic": force_basic,
        "mode": mode,
        "count": count,
        "seconds": seconds,
        "translate_to": ["x"] * max(0, min(5, translate)),
        "remove_silence": jump_cuts,
        "batch": links > 1,
    }
    cost, items = tokens.quote(kind, params)
    if links > 1:  # batch: the same job once per link
        cost, items = cost * links, {k: v * links for k, v in items.items()}
    w = tokens.get_wallet(m.user_id)
    return {
        "tokens": 0 if w.unlimited else cost,
        "list_price": cost,
        "items": items,
        "balance": w.total,
        "unlimited": w.unlimited,
        "enough": w.unlimited or w.total >= cost,
    }


# ---------------------------------------------------------------- notifications
@router.get("/notifications")
def notifications(m: CurrentMember, limit: int = Query(default=30, ge=1, le=100)) -> dict:
    rows = db.fetch_all(
        "select * from notifications where user_id = %s order by created_at desc limit %s", [m.user_id, limit]
    )
    unread = db.fetch_one(
        "select count(*) as n from notifications where user_id = %s and read_at is null", [m.user_id]
    )["n"]
    return {"unread": unread, "items": rows}


@router.post("/notifications/read")
def mark_read(m: CurrentMember) -> dict:
    db.execute("update notifications set read_at = now() where user_id = %s and read_at is null", [m.user_id])
    return {"ok": True}


# ---------------------------------------------------------------- admin
class GrantIn(BaseModel):
    amount: int = Field(ge=-1_000_000, le=1_000_000)
    note: str = Field(default="", max_length=300)


@router.post("/admin/users/{user_id}/tokens")
def grant_tokens(user_id: str, body: GrantIn, admin: AdminMember) -> dict:
    target = db.fetch_one("select user_id, email, role from members where user_id = %s", [user_id])
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    w = tokens.grant(user_id, body.amount, actor_id=admin.user_id, note=body.note)
    if body.amount > 0:
        db.execute(
            "insert into notifications (user_id, kind, title, body) values (%s, 'tokens', %s, %s)",
            [user_id, f"You received {body.amount:,} bonus tokens", body.note],
        )
    audit(admin, "tokens.grant", "user", user_id, email=target["email"], amount=body.amount, note=body.note)
    return w.to_json()


@router.get("/admin/users/{user_id}/tokens")
def user_tokens(user_id: str, _: AdminMember) -> dict:
    return {"wallet": tokens.get_wallet(user_id).to_json(), "ledger": tokens.ledger(user_id, 100)}


class OverrideIn(BaseModel):
    daily_tokens: int | None = Field(default=None, ge=0, le=10_000_000)


@router.put("/admin/users/{user_id}/daily-tokens")
def daily_override(user_id: str, body: OverrideIn, admin: AdminMember) -> dict:
    db.execute(
        "update members set daily_tokens_override = %s where user_id = %s", [body.daily_tokens, user_id]
    )
    # Apply immediately: today's balance becomes the new allowance.
    db.execute("update wallets set daily_reset_at = now() where user_id = %s", [user_id])
    audit(admin, "tokens.daily_override", "user", user_id, daily_tokens=body.daily_tokens)
    return tokens.get_wallet(user_id).to_json()


class BroadcastIn(BaseModel):
    amount: int = Field(gt=0, le=1_000_000)
    plan_id: str | None = None
    note: str = Field(default="", max_length=300)


@router.post("/admin/tokens/broadcast")
def broadcast(body: BroadcastIn, owner: OwnerMember) -> dict:
    """Owner promo: give bonus tokens to every active user (optionally on one plan)."""
    q = "select user_id from members where status = 'active' and role = 'user' and team is null"
    args: list[Any] = []
    if body.plan_id:
        q += " and plan_id = %s"
        args.append(body.plan_id)
    users = db.fetch_all(q, args)
    for u in users:
        tokens.grant(str(u["user_id"]), body.amount, actor_id=owner.user_id, note=body.note or "Promo")
        db.execute(
            "insert into notifications (user_id, kind, title, body) values (%s, 'tokens', %s, %s)",
            [u["user_id"], f"You received {body.amount:,} bonus tokens", body.note],
        )
    audit(owner, "tokens.broadcast", "plan", body.plan_id, amount=body.amount, users=len(users))
    return {"users": len(users), "amount": body.amount}


class PriceIn(BaseModel):
    tokens: int = Field(ge=0, le=1_000_000)


@router.put("/admin/token-prices/{action}")
def set_price(action: str, body: PriceIn, admin: AdminMember) -> dict:
    row = db.fetch_one(
        "update token_prices set tokens = %s, updated_at = now() where action = %s returning *",
        [body.tokens, action],
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown action")
    tokens.clear_price_cache()
    audit(admin, "tokens.price", "action", action, tokens=body.tokens)
    return row


class PlanIn(BaseModel):
    name: str | None = Field(default=None, max_length=60)
    description: str | None = Field(default=None, max_length=300)
    daily_tokens: int | None = Field(default=None, ge=0, le=100_000_000)
    unlimited: bool | None = None
    price_usd_month: float | None = Field(default=None, ge=0, le=100_000)
    features: list[str] | None = None
    limits: dict[str, int | bool] | None = None
    public: bool | None = None
    highlight: bool | None = None


@router.get("/admin/plans")
def list_plans(_: AdminMember) -> list[dict]:
    rows = db.fetch_all(
        "select p.*, (select count(*) from members m where m.plan_id = p.id) as users from plans p order by sort"
    )
    return [{**r, "price_usd_month": float(r["price_usd_month"])} for r in rows]


KNOWN_LIMITS = {
    "max_clips_per_job",
    "max_upload_mb",
    "max_source_minutes",
    "concurrent_jobs",
    "watermark",
    "max_batch",
}
BASE_FEATURES = {"clipper", "captions", "story", "exports", "basic_voices"}


@router.put("/admin/plans/{plan_id}")
def update_plan(plan_id: str, body: PlanIn, owner: OwnerMember) -> dict:
    """Owner edits a plan. `limits` is merged into the current limits (send only what changes)."""
    from ..plans import FEATURE_LABELS

    sets: dict[str, Any] = {k: v for k, v in body.model_dump(exclude={"unlimited"}).items() if v is not None}
    if body.unlimited is True:
        sets["daily_tokens"] = None
    if body.limits is not None:
        unknown = set(body.limits) - KNOWN_LIMITS
        if unknown:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown limit: {', '.join(sorted(unknown))}")
    if body.features is not None:
        unknown = set(body.features) - BASE_FEATURES - set(FEATURE_LABELS)
        if unknown:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown feature: {', '.join(sorted(unknown))}")
        sets["features"] = list(dict.fromkeys(body.features))
    if "limits" in sets:
        sets["limits"] = db.jsonb(sets["limits"])
    if not sets and body.unlimited is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing to change")
    cols = ", ".join(f"{k} = limits || %({k})s" if k == "limits" else f"{k} = %({k})s" for k in sets)
    row = db.fetch_one(
        f"update plans set {cols}, updated_at = now() where id = %(id)s returning *", {**sets, "id": plan_id}
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown plan")
    audit(
        owner,
        "plan.update",
        "plan",
        plan_id,
        **{k: (v if k != "limits" else body.limits) for k, v in sets.items()},
    )
    return {**row, "price_usd_month": float(row["price_usd_month"])}
