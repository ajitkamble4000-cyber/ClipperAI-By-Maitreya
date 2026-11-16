"""Growth: promo codes (tokens, trials + expiry), referrals, site controls (sign-ups closed, paused jobs)."""

from __future__ import annotations

import uuid

import httpx
import pytest
from studio_shared import db, growth, tokens
from studio_shared.config import get_settings

pytestmark = pytest.mark.integration


@pytest.fixture
def owner(client, monkeypatch):
    from conftest import create_auth_user, sign_in

    email = f"own-{uuid.uuid4().hex[:6]}@example.com"
    monkeypatch.setattr(get_settings(), "owner_email", email)
    db.execute("update members set role = 'admin' where role = 'owner'")
    uid = create_auth_user(email)
    yield uid, {"Authorization": f"Bearer {sign_in(email)}"}
    db.execute("update members set role = 'user' where user_id = %s", [uid])


@pytest.fixture
def site_reset():
    yield
    db.execute(
        "update settings set signups_open = true, jobs_paused = false, maintenance_message = '', "
        "referral_reward = 500, referral_monthly_cap = 20 where id = 1"
    )


def _code() -> str:
    return f"T{uuid.uuid4().hex[:8].upper()}"


def test_token_promo(client, make_member, owner):
    _, ohdr = owner
    code = _code()
    _, _, admin = make_member("admin")
    assert (
        client.post(
            "/admin/promos", headers=admin, json={"code": code, "kind": "tokens", "tokens": 300}
        ).status_code
        == 403
    )
    r = client.post(
        "/admin/promos",
        headers=ohdr,
        json={"code": code.lower(), "kind": "tokens", "tokens": 300, "max_redemptions": 2},
    )
    assert r.status_code == 201 and r.json()["code"] == code
    uid, _, user = make_member()
    before = tokens.get_wallet(uid).total
    r = client.post("/promo/redeem", headers=user, json={"code": f" {code.lower()} "})
    assert r.status_code == 200 and r.json()["tokens"] == 300
    assert tokens.get_wallet(uid).total == before + 300
    assert (
        client.post("/promo/redeem", headers=user, json={"code": code}).json()["detail"]
        == "You've already used this code"
    )
    _, _, u2 = make_member()
    _, _, u3 = make_member()
    assert client.post("/promo/redeem", headers=u2, json={"code": code}).status_code == 200
    assert (
        client.post("/promo/redeem", headers=u3, json={"code": code}).json()["detail"]
        == "That code has been used up"
    )
    assert client.post("/promo/redeem", headers=u3, json={"code": "NOPE-NOPE"}).status_code == 400
    client.patch(f"/admin/promos/{code}", headers=ohdr, json={"active": False})
    assert any(
        p["code"] == code and not p["active"] and p["redemptions"] == 2
        for p in client.get("/admin/promos", headers=admin).json()
    )


def test_trial_promo_and_expiry(client, make_member, owner):
    _, ohdr = owner
    code = _code()
    assert (
        client.post(
            "/admin/promos",
            headers=ohdr,
            json={"code": code, "kind": "trial", "plan_id": "pro", "trial_days": 7},
        ).status_code
        == 201
    )
    uid, _, user = make_member(plan="free")
    r = client.post("/promo/redeem", headers=user, json={"code": code})
    assert (
        r.status_code == 200
        and r.json()["kind"] == "trial"
        and "Pro unlocked for 7 days" in r.json()["message"]
    )
    me = client.get("/me", headers=user).json()
    assert me["plan"]["id"] == "pro" and me["trial_ends_at"] and me["wallet"]["daily_balance"] == 5000
    _, _, biz = make_member(plan="business")
    assert (
        "already on this plan"
        in client.post("/promo/redeem", headers=biz, json={"code": code}).json()["detail"]
    )
    # expire it: next request puts them back on Free and tells them
    db.execute("update members set plan_expires_at = now() - interval '1 minute' where user_id = %s", [uid])
    me = client.get("/me", headers=user).json()
    assert me["plan"]["id"] == "free" and me["trial_ends_at"] is None
    assert (
        db.fetch_one(
            "select title from notifications where user_id = %s order by created_at desc limit 1", [uid]
        )["title"]
        == "Your trial has ended"
    )
    assert growth.expire_trials() >= 0


