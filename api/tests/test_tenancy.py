"""Privacy between users: through the API (service role) and through Supabase RLS (browser access)."""

from __future__ import annotations

import httpx
import pytest
from authutil import ANON_KEY
from studio_shared import db
from studio_shared.config import get_settings

pytestmark = pytest.mark.integration


def rest(hdr, path, method="GET", **kw):
    h = {"apikey": ANON_KEY, **hdr}
    return httpx.request(method, f"{get_settings().supabase_url}/rest/v1/{path}", headers=h, **kw)


@pytest.fixture
def two_users(make_member):
    a_uid, _, a = make_member("user")
    b_uid, _, b = make_member("user")
    pid = db.fetch_one(
        "insert into projects (type, title, created_by) values ('clip','A private',%s) returning id", [a_uid]
    )["id"]
    cid = db.fetch_one(
        "insert into clips (project_id, idx, start_s, end_s, status) values (%s,1,0,20,'ready') returning id",
        [pid],
    )["id"]
    jid = db.fetch_one(
        "insert into jobs (kind, project_id, created_by, status) values ('clip',%s,%s,'failed') returning id",
        [pid, a_uid],
    )["id"]
    yield {"a": a, "b": b, "a_uid": a_uid, "b_uid": b_uid, "pid": str(pid), "cid": str(cid), "jid": str(jid)}
    db.execute("delete from projects where id = %s", [pid])


def test_api_blocks_other_users(client, two_users):
    t, b = two_users, two_users["b"]
    assert client.get(f"/jobs/{t['jid']}", headers=b).status_code == 404
    assert client.post(f"/jobs/{t['jid']}/retry", headers=b).status_code == 404
    assert client.post(f"/clips/{t['cid']}/rerender", json={"start": 1}, headers=b).status_code == 404
    assert client.post(f"/projects/{t['pid']}/zip", headers=b).status_code == 404
    assert client.delete(f"/projects/{t['pid']}", headers=b).status_code == 404
    assert (
        client.get("/files/sign", params={"key": f"projects/{t['pid']}/x.mp4"}, headers=b).status_code == 403
    )
    # Owner of the project is fine.
    assert client.get(f"/jobs/{t['jid']}", headers=t["a"]).status_code == 200
    assert (
        client.get("/files/sign", params={"key": f"projects/{t['pid']}/x.mp4"}, headers=t["a"]).status_code
        == 200
    )


def test_rls_blocks_other_users(two_users):
    t = two_users
    tok_b = {"Authorization": t["b"]["Authorization"]}
    assert rest(tok_b, f"projects?id=eq.{t['pid']}").json() == []
    assert rest(tok_b, f"clips?id=eq.{t['cid']}").json() == []
    assert rest(tok_b, f"jobs?id=eq.{t['jid']}").json() == []
    r = rest(tok_b, f"clips?id=eq.{t['cid']}", "PATCH", json={"title": "hijack"})
    assert db.fetch_one("select title from clips where id = %s", [t["cid"]])["title"] != "hijack"
    assert r.status_code in (200, 204, 401, 403)
    # B only sees their own profile.
    emails = [m["email"] for m in rest(tok_b, "members?select=email").json()]
    assert len(emails) == 1
    # A sees their own project.
    assert len(rest({"Authorization": t["a"]["Authorization"]}, f"projects?id=eq.{t['pid']}").json()) == 1


def test_team_shares_library_and_admin_sees_all(client, make_member):
    s1_uid, _, s1 = make_member("user", team="staff", plan="team")
    _, _, s2 = make_member("user", team="creator", plan="team")
    _, _, outsider = make_member("user")
    _, _, admin = make_member("admin")
    pid = db.fetch_one(
        "insert into projects (type, title, created_by) values ('story','Team story',%s) returning id",
        [s1_uid],
    )["id"]
    try:
        for hdr, visible in ((s2, 1), (outsider, 0), (admin, 1)):
            rows = rest({"Authorization": hdr["Authorization"]}, f"projects?id=eq.{pid}").json()
            assert len(rows) == visible
        assert client.post(f"/projects/{pid}/zip", headers=outsider).status_code == 404
    finally:
        db.execute("delete from projects where id = %s", [pid])


def test_settings_reserved_for_owner(client, make_member):
    _, _, admin = make_member("admin")
    assert (
        client.put(
            "/settings/gemini-key", json={"key": "AIzaSy-something-long-enough-1234"}, headers=admin
        ).status_code
        == 403
    )
    assert client.get("/settings", headers=admin).status_code == 200  # admins can view (masked)
