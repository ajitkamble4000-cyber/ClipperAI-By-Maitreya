"""Admin panel: overview analytics, jobs monitor (with admin cancel + refund), system health, user deletion."""

from __future__ import annotations

import pytest
from studio_shared import db, storage, tokens

pytestmark = pytest.mark.integration


def test_admin_only(client, make_member):
    _, _, user = make_member("user")
    for path in ("/admin/overview", "/admin/jobs", "/admin/health"):
        assert client.get(path, headers=user).status_code == 403


def test_overview(client, make_member):
    uid, _, user = make_member(plan="pro")
    _, _, admin = make_member("admin")
    job = db.fetch_one(
        "insert into jobs (kind, status, created_by, params) values ('clip','succeeded',%s,'{}') returning id",
        [uid],
    )
    db.execute("update members set daily_tokens_override = 100000 where user_id = %s", [uid])
    tokens.get_wallet(uid)
    db.execute("update wallets set daily_balance = 100000 where user_id = %s", [uid])
    tokens.charge(uid, 99_000, "clip", job_id=str(job["id"]))  # enough to rank in the shared test DB
    o = client.get("/admin/overview", headers=admin).json()
    assert o["users"]["total"] >= 2 and o["users"]["new_7d"] >= 2
    assert any(p["id"] == "pro" and p["users"] >= 1 for p in o["by_plan"]) and o["mrr_usd"] >= 19
    assert o["tokens"]["d1"] >= 99_000 and o["jobs"]["ok_1d"] >= 1
    assert len(o["signups"]) == 30 and len(o["jobs_per_day"]) == 14
    assert o["top_users"][0]["tokens"] >= o["top_users"][-1]["tokens"] and len(o["top_users"]) <= 8
    assert any(t["user_id"] == uid and t["tokens"] >= 99_000 for t in o["top_users"])
    assert "budget" in o["ai"] or "level" in o["ai"]


def test_jobs_monitor_and_cancel_refunds(client, make_member):
    uid, email, _ = make_member(plan="free")
    _, _, admin = make_member("admin")
    pid = db.fetch_one(
        "insert into projects (type, title, created_by) values ('clip','Monitor me',%s) returning id", [uid]
    )["id"]
    job = db.fetch_one(
        "insert into jobs (kind, status, created_by, project_id, params) values ('clip','queued',%s,%s,'{}') returning id",
        [uid, pid],
    )
    jid = str(job["id"])
    before = tokens.get_wallet(uid).total
    tokens.charge(uid, 90, "clip", job_id=jid)
    rows = client.get("/admin/jobs", headers=admin, params={"status": "active", "q": email}).json()
    assert (
        [r["id"] for r in rows] == [jid]
        and rows[0]["project_title"] == "Monitor me"
        and rows[0]["email"] == email
    )
    r = client.post(f"/admin/jobs/{jid}/cancel", headers=admin)
    assert r.status_code == 200 and r.json()["refunded"] == 90
    assert tokens.get_wallet(uid).total == before
    assert client.post(f"/admin/jobs/{jid}/cancel", headers=admin).status_code == 409
    assert client.post("/admin/jobs/not-a-uuid/cancel", headers=admin).status_code == 404
    assert db.fetch_one("select action from audit_log where target_id = %s", [jid])["action"] == "job.cancel"


def test_health(client, make_member):
    _, _, admin = make_member("admin")
    h = client.get("/admin/health", headers=admin).json()
    c = h["checks"]
    assert c["database"]["ok"] and c["redis"]["ok"] and c["storage"]["ok"]
    assert set(c["redis"]["queues"]) == {"media", "ai", "poll"}
    assert "running" in c["workers"] and "configured" in c["ai"]


def test_admin_delete_user_removes_files(client, make_member):
    uid, _, _ = make_member(plan="pro")
    _, _, admin = make_member("admin")
    pid = db.fetch_one(
        "insert into projects (type, title, created_by) values ('clip','Gone',%s) returning id", [uid]
    )["id"]
    storage.put_bytes(f"projects/{pid}/x.mp4", b"x")
    storage.put_bytes(f"brand/{uid}/logo-1.png", b"x")
    assert client.delete(f"/admin/users/{uid}", headers=admin).status_code == 200
    assert not storage.exists(f"projects/{pid}/x.mp4") and not storage.exists(f"brand/{uid}/logo-1.png")
    assert db.fetch_one("select 1 from members where user_id = %s", [uid]) is None
