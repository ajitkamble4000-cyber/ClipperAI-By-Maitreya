"""Developer API: API keys (auth, limits, session-only actions) and signed webhooks."""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from studio_shared import db, webhooks
from studio_shared.config import get_settings

pytestmark = pytest.mark.integration


@pytest.fixture
def receiver():
    """A local HTTP endpoint that records what it receives. `status` controls the reply."""
    got: list[dict] = []
    state = {"status": 200}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            body = self.rfile.read(int(self.headers["Content-Length"]))
            got.append({"headers": dict(self.headers), "body": body})
            self.send_response(state["status"])
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_port}/hook", got, state
    srv.shutdown()


@pytest.fixture
def allow_private(monkeypatch):
    monkeypatch.setattr(get_settings(), "webhook_allow_private", True)


def test_api_keys(client, make_member, monkeypatch):
    monkeypatch.setattr("app.plans.enqueue", lambda job: None)
    _, _, free = make_member(plan="free")
    assert client.post("/api-keys", headers=free, json={"name": "x"}).status_code == 403
    uid, _, biz = make_member(plan="business")
    r = client.post("/api-keys", headers=biz, json={"name": "Zapier"})
    assert r.status_code == 201
    key, kid = r.json()["key"], r.json()["id"]
    assert key.startswith("ss_live_") and r.json()["prefix"] in key
    listed = client.get("/api-keys", headers=biz).json()
    assert listed[0]["name"] == "Zapier" and "key" not in listed[0] and "key_hash" not in listed[0]
    k = {"X-API-Key": key}
    assert client.get("/me", headers=k).json()["user_id"] == uid
    r = client.post("/clipper/projects", headers=k, json={"url": "https://youtu.be/abc", "mode": "captions"})
    assert r.status_code == 201  # automations can start jobs
    assert client.get("/api-keys", headers=k).status_code == 403  # keys can't manage keys
    assert client.delete("/me", headers=k).status_code == 403  # or delete the account
    assert client.get("/me", headers={"X-API-Key": "ss_live_nope"}).status_code == 401
    db.execute("update members set plan_id = 'pro' where user_id = %s", [uid])  # downgraded: API stops
    assert "Business" in client.get("/me", headers=k).json()["detail"]
    db.execute("update members set plan_id = 'business' where user_id = %s", [uid])
    assert client.delete(f"/api-keys/{kid}", headers=biz).status_code == 200
    assert client.get("/me", headers=k).status_code == 401
    # admins' keys can't reach admin endpoints
    aid, _, admin = make_member("admin")
    akey = client.post("/api-keys", headers=admin, json={"name": "a"}).json()["key"]
    assert client.get("/admin/overview", headers={"X-API-Key": akey}).status_code == 403


def test_webhook_url_rules(client, make_member):
    _, _, biz = make_member(plan="business")
    for url in ("http://example.com/x", "https://127.0.0.1/x", "https://localhost/hook", "ftp://x.com"):
        assert client.post("/webhooks", headers=biz, json={"url": url}).status_code == 400, url


def test_webhook_signed_delivery(client, make_member, receiver, allow_private):
    url, got, state = receiver
    _, _, biz = make_member(plan="business")
    r = client.post("/webhooks", headers=biz, json={"url": url, "events": ["job.succeeded"]})
    assert r.status_code == 201
    hook, secret = r.json(), r.json()["secret"]
    res = client.post(f"/webhooks/{hook['id']}/test", headers=biz).json()
    assert res == {"ok": True, "status": 200, "error": None}
    body = got[-1]["body"]
    sig = got[-1]["headers"]["X-Studio-Signature"]
    assert sig == "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert json.loads(body)["event"] == "ping" and got[-1]["headers"]["X-Studio-Event"] == "ping"
    state["status"] = 500
    res = client.post(f"/webhooks/{hook['id']}/test", headers=biz).json()
    assert res["ok"] is False and res["status"] == 500
    listed = client.get("/webhooks", headers=biz).json()[0]
    assert listed["failures"] == 1 and listed["recent"][0]["status_code"] == 500 and "secret" not in listed
    assert (
        client.patch(f"/webhooks/{hook['id']}", headers=biz, json={"active": False}).json()["active"] is False
    )
    assert client.post(f"/webhooks/{hook['id']}/test", headers=biz).json()["error"] == "webhook is off"
    _, _, other = make_member(plan="business")
    assert client.delete(f"/webhooks/{hook['id']}", headers=other).status_code == 404


def test_job_payload_and_targets(make_member, allow_private, receiver):
    url, got, _ = receiver
    uid, _, _ = make_member(plan="business")
    pid = str(
        db.fetch_one(
            "insert into projects (type, title, created_by) values ('clip','Hooked',%s) returning id", [uid]
        )["id"]
    )
    db.execute(
        "insert into clips (project_id, idx, start_s, end_s, title, status, video_key, filename, duration_s) "
        "values (%s,1,0,9,'C1','ready','projects/x/v.mp4','01-c1.mp4',9)",
        [pid],
    )
    job = db.fetch_one(
        "insert into jobs (kind, status, created_by, project_id, params) values ('clip','succeeded',%s,%s,'{}') returning *",
        [uid, pid],
    )
    from studio_shared import crypto

    hid = db.fetch_one(
        "insert into webhooks (user_id, url, secret_enc) values (%s,%s,%s) returning id",
        [uid, url, crypto.encrypt("s")],
    )["id"]
    assert [str(t["id"]) for t in webhooks.targets(uid, "job.succeeded")] == [str(hid)]
    data = webhooks.job_payload(job, "succeeded")
    assert (
        data["job"]["kind"] == "clip"
        and data["project"]["title"] == "Hooked"
        and data["clips"][0]["video_url"].startswith("http")
    )
    assert webhooks.deliver(str(hid), "job.succeeded", data)["ok"]
    assert json.loads(got[-1]["body"])["data"]["clips"][0]["title"] == "C1"
