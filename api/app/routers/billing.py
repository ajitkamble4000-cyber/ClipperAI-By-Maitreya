"""Payments with Razorpay: catalog, checkout, confirmation, webhook, history; owner settings and admin list."""

from __future__ import annotations

import json
import re
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from studio_shared import db, payments
from studio_shared.config import get_settings
from studio_shared.errors import UserError

from ..auth import AdminMember, CurrentMember, OwnerMember, SessionMember, audit
from ..ratelimit import check_ip_rate

router = APIRouter(tags=["billing"])


@router.get("/public/billing")
def public_billing() -> dict:
    """What can be bought online, for the pricing and tokens pages (no sign-in needed)."""
    return payments.catalog()


class CheckoutIn(BaseModel):
    kind: Literal["plan", "tokens"]
    plan_id: str | None = Field(default=None, max_length=40)
    period: Literal["month", "year"] | None = None
    pack_id: str | None = Field(default=None, max_length=40)


@router.post("/billing/checkout", status_code=201)
def checkout(body: CheckoutIn, m: SessionMember) -> dict:
    check_ip_rate(m.user_id, "checkout", limit=20)
    return payments.start_checkout(
        m, body.kind, plan_id=body.plan_id, period=body.period, pack_id=body.pack_id
    )


class ConfirmIn(BaseModel):
    razorpay_order_id: str = Field(max_length=60)
    razorpay_payment_id: str = Field(max_length=60)
    razorpay_signature: str = Field(max_length=200)


@router.post("/billing/confirm")
def confirm(body: ConfirmIn, m: SessionMember) -> dict:
    p = payments.confirm(m, body.razorpay_order_id, body.razorpay_payment_id, body.razorpay_signature)
    out = {"status": "paid", "description": p["description"]}
    if p.get("until"):
        out["until"] = p["until"]
    if p.get("tokens"):
        out["tokens"] = p["tokens"]
    if p.get("already") and p["kind"] == "plan":
        out["until"] = str(
            db.fetch_one("select plan_expires_at from members where user_id = %s", [m.user_id])[
                "plan_expires_at"
            ]
        )
    return out


@router.post("/billing/razorpay/webhook")
async def razorpay_webhook(request: Request) -> dict:
    """Razorpay → us. Set this URL and the webhook secret in the Razorpay dashboard (events: payment.captured,
    order.paid, payment.failed). Always answers 200 for events we don't track so Razorpay doesn't retry them."""
    body = await request.body()
    try:
        event = json.loads(body or b"{}")
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid JSON") from e
    try:
        result = payments.handle_webhook(body, request.headers.get("x-razorpay-signature", ""), event)
    except PermissionError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid signature") from e
    except UserError as e:
        if "Webhook secret" in str(e):
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e
        return {"ok": False, "result": str(e)}  # e.g. amount mismatch: recorded on the payment, don't retry
    return {"ok": True, "result": result}


@router.get("/billing/me")
def my_billing(m: CurrentMember) -> dict:
    """Your plan's end date (trial or paid) and your payments."""
    row = db.fetch_one(
        """select m.plan_id, p.name as plan_name, m.plan_source, m.plan_expires_at, m.plan_before_trial
             from members m join plans p on p.id = m.plan_id where m.user_id = %s""",
        [m.user_id],
    )
    history = db.fetch_all(
        """select id, kind, description, amount, currency, status, created_at, paid_at, payment_id
             from payments where user_id = %s and status <> 'created' order by created_at desc limit 50""",
        [m.user_id],
    )
    return {**row, "payments": history, "enabled": payments.enabled()}


