"""Online payments with Razorpay: plans (per month / per year) and bonus-token packs, priced in INR.

Flow: the API creates a Razorpay order and a `payments` row → the browser opens Razorpay Checkout → the browser
sends back the payment id and signature (`confirm`) and Razorpay also calls the webhook. Either one fulfils the
payment exactly once (`fulfill` locks the row). Signatures are always checked with the secret; amounts are checked
against what we asked for.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from . import crypto, db, tokens
from .config import get_settings
from .errors import UserError
from .notify import notify, notify_admins

log = logging.getLogger(__name__)

PERIOD_DAYS = {"month": 30, "year": 365}
CURRENCY = "INR"


# ---------------------------------------------------------------- keys
@dataclass(frozen=True)
class Keys:
    key_id: str
    key_secret: str
    webhook_secret: str | None
    source: str  # "env" | "settings"


def keys() -> Keys | None:
    """Razorpay keys from the environment, else from Admin → Payments. None until both id and secret exist."""
    s = get_settings()
    if s.razorpay_key_id and s.razorpay_key_secret and s.razorpay_key_secret.get_secret_value():
        wh = s.razorpay_webhook_secret.get_secret_value() if s.razorpay_webhook_secret else None
        return Keys(s.razorpay_key_id, s.razorpay_key_secret.get_secret_value(), wh or None, "env")
    row = db.fetch_one(
        "select razorpay_key_id, razorpay_secret_enc, razorpay_webhook_secret_enc from settings where id = 1"
    )
    if not row or not row["razorpay_key_id"] or not row["razorpay_secret_enc"]:
        return None
    wh = row["razorpay_webhook_secret_enc"]
    return Keys(
        row["razorpay_key_id"],
        crypto.decrypt(row["razorpay_secret_enc"]),
        crypto.decrypt(wh) if wh else None,
        "settings",
    )


def enabled() -> bool:
    try:
        return keys() is not None
    except crypto.CryptoError:
        return False


def save_keys(key_id: str | None, key_secret: str | None, webhook_secret: str | None) -> None:
    """Owner sets (or clears with "") the keys. None leaves a value unchanged."""
    sets: dict[str, Any] = {}
    if key_id is not None:
        sets["razorpay_key_id"] = key_id.strip() or None
    if key_secret is not None:
        sets["razorpay_secret_enc"] = crypto.encrypt(key_secret.strip()) if key_secret.strip() else None
    if webhook_secret is not None:
        sets["razorpay_webhook_secret_enc"] = (
            crypto.encrypt(webhook_secret.strip()) if webhook_secret.strip() else None
        )
    if not sets:
        return
    cols = ", ".join(f"{k} = %({k})s" for k in sets)
    db.execute(f"update settings set {cols}, updated_at = now() where id = 1", sets)


def key_status() -> dict[str, Any]:
    """What the admin page shows (never the secrets themselves)."""
    s = get_settings()
    row = (
        db.fetch_one(
            "select razorpay_key_id, razorpay_secret_enc is not null as has_secret, "
            "razorpay_webhook_secret_enc is not null as has_webhook from settings where id = 1"
        )
        or {}
    )
    env = bool(s.razorpay_key_id and s.razorpay_key_secret and s.razorpay_key_secret.get_secret_value())
    key_id = s.razorpay_key_id if env else row.get("razorpay_key_id")
    return {
        "source": "env" if env else ("settings" if row.get("razorpay_key_id") else "none"),
        "key_id": key_id,
        "mode": ("test" if key_id.startswith("rzp_test_") else "live") if key_id else None,
        "has_secret": env or bool(row.get("has_secret")),
        "has_webhook_secret": bool(
            (s.razorpay_webhook_secret and s.razorpay_webhook_secret.get_secret_value())
            or row.get("has_webhook")
        ),
        "enabled": enabled(),
    }


# ---------------------------------------------------------------- signatures
def _hmac(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def payment_signature_ok(order_id: str, payment_id: str, signature: str, secret: str) -> bool:
    """Checkout success: signature = HMAC-SHA256(order_id + "|" + payment_id, key_secret)."""
    return hmac.compare_digest(_hmac(secret, f"{order_id}|{payment_id}".encode()), signature or "")


def webhook_signature_ok(body: bytes, signature: str, secret: str) -> bool:
    """Webhook: X-Razorpay-Signature = HMAC-SHA256(raw body, webhook secret)."""
    return hmac.compare_digest(_hmac(secret, body), signature or "")


# ---------------------------------------------------------------- Razorpay API
def _client(k: Keys) -> httpx.Client:
    return httpx.Client(base_url=get_settings().razorpay_api, auth=(k.key_id, k.key_secret), timeout=20)


def create_order(amount: int, receipt: str, notes: dict[str, str]) -> str:
    k = keys()
    if not k:
        raise UserError("Online payments aren't set up yet")
    if get_settings().studio_fake_razorpay:  # tests only
        return f"order_fake{secrets.token_hex(7)}"
    try:
        with _client(k) as c:
            r = c.post(
                "/orders", json={"amount": amount, "currency": CURRENCY, "receipt": receipt, "notes": notes}
            )
    except httpx.HTTPError as e:
        log.warning("razorpay order failed: %s", type(e).__name__)
        raise UserError("Couldn't reach Razorpay. Try again in a minute.") from e
    if r.status_code == 401:
        raise UserError("Razorpay rejected the keys. Check them in Admin → Payments.")
    if r.status_code >= 400:
        detail = (
            (r.json().get("error") or {}).get("description")
            if "json" in r.headers.get("content-type", "")
            else ""
        )
        raise UserError(f"Razorpay couldn't create the order{': ' + detail if detail else ''}")
    return str(r.json()["id"])


def test_keys() -> dict[str, Any]:
    """Owner's "Test" button: a harmless authenticated read."""
    k = keys()
    if not k:
        raise UserError("Add the Key ID and Key secret first")
    if get_settings().studio_fake_razorpay:
        return {"ok": True, "mode": "test" if k.key_id.startswith("rzp_test_") else "live"}
    try:
        with _client(k) as c:
            r = c.get("/orders", params={"count": 1})
    except httpx.HTTPError as e:
        raise UserError("Couldn't reach Razorpay") from e
    if r.status_code == 401:
        raise UserError("Razorpay rejected these keys")
    if r.status_code >= 400:
        raise UserError(f"Razorpay answered {r.status_code}")
    return {"ok": True, "mode": "test" if k.key_id.startswith("rzp_test_") else "live"}


