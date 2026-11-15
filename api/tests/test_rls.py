"""Row Level Security: members can read, outsiders (signed in but not invited) cannot."""

from __future__ import annotations

import uuid

import httpx
import pytest
from authutil import ANON_KEY, create_auth_user, sign_in
from studio_shared import db
from studio_shared.config import get_settings

pytestmark = pytest.mark.integration


def rest(token: str | None, path: str, method: str = "GET", **kw) -> httpx.Response:
    h = {"apikey": ANON_KEY}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return httpx.request(method, f"{get_settings().supabase_url}/rest/v1/{path}", headers=h, **kw)


def test_member_reads_outsider_does_not(make_member):
    uid, _, hdr = make_member("member")
    token = hdr["Authorization"][7:]
    pid = db.fetch_one(
        "insert into projects (type, title, created_by) values ('clip','rls test',%s) returning id", [uid]
    )["id"]
    try:
        assert any(p["id"] == str(pid) for p in rest(token, "projects?select=id").json())

        outsider = f"o-{uuid.uuid4().hex[:8]}@example.com"
        create_auth_user(outsider)
        otoken = sign_in(outsider)
        assert rest(otoken, "projects?select=id").json() == []
        assert [m["email"] for m in rest(otoken, "members?select=email").json()] == [outsider]
        anon = rest(None, "projects?select=id")
        assert anon.status_code in (401, 403) or anon.json() == []
    finally:
        db.execute("delete from projects where id = %s", [pid])


def test_settings_never_readable_by_clients(make_member):
    _, _, hdr = make_member("admin")
    r = rest(hdr["Authorization"][7:], "settings?select=*")
    assert r.status_code in (401, 403) or r.json() == []


def test_member_cannot_change_worker_columns(make_member):
    uid, _, hdr = make_member("member")
    token = hdr["Authorization"][7:]
    pid = db.fetch_one(
        "insert into projects (type, title, created_by) values ('clip','x',%s) returning id", [uid]
    )["id"]
    cid = db.fetch_one(
        "insert into clips (project_id, idx, start_s, end_s) values (%s, 1, 0, 10) returning id", [pid]
    )["id"]
    try:
        ok = rest(token, f"clips?id=eq.{cid}", "PATCH", json={"title": "new title"})
        assert ok.status_code in (200, 204)
        bad = rest(token, f"clips?id=eq.{cid}", "PATCH", json={"video_key": "evil"})
        assert bad.status_code in (401, 403)
        assert db.fetch_one("select title, video_key from clips where id = %s", [cid]) == {
            "title": "new title",
            "video_key": None,
        }
    finally:
        db.execute("delete from projects where id = %s", [pid])
