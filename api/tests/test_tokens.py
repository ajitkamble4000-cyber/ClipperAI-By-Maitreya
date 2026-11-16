"""Token economy: daily allowance + refill, charges, refunds, grants, unlimited team, plan limits."""

from __future__ import annotations

import pytest
from studio_shared import db, tokens

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def no_queue(monkeypatch):
    sent = []
    monkeypatch.setattr("app.plans.enqueue", lambda job: sent.append(job))
    return sent


def clip(client, hdr, **kw):
    body = {"url": "https://www.youtube.com/watch?v=abc", "num_clips": 4, **kw}
    return client.post("/clipper/projects", json=body, headers=hdr)


def finish_failed(job_id):
    from worker.hooks import on_job_finished  # the same hook the worker runs

    job = db.fetch_one("select * from jobs where id = %s", [job_id])
    db.execute("update jobs set status = 'failed' where id = %s", [job_id])
    on_job_finished(job, "failed", {"error": "boom"})


@pytest.fixture(scope="module", autouse=True)
def worker_path():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "worker"))


def test_new_free_user_has_1000_daily_tokens(client, make_member):
    _, _, hdr = make_member("user")
    w = client.get("/tokens", headers=hdr).json()
    assert w["daily_balance"] == 1000 and w["daily_allowance"] == 1000 and w["bonus_balance"] == 0
    assert w["resets_at"].endswith("00:00:00+00:00")
    assert client.get("/me", headers=hdr).json()["wallet"]["total"] == 1000


def test_charge_quote_refund_retry(client, make_member, no_queue):
    uid, _, hdr = make_member("user")
    q = client.get("/tokens/quote", params={"kind": "clip", "num_clips": 4}, headers=hdr).json()
    assert q["tokens"] == 50 + 4 * 40 and q["enough"]
    r = clip(client, hdr)
    assert r.status_code == 201 and r.json()["tokens"] == 210
    assert tokens.get_wallet(uid).total == 790
    jid = r.json()["job_id"]
    finish_failed(jid)
    assert tokens.get_wallet(uid).total == 1000
    finish_failed(jid)  # idempotent
    assert tokens.get_wallet(uid).total == 1000
    # Retry charges again; a second failure refunds again.
    db.execute("update jobs set status = 'failed' where id = %s", [jid])
    assert client.post(f"/jobs/{jid}/retry", headers=hdr).status_code == 200
    assert tokens.get_wallet(uid).total == 790
    finish_failed(jid)
    assert tokens.get_wallet(uid).total == 1000
    reasons = [x["reason"] for x in client.get("/tokens/ledger", headers=hdr).json()]
    assert reasons.count("charge") == 2 and reasons.count("refund") == 2


def test_insufficient_tokens(client, make_member):
    uid, _, hdr = make_member("user")
    db.execute(
        "insert into wallets (user_id, daily_balance, daily_reset_at) values (%s, 100, now() + interval '1 day') "
        "on conflict (user_id) do update set daily_balance = 100, daily_reset_at = now() + interval '1 day'",
        [uid],
    )
    before = db.fetch_one("select count(*) as n from projects where created_by = %s", [uid])["n"]
    r = clip(client, hdr)
    assert r.status_code == 402 and "needs 210, you have 100" in r.json()["detail"]
    assert db.fetch_one("select count(*) as n from projects where created_by = %s", [uid])["n"] == before


def test_cancel_refunds(client, make_member):
    uid, _, hdr = make_member("user")
    jid = clip(client, hdr).json()["job_id"]
    r = client.post(f"/jobs/{jid}/cancel", headers=hdr).json()
    assert r == {"canceled": True, "refunded": 210}
    assert tokens.get_wallet(uid).total == 1000


def test_daily_refill_and_bonus_spend_order(client, make_member):
    uid, _, hdr = make_member("user")
    _, _, admin = make_member("admin")
    tokens.get_wallet(uid)
    db.execute(
        "update wallets set daily_balance = 30, daily_reset_at = now() - interval '1 minute' where user_id = %s",
        [uid],
    )
    assert tokens.get_wallet(uid).daily_balance == 1000  # refilled
    assert (
        client.post(
            f"/admin/users/{uid}/tokens", json={"amount": 500, "note": "welcome"}, headers=hdr
        ).status_code
        == 403
    )
    w = client.post(
        f"/admin/users/{uid}/tokens", json={"amount": 500, "note": "welcome"}, headers=admin
    ).json()
    assert w["bonus_balance"] == 500 and w["total"] == 1500
    tokens.charge(uid, 1200, "test")
    w = tokens.get_wallet(uid)
    assert (w.daily_balance, w.bonus_balance) == (0, 300)  # daily first, then bonus
    w = client.post(f"/admin/users/{uid}/tokens", json={"amount": -10_000}, headers=admin).json()
    assert w["bonus_balance"] == 0  # revokes floor at zero
    notes = client.get("/notifications", headers=hdr).json()
    assert (
        notes["unread"] >= 1
        and "500 bonus tokens" in notes["items"][-1]["title"]
        or any("500 bonus tokens" in n["title"] for n in notes["items"])
    )
    # Daily override applies immediately.
    w = client.put(f"/admin/users/{uid}/daily-tokens", json={"daily_tokens": 3000}, headers=admin).json()
    assert w["daily_balance"] == 3000 and w["daily_allowance"] == 3000