# ---------------------------------------------------------------- catalog & checkout
def catalog() -> dict[str, Any]:
    plans = db.fetch_all(
        "select id, name, price_inr_month, price_inr_year from plans "
        "where public and (price_inr_month > 0 or price_inr_year > 0) order by sort"
    )
    packs = db.fetch_all("select id, name, tokens, price_inr from token_packs where active order by sort")
    k = None
    try:
        k = keys()
    except crypto.CryptoError:
        pass
    return {
        "enabled": k is not None,
        "key_id": k.key_id if k else None,
        "currency": CURRENCY,
        "plans": plans,
        "packs": packs,
    }


def start_checkout(
    member: Any, kind: str, *, plan_id: str | None, period: str | None, pack_id: str | None
) -> dict:
    """Create the Razorpay order and our payment row; returns what Razorpay Checkout needs."""
    k = keys()
    if not k:
        raise UserError("Online payments aren't set up yet. Ask for an upgrade on the Pricing page instead.")
    if member.unlimited:
        raise UserError("Your team account already has everything for free")
    if kind == "plan":
        if period not in PERIOD_DAYS:
            raise UserError("Pick monthly or yearly")
        p = db.fetch_one(
            "select id, name, price_inr_month, price_inr_year, daily_tokens from plans where id = %s and public",
            [plan_id],
        )
        price = (p or {}).get("price_inr_month" if period == "month" else "price_inr_year") or 0
        if not p or price <= 0:
            raise UserError("That plan can't be bought online")
        item = {"plan_id": p["id"], "period": period}
        description = f"{p['name']} plan, 1 {period}"
    elif kind == "tokens":
        pk = db.fetch_one("select * from token_packs where id = %s and active", [pack_id])
        if not pk:
            raise UserError("That token pack isn't available")
        price = pk["price_inr"]
        item = {"pack_id": pk["id"], "tokens": pk["tokens"]}
        description = f"{pk['name']}: {pk['tokens']:,} tokens"
    else:
        raise UserError("Unknown purchase")
    amount = int(price) * 100  # paise
    receipt = f"r_{secrets.token_hex(8)}"
    order_id = create_order(
        amount, receipt, {"user_id": member.user_id, "kind": kind, **{k2: str(v) for k2, v in item.items()}}
    )
    db.execute(
        "insert into payments (user_id, kind, item, description, amount, currency, order_id) values (%s,%s,%s,%s,%s,%s,%s)",
        [member.user_id, kind, db.jsonb(item), description, amount, CURRENCY, order_id],
    )
    return {
        "order_id": order_id,
        "key_id": k.key_id,
        "amount": amount,
        "currency": CURRENCY,
        "description": description,
        "prefill": {"email": member.email, "name": member.display_name or ""},
    }