# ---------------------------------------------------------------- admin
@router.get("/admin/payments")
def admin_payments(
    _: AdminMember,
    state: Annotated[str | None, Query(alias="status", max_length=20)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> dict:
    where, args = ["true"], []
    if state:
        where.append("p.status = %s")
        args.append(state)
    if q:
        where.append("(m.email ilike %s or p.order_id = %s or p.payment_id = %s)")
        args += [f"%{q}%", q, q]
    rows = db.fetch_all(
        f"""select p.id, p.kind, p.description, p.amount, p.currency, p.status, p.order_id, p.payment_id, p.error,
                   p.created_at, p.paid_at, m.email, coalesce(m.display_name, m.email) as user_name, p.user_id
              from payments p join members m on m.user_id = p.user_id
             where {" and ".join(where)} order by p.created_at desc limit %s""",
        [*args, limit],
    )
    summary = db.fetch_one(
        """select coalesce(sum(amount) filter (where paid_at > now() - interval '30 days'), 0)::bigint as revenue_30d,
                  coalesce(sum(amount), 0)::bigint as revenue_total,
                  count(*) filter (where paid_at > now() - interval '30 days') as paid_30d,
                  (select count(*) from members where plan_source = 'paid' and plan_expires_at > now()) as active_paid
             from payments where status = 'paid'"""
    )
    return {"payments": rows, "summary": summary}


def _webhook_url() -> str:
    return f"{(get_settings().public_api_url or '').rstrip('/')}/billing/razorpay/webhook"


@router.get("/admin/payments/settings")
def payment_settings(_: AdminMember) -> dict:
    return {**payments.key_status(), "webhook_url": _webhook_url()}


class KeysIn(BaseModel):
    key_id: str | None = Field(default=None, max_length=60)
    key_secret: str | None = Field(default=None, max_length=200)
    webhook_secret: str | None = Field(default=None, max_length=200)


@router.put("/admin/payments/settings")
def save_payment_settings(body: KeysIn, owner: OwnerMember) -> dict:
    if body.key_id and not re.fullmatch(r"rzp_(test|live)_[A-Za-z0-9]{6,40}", body.key_id.strip()):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The Key ID looks like rzp_test_… or rzp_live_…")
    payments.save_keys(body.key_id, body.key_secret, body.webhook_secret)
    audit(
        owner,
        "payments.keys",
        "settings",
        None,
        key_id=body.key_id,
        secret_changed=body.key_secret is not None,
        webhook_changed=body.webhook_secret is not None,
    )
    return {**payments.key_status(), "webhook_url": _webhook_url()}


@router.post("/admin/payments/test")
def test_payment_keys(_: OwnerMember) -> dict:
    return payments.test_keys()


@router.get("/admin/token-packs")
def list_packs(_: AdminMember) -> list[dict]:
    return db.fetch_all("select * from token_packs order by sort, price_inr")


class PackIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=40)
    tokens: int | None = Field(default=None, ge=100, le=10_000_000)
    price_inr: int | None = Field(default=None, ge=1, le=10_000_000)
    active: bool | None = None


@router.put("/admin/token-packs/{pack_id}")
def save_pack(pack_id: str, body: PackIn, owner: OwnerMember) -> dict:
    sets = {k: v for k, v in body.model_dump().items() if v is not None}
    if not sets:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing to change")
    if not re.fullmatch(r"[a-z0-9_-]{2,40}", pack_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pack ids use a-z, 0-9, - and _")
    exists = db.fetch_one("select 1 from token_packs where id = %s", [pack_id])
    if not exists and not {"name", "tokens", "price_inr"} <= set(sets):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A new pack needs a name, tokens and a price")
    if exists:
        cols = ", ".join(f"{k} = %({k})s" for k in sets)
        row = db.fetch_one(
            f"update token_packs set {cols} where id = %(id)s returning *", {**sets, "id": pack_id}
        )
    else:
        row = db.fetch_one(
            "insert into token_packs (id, name, tokens, price_inr, active, sort) values "
            "(%(id)s, %(name)s, %(tokens)s, %(price_inr)s, coalesce(%(active)s, true), 99) returning *",
            {"active": None, **sets, "id": pack_id},
        )
    audit(owner, "token_pack.save", "token_pack", pack_id, **sets)
    return row
