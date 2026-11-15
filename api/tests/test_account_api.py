"""User panel: dashboard, checklist, plan upgrade requests, public share links."""

from __future__ import annotations

import pytest
from studio_shared import db, storage

pytestmark = pytest.mark.integration


def test_dashboard_and_checklist(client, make_member):
    uid, _, hdr = make_member(plan="pro")
    d = client.get("/me/dashboard", headers=hdr).json()
    assert d["wallet"]["daily_allowance"] == 5000 and d["recent"] == [] and d["running_jobs"] == 0
    ids = {i["id"]: i["done"] for i in d["checklist"]}
    assert ids == {
        "first_clip": False,
        "download": False,
        "first_story": False,
        "brand": False,
        "share": False,
    }
    db.execute("insert into projects (type, title, created_by) values ('clip','Mine',%s)", [uid])
    d = client.get("/me/dashboard", headers=hdr).json()
    assert d["recent"][0]["title"] == "Mine" and {i["id"]: i["done"] for i in d["checklist"]}["first_clip"]
    _, _, free = make_member(plan="free")
    assert "brand" not in {i["id"] for i in client.get("/me/dashboard", headers=free).json()["checklist"]}


def test_upgrade_request_flow(client, make_member):
    uid, _, user = make_member(plan="free")
    aid, _, admin = make_member("admin")
    assert (
        client.post("/billing/upgrade-request", headers=user, json={"plan_id": "team"}).status_code == 404
    )  # hidden
    assert client.post("/billing/upgrade-request", headers=user, json={"plan_id": "free"}).status_code == 400
    r = client.post(
        "/billing/upgrade-request", headers=user, json={"plan_id": "pro", "note": "for my channel"}
    )
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    assert (
        client.post("/billing/upgrade-request", headers=user, json={"plan_id": "business"}).status_code == 409
    )
    note = db.fetch_one(
        "select title, link from notifications where user_id = %s order by created_at desc limit 1", [aid]
    )
    assert note["title"] == "Upgrade request: Pro" and note["link"] == "/admin/requests"
    assert client.get("/admin/upgrade-requests", headers=user).status_code == 403
    pending = client.get("/admin/upgrade-requests", headers=admin).json()
    assert any(p["id"] == rid and p["email"] for p in pending)
    r = client.post(
        f"/admin/upgrade-requests/{rid}", headers=admin, json={"approve": True, "reply": "Welcome!"}
    )
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert db.fetch_one("select plan_id from members where user_id = %s", [uid])["plan_id"] == "pro"
    assert client.get("/me", headers=user).json()["plan"]["id"] == "pro"
    assert client.get("/tokens", headers=user).json()["daily_balance"] == 5000  # upgrade applies today
    assert (
        client.post(f"/admin/upgrade-requests/{rid}", headers=admin, json={"approve": False}).status_code
        == 404
    )
    got = db.fetch_one(
        "select title, kind from notifications where user_id = %s order by created_at desc limit 1", [uid]
    )
    assert got["title"] == "You're on Pro now" and got["kind"] == "success"
    # cancel a pending request
    client.post("/billing/upgrade-request", headers=user, json={"plan_id": "business"})
    client.delete("/billing/upgrade-request", headers=user)
    assert client.get("/billing/upgrade-request", headers=user).json()[0]["status"] == "canceled"


def _ready_clip(uid: str) -> tuple[str, str]:
    pid = db.fetch_one(
        "insert into projects (type, title, created_by) values ('clip','P',%s) returning id", [uid]
    )["id"]
    key = f"projects/{pid}/clips/x/v.mp4"
    storage.put_bytes(key, b"fake mp4", "video/mp4")
    cid = db.fetch_one(
        "insert into clips (project_id, idx, start_s, end_s, title, status, video_key, filename, duration_s) "
        "values (%s,1,0,10,'Shared clip','ready',%s,'01-shared.mp4',10) returning id",
        [pid, key],
    )["id"]
    return str(pid), str(cid)


def test_share_links(client, make_member):
    uid, _, free = make_member(plan="free")
    _, cid = _ready_clip(uid)
    assert client.post(f"/clips/{cid}/share", headers=free, json={}).status_code == 403
    db.execute("update members set plan_id = 'pro' where user_id = %s", [uid])
    r = client.post(f"/clips/{cid}/share", headers=free, json={"days": 7})
    assert r.status_code == 201, r.text
    token = r.json()["token"]
    pub = client.get(f"/public/share/{token}")  # no sign-in
    assert (
        pub.status_code == 200
        and pub.json()["title"] == "Shared clip"
        and pub.json()["video_url"].startswith("http")
    )
    client.get(f"/public/share/{token}")
    assert client.get("/share-links", headers=free).json()[0]["views"] == 2
    _, _, other = make_member(plan="pro")
    assert client.delete(f"/share-links/{token}", headers=other).status_code == 404  # not theirs
    assert client.delete(f"/share-links/{token}", headers=free).status_code == 200
    assert client.get(f"/public/share/{token}").status_code == 404
    r = client.post(f"/clips/{cid}/share", headers=free, json={"days": 1})
    db.execute(
        "update share_links set expires_at = now() - interval '1 minute' where token = %s",
        [r.json()["token"]],
    )
    assert client.get(f"/public/share/{r.json()['token']}").status_code == 404
    assert client.get("/public/share/short").status_code == 404