# ---------------------------------------------------------------- fulfilment
def _extend_plan(c: Any, user_id: str, plan_id: str, period: str) -> datetime:
    m = c.execute(
        "select plan_id, plan_source, plan_expires_at, plan_before_trial from members where user_id = %s for update",
        [user_id],
    ).fetchone()
    now = datetime.now(UTC)
    days = timedelta(days=PERIOD_DAYS[period])
    same_paid = (
        m["plan_id"] == plan_id
        and m["plan_source"] == "paid"
        and m["plan_expires_at"]
        and m["plan_expires_at"] > now
    )
    until = (m["plan_expires_at"] + days) if same_paid else (now + days)
    # what to return to when the paid time runs out: the plan they had before any trial / payment
    base = m["plan_before_trial"] if m["plan_source"] in ("trial", "paid") else m["plan_id"]
    if base == plan_id:
        base = "free"
    c.execute(
        """update members set plan_id = %s, plan_source = 'paid', plan_expires_at = %s,
                  plan_before_trial = %s, renewal_reminded_at = null where user_id = %s""",
        [plan_id, until, base or "free", user_id],
    )
    return until


def fulfill(
    order_id: str, payment_id: str, *, amount: int | None = None, via: str = "checkout"
) -> dict[str, Any]:
    """Apply a paid order once. Returns the payment row (with `already` = True if it was applied before)."""
    plan_changed: str | None = None
    expected = db.fetch_one("select amount from payments where order_id = %s", [order_id])
    if expected and amount is not None and int(amount) != int(expected["amount"]):
        # recorded outside any transaction so the note survives the error below
        db.execute(
            "update payments set status = 'failed', error = %s where order_id = %s and status = 'created'",
            [f"amount mismatch: paid {amount}, expected {expected['amount']}", order_id],
        )
        log.error("payment amount mismatch for order %s", order_id)
        raise UserError("The paid amount doesn't match the order")
    with db.transaction() as c:
        p = c.execute("select * from payments where order_id = %s for update", [order_id]).fetchone()
        if not p:
            raise UserError("Unknown order")
        if p["status"] == "paid" and p["fulfilled_at"]:
            return {**p, "already": True}
        if p["status"] == "refunded":
            raise UserError("This payment was refunded")
        uid = str(p["user_id"])
        item = p["item"]
        result: dict[str, Any] = {}
        if p["kind"] == "plan":
            until = _extend_plan(c, uid, item["plan_id"], item["period"])
            result = {"plan_id": item["plan_id"], "until": until.isoformat()}
            plan_changed = item["plan_id"]
        row = c.execute(
            """update payments set status = 'paid', payment_id = %s, paid_at = coalesce(paid_at, now()),
                      fulfilled_at = now(), error = null where id = %s returning *""",
            [payment_id, p["id"]],
        ).fetchone()
    if p["kind"] == "tokens":
        tokens.purchase(uid, int(item["tokens"]), payment_ref=str(p["id"]))
        result = {"tokens": int(item["tokens"])}
    if plan_changed:
        tokens.on_plan_change(uid)  # the bigger daily allowance applies today
    rupees = p["amount"] / 100
    if p["kind"] == "plan":
        until_txt = datetime.fromisoformat(result["until"]).strftime("%d %b %Y")
        notify(
            uid,
            "Payment received, thank you!",
            f"{p['description']}. Active until {until_txt}.",
            kind="success",
            link="/account",
        )
    else:
        notify(
            uid,
            "Tokens added, thank you!",
            f"{p['description']} are in your balance.",
            kind="success",
            link="/account/tokens",
        )
    notify_admins(f"New payment: ₹{rupees:,.0f}", p["description"], link="/admin/payments")
    db.execute(
        "insert into audit_log (actor_id, action, target_type, target_id, details) values (%s,'payment.paid','payment',%s,%s)",
        [uid, str(p["id"]), db.jsonb({"via": via, "amount": p["amount"], "order_id": order_id, **result})],
    )
    return {**row, "already": False, **result}