def test_referrals(client, make_member, site_reset):
    referrer, _, rhdr = make_member()
    info = client.get("/referrals", headers=rhdr).json()
    assert info["path"] == f"/signup?ref={info['code']}" and info["joined"] == 0 and info["reward"] == 500
    assert client.get("/referrals", headers=rhdr).json()["code"] == info["code"]  # stable
    # a friend signs up through the link (the sign-up trigger links them)
    email = f"friend-{uuid.uuid4().hex[:6]}@example.com"
    s = get_settings()
    hdr = {
        "apikey": s.supabase_service_role_key.get_secret_value(),
        "Authorization": f"Bearer {s.supabase_service_role_key.get_secret_value()}",
    }
    r = httpx.post(
        f"{s.supabase_url}/auth/v1/admin/users",
        headers=hdr,
        json={
            "email": email,
            "password": "pw-123456789",
            "email_confirm": True,
            "user_metadata": {"ref": info["code"]},
        },
    )
    friend = r.json()["id"]
    try:
        assert (
            db.fetch_one("select status from referrals where referred_id = %s", [friend])["status"]
            == "pending"
        )
        b_ref, b_friend = tokens.get_wallet(referrer).total, tokens.get_wallet(friend).total
        assert growth.maybe_reward_referral(friend) == 500
        assert growth.maybe_reward_referral(friend) == 0  # only once
        assert (
            tokens.get_wallet(referrer).total == b_ref + 500
            and tokens.get_wallet(friend).total == b_friend + 500
        )
        info = client.get("/referrals", headers=rhdr).json()
        assert info["joined"] == 1 and info["rewarded"] == 1 and info["tokens_earned"] == 500
    finally:
        httpx.delete(f"{s.supabase_url}/auth/v1/admin/users/{friend}", headers=hdr)


def test_referral_monthly_cap(make_member, site_reset):
    db.execute("update settings set referral_monthly_cap = 0 where id = 1")
    referrer, _, _ = make_member()
    friend, _, _ = make_member()
    db.execute("insert into referrals (referred_id, referrer_id) values (%s, %s)", [friend, referrer])
    b = tokens.get_wallet(referrer).total
    assert growth.maybe_reward_referral(friend) == 500  # the friend still gets the welcome bonus
    assert tokens.get_wallet(referrer).total == b  # the referrer is capped this month
    assert db.fetch_one("select status from referrals where referred_id = %s", [friend])["status"] == "capped"


def test_site_controls(client, make_member, owner, site_reset, monkeypatch):
    _, ohdr = owner
    monkeypatch.setattr("app.plans.enqueue", lambda job: None)
    r = client.put(
        "/admin/site",
        headers=ohdr,
        json={"jobs_paused": True, "maintenance_message": "Upgrading servers, back at 6pm"},
    )
    assert r.status_code == 200 and r.json()["jobs_paused"] is True
    pub = client.get("/public/site").json()  # no sign-in
    assert pub["maintenance_message"] == "Upgrading servers, back at 6pm" and pub["jobs_paused"]
    _, _, user = make_member()
    r = client.post("/clipper/projects", headers=user, json={"url": "https://youtu.be/x", "mode": "captions"})
    assert r.status_code == 503 and "Upgrading servers" in r.json()["detail"]
    _, _, admin = make_member("admin")
    assert client.put("/admin/site", headers=admin, json={"jobs_paused": False}).status_code == 403
    # sign-ups closed: the database refuses new accounts (invites still work)
    client.put("/admin/site", headers=ohdr, json={"signups_open": False, "jobs_paused": False})
    s = get_settings()
    hdr = {
        "apikey": s.supabase_service_role_key.get_secret_value(),
        "Authorization": f"Bearer {s.supabase_service_role_key.get_secret_value()}",
    }
    r = httpx.post(
        f"{s.supabase_url}/auth/v1/admin/users",
        headers=hdr,
        json={
            "email": f"closed-{uuid.uuid4().hex[:6]}@example.com",
            "password": "pw-123456789",
            "email_confirm": True,
        },
    )
    assert r.status_code >= 400
    assert client.get("/public/site").json()["signups_open"] is False
