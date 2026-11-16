"""Insights: personal stats, admin refund of a finished job, users CSV export."""

from __future__ import annotations

import csv
import io

import pytest
from studio_shared import db, tokens

pytestmark = pytest.mark.integration


def _job(uid: str, pid: str, kind: str, state: str = "succeeded") -> str:
    return str(
        db.fetch_one(
            "insert into jobs (project_id, kind, status, created_by, finished_at) "
            "values (%s,%s,%s,%s, case when %s in ('succeeded','failed') then now() end) returning id",
            [pid, kind, state, uid, state],
        )["id"]
    )


def _project(uid: str, kind: str = "clip", title: str = "Stats project") -> str:
    return str(
        db.fetch_one(
            "insert into projects (type, title, created_by) values (%s,%s,%s) returning id",
            [kind, title, uid],
        )["id"]
    )


def test_my_stats(client, make_member):
    uid, _, hdr = make_member()
    other, _, _ = make_member()
    pid = _project(uid)
    db.execute(
        "insert into sources (project_id, kind, url, duration_s) values (%s,'url','https://x.test/v',600)",
        [pid],
    )
    for i, score in enumerate((80, 60), 1):
        db.execute(
            "insert into clips (project_id, idx, start_s, end_s, title, status, virality_score, duration_s) "
            "values (%s,%s,0,30,%s,'ready',%s,30)",
            [pid, i, f"Clip {i}", score],
        )
    db.execute(
        "insert into clips (project_id, idx, start_s, end_s, title, status, virality_score) "
        "values (%s,3,0,30,'Broken','failed',99)",
        [pid],
    )
    spid = _project(uid, "story", "A story")
    db.execute("insert into stories (project_id, idea, render_key) values (%s,'i','r/final.mp4')", [spid])

    clip_job = _job(uid, pid, "clip")
    tokens.charge(uid, 100, "clip", job_id=clip_job)
    tokens.partial_refund(clip_job, 20, "fewer clips than asked")
    thumb_job = _job(uid, pid, "thumbnail")
    tokens.charge(uid, 5, "thumbnail", job_id=thumb_job)
    failed = _job(uid, pid, "repurpose", "failed")
    tokens.charge(uid, 25, "repurpose", job_id=failed)
    tokens.refund_job(failed, "job failed")
    # someone else's activity never shows up
    opid = _project(other)
    tokens.charge(other, 40, "clip", job_id=_job(other, opid, "clip"))

    r = client.get("/me/stats", params={"days": 7}, headers=hdr)
    assert r.status_code == 200, r.text
    s = r.json()
    t = s["totals"]
    assert (t["videos_in"], t["minutes_in"], t["clips"], t["minutes_out"]) == (1, 10.0, 2, 1.0)
    assert (t["avg_score"], t["stories"], t["jobs_ok"], t["jobs_failed"]) == (70, 1, 2, 1)
    assert t["tokens"] == 85
    assert s["by_feature"] == [{"feature": "Clips", "tokens": 80}, {"feature": "Thumbnails", "tokens": 5}]
    assert len(s["daily"]) == 7 and s["daily"][-1]["tokens"] == 85 and s["daily"][-1]["clips"] == 2
    assert [c["title"] for c in s["best_clips"]] == ["Clip 1", "Clip 2"]
    assert s["streak"] == 1
    assert client.get("/me/stats", params={"days": 365}, headers=hdr).status_code == 422

    empty = client.get("/me/stats", headers=make_member()[2]).json()
    assert empty["totals"]["tokens"] == 0 and empty["totals"]["avg_score"] is None and empty["streak"] == 0
    assert len(empty["daily"]) == 30


def test_admin_refund_finished_job(client, make_member):
    uid, _, hdr = make_member()
    _, _, admin = make_member("admin")
    pid = _project(uid)
    job = _job(uid, pid, "clip")
    before = tokens.get_wallet(uid)
    tokens.charge(uid, 60, "clip", job_id=job)
    assert tokens.get_wallet(uid).daily_balance == before.daily_balance - 60

    assert client.post(f"/admin/jobs/{job}/refund", headers=hdr, json={}).status_code == 403
    r = client.post(f"/admin/jobs/{job}/refund", headers=admin, json={"reason": "captions were off"})
    assert r.status_code == 200 and r.json() == {"refunded": 60}
    assert tokens.get_wallet(uid).daily_balance == before.daily_balance
    note = db.fetch_one(
        "select title, body, link from notifications where user_id = %s order by created_at desc limit 1",
        [uid],
    )
    assert note["title"] == "60 tokens refunded" and "Captions were off" in note["body"]
    assert db.fetch_one("select 1 from audit_log where action = 'job.refund' and target_id = %s", [job])

    again = client.post(f"/admin/jobs/{job}/refund", headers=admin, json={})
    assert again.status_code == 409 and "Nothing left" in again.json()["detail"]
    running = _job(uid, pid, "clip", "running")
    assert (
        "Cancel it instead"
        in client.post(f"/admin/jobs/{running}/refund", headers=admin, json={}).json()["detail"]
    )
    assert client.post("/admin/jobs/not-a-uuid/refund", headers=admin, json={}).status_code == 404


def test_users_csv_export(client, make_member):
    uid, email, hdr = make_member(plan="pro")
    _, _, admin = make_member("admin")
    db.execute("update members set display_name = '=HYPERLINK(\"http://evil\")' where user_id = %s", [uid])
    _project(uid)

    assert client.get("/admin/users.csv", headers=hdr).status_code == 403
    r = client.get("/admin/users.csv", params={"q": email}, headers=admin)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert r.headers["content-disposition"].startswith('attachment; filename="users-')
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert len(rows) == 1
    row = rows[0]
    assert row["email"] == email and row["plan"] == "pro" and row["projects"] == "1"
    assert row["name"].startswith("'=")  # formula neutralised
    assert db.fetch_one("select 1 from audit_log where action = 'users.export' limit 1")
    pro_only = list(
        csv.DictReader(
            io.StringIO(client.get("/admin/users.csv", params={"plan": "pro"}, headers=admin).text)
        )
    )
    assert pro_only and all(x["plan"] == "pro" for x in pro_only)