def test_team_is_unlimited(client, make_member):
    uid, _, hdr = make_member("user", team="creator", plan="team")
    r = clip(client, hdr, num_clips=20, visual_analysis=True)
    assert r.status_code == 201 and r.json()["tokens"] == 0
    assert tokens.get_wallet(uid).unlimited
    row = db.fetch_one(
        "select reason, delta, meta from token_ledger where user_id = %s order by id desc limit 1", [uid]
    )
    assert row["reason"] == "waived" and row["delta"] == 0 and row["meta"]["tokens"] > 0


def test_plan_limits_and_features(client, make_member):
    _, _, free = make_member("user")
    assert clip(client, free, num_clips=10).status_code == 403
    r = clip(client, free, visual_analysis=True)
    assert r.status_code == 403 and "Pro" in r.json()["detail"]
    big = client.post(
        "/uploads", json={"filename": "a.mp4", "size": 2 * 1024**3, "content_type": "video/mp4"}, headers=free
    )
    assert big.status_code == 403
    _, _, pro = make_member("user", plan="pro")
    assert clip(client, pro, num_clips=10, visual_analysis=True).status_code == 201
    # Concurrency: Free runs one job at a time.
    assert clip(client, free).status_code == 201
    r = clip(client, free)
    assert r.status_code == 429 and "1 job at a time" in r.json()["detail"]
    job = db.fetch_one(
        "select params from jobs where created_by = (select user_id from members where user_id = "
        "(select created_by from jobs order by created_at desc limit 1)) order by created_at desc limit 1"
    )
    assert "watermark" in job["params"]


def test_prices_and_plans_admin(client, make_member, monkeypatch):
    import uuid

    from authutil import create_auth_user, sign_in
    from studio_shared.config import get_settings

    _, _, admin = make_member("admin")
    _, _, user = make_member("user")
    try:
        assert (
            client.put("/admin/token-prices/clip_ai_per_clip", json={"tokens": 55}, headers=admin).status_code
            == 200
        )
        assert (
            client.get("/tokens/quote", params={"kind": "clip", "num_clips": 2}, headers=user).json()[
                "tokens"
            ]
            == 50 + 110
        )
    finally:
        client.put("/admin/token-prices/clip_ai_per_clip", json={"tokens": 40}, headers=admin)
    assert client.put("/admin/plans/free", json={"daily_tokens": 2000}, headers=admin).status_code == 403
    email = f"own-{uuid.uuid4().hex[:6]}@example.com"
    monkeypatch.setattr(get_settings(), "owner_email", email)
    db.execute("update members set role = 'admin' where role = 'owner'")
    oid = create_auth_user(email)
    owner = {"Authorization": f"Bearer {sign_in(email)}"}
    before = db.fetch_one("select price_usd_month, limits, features from plans where id = 'pro'")
    try:
        r = client.put(
            "/admin/plans/pro",
            json={"price_usd_month": 24, "limits": {"max_clips_per_job": 16}},
            headers=owner,
        )
        assert r.status_code == 200 and r.json()["price_usd_month"] == 24
        assert r.json()["limits"]["concurrent_jobs"] == 3  # merged, other limits kept
        assert client.put("/admin/plans/pro", json={"limits": {"bogus": 1}}, headers=owner).status_code == 400
        r = client.put("/admin/plans/pro", json={"features": ["brand_kit"]}, headers=owner)
        assert {"clipper", "captions", "story", "brand_kit"} <= set(
            r.json()["features"]
        )  # base never removed
        b = client.post(
            "/admin/tokens/broadcast",
            json={"amount": 5, "plan_id": "business", "note": "promo"},
            headers=owner,
        )
        assert b.status_code == 200
    finally:
        db.execute(  # put the plan back exactly as it was (features added by later migrations included)
            "update plans set price_usd_month = %s, limits = %s, features = %s where id = 'pro'",
            [before["price_usd_month"], db.jsonb(before["limits"]), before["features"]],
        )
        db.execute("update members set role = 'user' where user_id = %s", [oid])
