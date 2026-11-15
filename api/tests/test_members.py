"""Accounts: owner by verified email, admins appointed by the owner, invites, suspension, self-service."""

from __future__ import annotations

import httpx
import pytest
from authutil import create_auth_user, sign_in
from studio_shared import db
from studio_shared.config import get_settings

pytestmark = pytest.mark.integration


@pytest.fixture
def owner_email(monkeypatch, unique_email):
    monkeypatch.setattr(get_settings(), "owner_email", unique_email)
    yield unique_email
    db.execute("update members set role = 'admin' where role = 'owner' and email = %s", [unique_email])


def test_owner_is_the_verified_owner_email_only(client, owner_email):
    uid = create_auth_user(owner_email)  # created with email_confirm=True
    hdr = {"Authorization": f"Bearer {sign_in(owner_email)}"}
    me = client.get("/me", headers=hdr).json()
    assert me["role"] == "owner" and me["unlimited"] is True
    # Exactly one owner.
    assert db.fetch_one("select count(*) as n from members where role = 'owner'")["n"] == 1
    # If the email were not verified, the account would not be owner.
    db.execute("update auth.users set email_confirmed_at = null where id = %s", [uid])
    assert client.get("/me", headers=hdr).json()["role"] == "admin"  # demoted (keeps admin, not owner)
    db.execute("update auth.users set email_confirmed_at = now() where id = %s", [uid])
    assert client.get("/me", headers=hdr).json()["role"] == "owner"
    from app.supabase_admin import delete_user

    db.execute("update members set role = 'user' where user_id = %s", [uid])
    delete_user(uid)


def test_signup_creates_free_profile(client, unique_email):
    uid = create_auth_user(unique_email)
    me = client.get("/me", headers={"Authorization": f"Bearer {sign_in(unique_email)}"}).json()
    assert me["role"] == "user" and me["plan_id"] == "free" and me["plan"]["daily_tokens"] == 1000
    assert "clipper" in me["features"] and "premium_video" not in me["features"]
    from app.supabase_admin import delete_user

    delete_user(uid)


def test_only_owner_manages_admins(client, make_member, owner_email):
    _, _, admin = make_member("admin")
    target_uid, _, _ = make_member("user")
    assert (
        client.put(f"/admin/users/{target_uid}/role", json={"role": "admin"}, headers=admin).status_code
        == 403
    )
    oid = create_auth_user(owner_email)
    owner = {"Authorization": f"Bearer {sign_in(owner_email)}"}
    assert (
        client.put(f"/admin/users/{target_uid}/role", json={"role": "admin"}, headers=owner).json()["role"]
        == "admin"
    )
    # An admin can't change another admin.
    assert (
        client.patch(f"/admin/users/{target_uid}", json={"status": "suspended"}, headers=admin).status_code
        == 403
    )
    assert (
        client.put(f"/admin/users/{target_uid}/role", json={"role": "user"}, headers=owner).json()["role"]
        == "user"
    )
    assert (
        db.fetch_one(
            "select count(*) as n from audit_log where action = 'user.role' and target_id = %s", [target_uid]
        )["n"]
        >= 2
    )
    from app.supabase_admin import delete_user

    db.execute("update members set role = 'user' where user_id = %s", [oid])
    delete_user(oid)


def test_admin_sets_plan_team_and_suspends(client, make_member):
    _, _, admin = make_member("admin")
    uid, _, user = make_member("user")
    r = client.patch(f"/admin/users/{uid}", json={"plan_id": "pro", "team": "creator"}, headers=admin)
    assert r.status_code == 200 and r.json()["plan_id"] == "pro" and r.json()["team"] == "creator"
    assert client.get("/me", headers=user).json()["unlimited"] is True  # team members get everything free
    client.patch(
        f"/admin/users/{uid}", json={"status": "suspended", "suspended_reason": "spam"}, headers=admin
    )
    r = client.get("/me", headers=user)
    assert r.status_code == 403 and "spam" in r.json()["detail"]
    users = client.get("/admin/users", params={"q": "m-", "status": "suspended"}, headers=admin).json()
    assert any(u["user_id"] == uid for u in users["users"])
    _, _, plain = make_member("user")
    assert client.get("/admin/users", headers=plain).status_code == 403


def test_invites(client, make_member, unique_email):
    _, _, admin = make_member("admin")
    _, _, user = make_member("user")
    assert client.post("/invites", json={"email": unique_email}, headers=user).status_code == 403
    assert (
        client.post("/invites", json={"email": unique_email, "role": "admin"}, headers=admin).status_code
        == 403
    )
    r = client.post("/invites", json={"email": unique_email, "team": "staff"}, headers=admin)
    assert r.status_code == 201, r.text
    row = db.fetch_one("select role, team, plan_id, user_id from members where email = %s", [unique_email])
    assert row["team"] == "staff" and row["plan_id"] == "team"
    msgs = httpx.get("http://127.0.0.1:54324/api/v1/search", params={"query": f"to:{unique_email}"}).json()
    assert msgs["messages_count"] >= 1
    from app.supabase_admin import delete_user

    delete_user(str(row["user_id"]))


def test_delete_my_account(client, unique_email):
    uid = create_auth_user(unique_email)
    hdr = {"Authorization": f"Bearer {sign_in(unique_email)}"}
    db.execute("insert into projects (type, title, created_by) values ('clip', 'mine', %s)", [uid])
    assert client.delete("/me", headers=hdr).status_code == 200
    assert db.fetch_one("select 1 from members where user_id = %s", [uid]) is None
    assert db.fetch_one("select 1 from projects where created_by = %s", [uid]) is None


def test_announcements(client, make_member):
    _, _, admin = make_member("admin")
    _, _, user = make_member("user")
    a = client.post(
        "/admin/announcements", json={"message": "Maintenance tonight", "level": "warning"}, headers=admin
    )
    assert a.status_code == 201
    assert any(
        x["message"] == "Maintenance tonight" for x in client.get("/announcements", headers=user).json()
    )
    client.delete(f"/admin/announcements/{a.json()['id']}", headers=admin)
    assert not any(
        x["message"] == "Maintenance tonight" for x in client.get("/announcements", headers=user).json()
    )