def confirm(member: Any, order_id: str, payment_id: str, signature: str) -> dict[str, Any]:
    """The browser's success callback from Razorpay Checkout."""
    k = keys()
    if not k:
        raise UserError("Online payments aren't set up")
    p = db.fetch_one("select user_id from payments where order_id = %s", [order_id])
    if not p or str(p["user_id"]) != member.user_id:
        raise UserError("Unknown order")
    if not payment_signature_ok(order_id, payment_id, signature, k.key_secret):
        db.execute(
            "update payments set error = 'bad signature from browser' where order_id = %s and status = 'created'",
            [order_id],
        )
        raise UserError(
            "We couldn't verify this payment. If money was taken it will be applied automatically, or contact us."
        )
    return fulfill(order_id, payment_id, via="checkout")


def handle_webhook(body: bytes, signature: str, event: dict[str, Any]) -> str:
    """Razorpay webhook (payment.captured / order.paid / payment.failed). Returns what happened."""
    k = keys()
    if not k or not k.webhook_secret:
        raise UserError("Webhook secret not set")
    if not webhook_signature_ok(body, signature, k.webhook_secret):
        raise PermissionError("bad signature")
    name = event.get("event", "")
    pay = ((event.get("payload") or {}).get("payment") or {}).get("entity") or {}
    order_id = pay.get("order_id") or (
        ((event.get("payload") or {}).get("order") or {}).get("entity") or {}
    ).get("id")
    if not order_id or not db.fetch_one("select 1 from payments where order_id = %s", [order_id]):
        return "ignored"
    if name in ("payment.captured", "order.paid"):
        fulfill(order_id, pay.get("id") or "", amount=pay.get("amount"), via="webhook")
        return "fulfilled"
    if name == "payment.failed":
        db.execute(
            "update payments set status = 'failed', error = %s where order_id = %s and status = 'created'",
            [(pay.get("error_description") or "payment failed")[:300], order_id],
        )
        return "failed"
    return "ignored"


# ---------------------------------------------------------------- renewals
def remind_renewals() -> int:
    """Three days before a paid plan ends: one reminder to renew."""
    rows = db.fetch_all(
        """update members set renewal_reminded_at = now()
            where plan_source = 'paid' and renewal_reminded_at is null
              and plan_expires_at between now() and now() + interval '3 days'
        returning user_id, plan_id, plan_expires_at"""
    )
    for r in rows:
        notify(
            str(r["user_id"]),
            f"Your {r['plan_id'].title()} plan ends on {r['plan_expires_at']:%d %b}",
            "Renew on the Pricing page to keep your features and daily tokens.",
            link="/pricing",
        )
    return len(rows)
