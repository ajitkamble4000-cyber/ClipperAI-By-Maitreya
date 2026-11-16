"""Razorpay payments: checkout, signature checks, idempotent fulfilment (browser + webhook), renewals, expiry,
owner key settings and the admin list. Razorpay itself is not called: orders are created in fake mode."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime

import pytest
from studio_shared import db, growth, payments, tokens
from studio_shared.config import get_settings

pytestmark = pytest.mark.integration

KEY_ID = "rzp_test_ABCdef123456"
SECRET = "test_secret_value_123"
WEBHOOK_SECRET = "whsec_test_456"


@pytest.fixture
def razorpay(monkeypatch):
    """Keys saved in settings (like the owner would), fake order creation."""
    monkeypatch.setattr(get_settings(), "studio_fake_razorpay", True)
    payments.save_keys(KEY_ID, SECRET, WEBHOOK_SECRET)
    yield
    payments.save_keys("", "", "")


@pytest.fixture
def owner(client, monkeypatch):
    from conftest import create_auth_user, sign_in

    email = f"own-{uuid.uuid4().hex[:6]}@example.com"
    monkeypatch.setattr(get_settings(), "owner_email", email)
    db.execute("update members set role = 'admin' where role = 'owner'")
    uid = create_auth_user(email)
    yield uid, {"Authorization": f"Bearer {sign_in(email)}"}
    db.execute("update members set role = 'user' where user_id = %s", [uid])


def sign(order_id: str, payment_id: str, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()


def webhook(
    client,
    event: str,
    order_id: str,
    amount: int,
    payment_id: str = "pay_wh123",
    secret: str = WEBHOOK_SECRET,
):
    body = json.dumps(
        {
            "event": event,
            "payload": {"payment": {"entity": {"id": payment_id, "order_id": order_id, "amount": amount}}},
        }
    ).encode()
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        "/billing/razorpay/webhook",
        content=body,
        headers={"x-razorpay-signature": sig, "content-type": "application/json"},
    )


def test_not_set_up_yet(client, make_member):
    _, _, hdr = make_member()
    cat = client.get("/public/billing").json()
    assert cat["enabled"] is False and cat["key_id"] is None
    assert {p["id"] for p in cat["plans"]} >= {"pro", "business"} and len(cat["packs"]) >= 3
    r = client.post(
        "/billing/checkout", headers=hdr, json={"kind": "plan", "plan_id": "pro", "period": "month"}
    )
    assert r.status_code == 400 and "aren't set up" in r.json()["detail"]


def test_buy_plan_confirm_and_renew(client, make_member, razorpay):
    uid, email, hdr = make_member()
    cat = client.get("/public/billing").json()
    assert cat["enabled"] and cat["key_id"] == KEY_ID and SECRET not in json.dumps(cat)
    pro = next(p for p in cat["plans"] if p["id"] == "pro")

    r = client.post(
        "/billing/checkout", headers=hdr, json={"kind": "plan", "plan_id": "pro", "period": "month"}
    )
    assert r.status_code == 201, r.text
    o = r.json()
    assert o["amount"] == pro["price_inr_month"] * 100 and o["currency"] == "INR" and o["key_id"] == KEY_ID
    assert o["prefill"]["email"] == email and o["order_id"].startswith("order_")

    # a forged signature changes nothing
    bad = client.post(
        "/billing/confirm",
        headers=hdr,
        json={
            "razorpay_order_id": o["order_id"],
            "razorpay_payment_id": "pay_1",
            "razorpay_signature": "nope",
        },
    )
    assert bad.status_code == 400 and "couldn't verify" in bad.json()["detail"]
    assert db.fetch_one("select plan_id from members where user_id = %s", [uid])["plan_id"] == "free"

    ok = client.post(
        "/billing/confirm",
        headers=hdr,
        json={
            "razorpay_order_id": o["order_id"],
            "razorpay_payment_id": "pay_1",
            "razorpay_signature": sign(o["order_id"], "pay_1"),
        },
    )
    assert ok.status_code == 200, ok.text
    m = db.fetch_one(
        "select plan_id, plan_source, plan_expires_at, plan_before_trial from members where user_id = %s",
        [uid],
    )
    assert (m["plan_id"], m["plan_source"], m["plan_before_trial"]) == ("pro", "paid", "free")
    days = (m["plan_expires_at"] - datetime.now(UTC)).days
    assert 29 <= days <= 30
    assert tokens.get_wallet(uid).daily_balance == 5000  # Pro allowance applies today
    note = db.fetch_one(
        "select title from notifications where user_id = %s order by created_at desc limit 1", [uid]
    )
    assert note["title"] == "Payment received, thank you!"

    # the same confirmation again (double click / webhook too) doesn't add another month
    again = client.post(
        "/billing/confirm",
        headers=hdr,
        json={
            "razorpay_order_id": o["order_id"],
            "razorpay_payment_id": "pay_1",
            "razorpay_signature": sign(o["order_id"], "pay_1"),
        },
    )
    assert again.status_code == 200
    assert (
        webhook(client, "payment.captured", o["order_id"], o["amount"], "pay_1").json()["result"]
        == "fulfilled"
    )
    assert (
        db.fetch_one("select plan_expires_at from members where user_id = %s", [uid])["plan_expires_at"]
        == m["plan_expires_at"]
    )

    # renewing adds a year on top of the time left
    o2 = client.post(
        "/billing/checkout", headers=hdr, json={"kind": "plan", "plan_id": "pro", "period": "year"}
    ).json()
    assert o2["amount"] == pro["price_inr_year"] * 100
    client.post(
        "/billing/confirm",
        headers=hdr,
        json={
            "razorpay_order_id": o2["order_id"],
            "razorpay_payment_id": "pay_2",
            "razorpay_signature": sign(o2["order_id"], "pay_2"),
        },
    )
    until = db.fetch_one("select plan_expires_at from members where user_id = %s", [uid])["plan_expires_at"]
    assert (until - m["plan_expires_at"]).days == 365

    me = client.get("/billing/me", headers=hdr).json()
    assert me["plan_id"] == "pro" and me["plan_source"] == "paid" and len(me["payments"]) == 2
    assert all(p["status"] == "paid" for p in me["payments"])

    # someone else can't confirm my order
    _, _, other = make_member()
    o3 = client.post("/billing/checkout", headers=hdr, json={"kind": "tokens", "pack_id": "starter"}).json()
    r = client.post(
        "/billing/confirm",
        headers=other,
        json={
            "razorpay_order_id": o3["order_id"],
            "razorpay_payment_id": "pay_3",
            "razorpay_signature": sign(o3["order_id"], "pay_3"),
        },
    )
    assert r.status_code == 400 and r.json()["detail"] == "Unknown order"


def test_token_pack_via_webhook(client, make_member, razorpay):
    uid, _, hdr = make_member()
    before = tokens.get_wallet(uid).bonus_balance
    o = client.post("/billing/checkout", headers=hdr, json={"kind": "tokens", "pack_id": "starter"}).json()
    assert o["amount"] == 199 * 100 and "5,000 tokens" in o["description"]

    assert webhook(client, "payment.captured", o["order_id"], o["amount"], secret="wrong").status_code == 400
    assert tokens.get_wallet(uid).bonus_balance == before

    assert webhook(client, "payment.captured", o["order_id"], o["amount"]).json() == {
        "ok": True,
        "result": "fulfilled",
    }
    assert webhook(client, "order.paid", o["order_id"], o["amount"]).json()["ok"]  # repeated: no second grant
    assert tokens.get_wallet(uid).bonus_balance == before + 5000
    led = db.fetch_one(
        "select reason, delta, bucket from token_ledger where user_id = %s order by id desc limit 1", [uid]
    )
    assert (led["reason"], led["delta"], led["bucket"]) == ("purchase", 5000, "bonus")
    assert (
        db.fetch_one("select status, payment_id from payments where order_id = %s", [o["order_id"]])[
            "payment_id"
        ]
        == "pay_wh123"
    )

    # paying less than the order (tampering) is recorded and not applied
    o2 = client.post("/billing/checkout", headers=hdr, json={"kind": "tokens", "pack_id": "creator"}).json()
    r = webhook(client, "payment.captured", o2["order_id"], 100, "pay_cheap")
    assert r.status_code == 200 and r.json()["ok"] is False
    row = db.fetch_one("select status, error from payments where order_id = %s", [o2["order_id"]])
    assert row["status"] == "failed" and "amount mismatch" in row["error"]
    assert tokens.get_wallet(uid).bonus_balance == before + 5000

    # failures are recorded; unknown orders are ignored
    o3 = client.post("/billing/checkout", headers=hdr, json={"kind": "tokens", "pack_id": "starter"}).json()
    assert webhook(client, "payment.failed", o3["order_id"], o3["amount"]).json()["result"] == "failed"
    assert webhook(client, "payment.captured", "order_unknown", 100).json()["result"] == "ignored"


def test_checkout_rules(client, make_member, razorpay):
    _, _, team = make_member(team="staff")
    r = client.post(
        "/billing/checkout", headers=team, json={"kind": "plan", "plan_id": "pro", "period": "month"}
    )
    assert r.status_code == 400 and "already has everything" in r.json()["detail"]
    _, _, hdr = make_member()
    for body, msg in [
        ({"kind": "plan", "plan_id": "team", "period": "month"}, "can't be bought online"),
        ({"kind": "plan", "plan_id": "free", "period": "month"}, "can't be bought online"),
        ({"kind": "plan", "plan_id": "pro"}, "monthly or yearly"),
        ({"kind": "tokens", "pack_id": "nope"}, "isn't available"),
    ]:
        r = client.post("/billing/checkout", headers=hdr, json=body)
        assert r.status_code == 400 and msg in r.json()["detail"], (body, r.text)


def test_paid_plan_ends_and_reminders(client, make_member, razorpay):
    uid, _, hdr = make_member()
    o = client.post(
        "/billing/checkout", headers=hdr, json={"kind": "plan", "plan_id": "business", "period": "month"}
    ).json()
    client.post(
        "/billing/confirm",
        headers=hdr,
        json={
            "razorpay_order_id": o["order_id"],
            "razorpay_payment_id": "pay_b",
            "razorpay_signature": sign(o["order_id"], "pay_b"),
        },
    )
    # a promo trial can't stack on a paid plan
    db.execute(
        "insert into promo_codes (code, kind, plan_id, trial_days) values ('PAIDTRY', 'trial', 'team', 7) on conflict do nothing"
    )
    r = client.post("/promo/redeem", headers=hdr, json={"code": "PAIDTRY"})
    assert r.status_code == 400

    # three days before the end: one reminder
    db.execute("update members set plan_expires_at = now() + interval '2 days' where user_id = %s", [uid])
    payments.remind_renewals()
    payments.remind_renewals()
    n = db.fetch_one(
        "select count(*) as n from notifications where user_id = %s and title like 'Your Business plan ends on%%'",
        [uid],
    )
    assert n["n"] == 1

    # after the end: back to Free with a "plan has ended" note
    db.execute("update members set plan_expires_at = now() - interval '1 minute' where user_id = %s", [uid])
    assert growth.expire_trial(uid) is True
    m = db.fetch_one("select plan_id, plan_source, plan_expires_at from members where user_id = %s", [uid])
    assert (m["plan_id"], m["plan_source"], m["plan_expires_at"]) == ("free", None, None)
    note = db.fetch_one(
        "select title from notifications where user_id = %s order by created_at desc limit 1", [uid]
    )
    assert note["title"] == "Your Business plan has ended"
    db.execute("delete from promo_codes where code = 'PAIDTRY'")


def test_owner_settings_and_admin_list(client, make_member, owner, monkeypatch):
    monkeypatch.setattr(get_settings(), "studio_fake_razorpay", True)
    _, ohdr = owner
    _, _, admin = make_member("admin")
    try:
        assert (
            client.put("/admin/payments/settings", headers=admin, json={"key_id": KEY_ID}).status_code == 403
        )
        bad = client.put("/admin/payments/settings", headers=ohdr, json={"key_id": "not-a-key"})
        assert bad.status_code == 400 and "rzp_test_" in bad.json()["detail"]
        r = client.put(
            "/admin/payments/settings",
            headers=ohdr,
            json={"key_id": KEY_ID, "key_secret": SECRET, "webhook_secret": WEBHOOK_SECRET},
        )
        assert r.status_code == 200
        s = r.json()
        assert s["enabled"] and s["mode"] == "test" and s["has_secret"] and s["has_webhook_secret"]
        assert s["webhook_url"].endswith("/billing/razorpay/webhook") and SECRET not in json.dumps(s)
        assert (
            db.fetch_one("select razorpay_secret_enc from settings where id = 1")["razorpay_secret_enc"]
            != SECRET
        )
        assert client.get("/admin/payments/settings", headers=admin).json()["key_id"] == KEY_ID
        assert client.post("/admin/payments/test", headers=ohdr).json() == {"ok": True, "mode": "test"}

        # a sale shows up in the admin list and revenue
        uid, _, hdr = make_member()
        o = client.post(
            "/billing/checkout", headers=hdr, json={"kind": "tokens", "pack_id": "starter"}
        ).json()
        webhook(client, "payment.captured", o["order_id"], o["amount"])
        lst = client.get("/admin/payments", headers=admin, params={"q": o["order_id"]}).json()
        assert [p["status"] for p in lst["payments"]] == ["paid"] and lst["summary"]["revenue_30d"] >= 19900

        # prices and packs
        assert (
            client.put("/admin/plans/pro", headers=ohdr, json={"price_inr_month": 999}).json()[
                "price_inr_month"
            ]
            == 999
        )
        client.put("/admin/plans/pro", headers=ohdr, json={"price_inr_month": 1499})
        assert (
            client.put("/admin/token-packs/starter", headers=admin, json={"price_inr": 1}).status_code == 403
        )
        p = client.put(
            "/admin/token-packs/mega",
            headers=ohdr,
            json={"name": "Mega", "tokens": 500000, "price_inr": 9999},
        ).json()
        assert p["id"] == "mega" and p["active"] is True
        assert (
            client.put("/admin/token-packs/mega", headers=ohdr, json={"active": False}).json()["active"]
            is False
        )
        assert "mega" not in {x["id"] for x in client.get("/public/billing").json()["packs"]}
    finally:
        db.execute("delete from token_packs where id = 'mega'")
        payments.save_keys("", "", "")
