"""Setup, invites and roles through the API."""

from __future__ import annotations

import httpx
import pytest
from studio_shared import db

pytestmark = pytest.mark.integration


def test_setup_creates_first_admin_only_once(client, unique_email, monkeypatch):
    existing = db.fetch_all("select * from members")
    db.execute("delete from members")
    try:
        assert client.get("/setup/status").json() == {"needs_setup": True}
        r = client.post(
            "/setup", json={"token": "wrong", "email": unique_email, "password": "a-long-password"}
        )
        assert r.status_code == 403
        r = client.post(
            "/setup",
            json={"token": "local-setup-token", "email": unique_email, "password": "a-long-password"},
        )
        assert r.status_code == 200, r.text
        row = db.fetch_one("select role from members where email = %s", [unique_email])
        assert row["role"] == "admin"
        r = client.post(
            "/setup",
            json={"token": "local-setup-token", "email": "x" + unique_email, "password": "a-long-password"},
        )
        assert r.status_code == 409
    finally:
        uid = db.fetch_one("select user_id from members where email = %s", [unique_email])
        db.execute("delete from members")
        for m in existing:
            db.execute(
                "insert into members (user_id, email, role, display_name, created_at) values (%s,%s,%s,%s,%s)",
                [m["user_id"], m["email"], m["role"], m["display_name"], m["created_at"]],
            )
        if uid:
            from app.supabase_admin import delete_user

            delete_user(str(uid["user_id"]))


def test_invite_flow_creates_membership(client, make_member, unique_email):
    _, _, admin = make_member("admin")
    _, _, member = make_member("member")
    assert client.post("/invites", json={"email": unique_email}, headers=member).status_code == 403
    r = client.post("/invites", json={"email": unique_email, "role": "member"}, headers=admin)
    assert r.status_code == 201, r.text
    # Invite creates the auth user; the DB trigger turns the invite into a membership.
    row = db.fetch_one("select role, user_id from members where email = %s", [unique_email])
    assert row and row["role"] == "member"
    # An email was sent (Mailpit in local dev).
    msgs = httpx.get("http://127.0.0.1:54324/api/v1/search", params={"query": f"to:{unique_email}"}).json()
    assert msgs["messages_count"] >= 1
    from app.supabase_admin import delete_user

    delete_user(str(row["user_id"]))


def test_non_member_gets_403(client, unique_email):
    from authutil import create_auth_user, sign_in

    uid = create_auth_user(unique_email)
    r = client.get("/me", headers={"Authorization": f"Bearer {sign_in(unique_email)}"})
    assert r.status_code == 403
    from app.supabase_admin import delete_user

    delete_user(uid)


def test_last_admin_cannot_demote_self(client, make_member):
    db_admins = db.fetch_all("select user_id from members where role = 'admin'")
    uid, _, admin = make_member("admin")
    if not db_admins:
        r = client.patch(f"/members/{uid}", json={"role": "member"}, headers=admin)
        assert r.status_code == 400
