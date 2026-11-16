"""The signed-in user's profile, the team list (Staff/Creator), and invites (admins)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from studio_shared import db, tokens
from studio_shared.config import get_settings

from .. import supabase_admin
from ..auth import AdminMember, CurrentMember, SessionMember, audit

router = APIRouter(tags=["members"])


def plan_row(plan_id: str) -> dict:
    return db.fetch_one(
        "select id, name, daily_tokens, features, limits, price_usd_month from plans where id = %s", [plan_id]
    ) or {"id": plan_id, "name": plan_id, "daily_tokens": None, "features": [], "limits": {}}


def me_payload(m) -> dict:
    plan = plan_row("team" if m.unlimited else m.plan_id) if m.unlimited else plan_row(m.plan_id)
    row = (
        db.fetch_one("select onboarding, plan_expires_at from members where user_id = %s", [m.user_id]) or {}
    )
    return {
        "user_id": m.user_id,
        "email": m.email,
        "role": m.role,
        "display_name": m.display_name,
        "plan_id": m.plan_id,
        "team": m.team,
        "unlimited": m.unlimited,
        "plan": {**plan, "price_usd_month": float(plan.get("price_usd_month") or 0)},
        "features": list(plan.get("features") or []),
        "limits": plan.get("limits") or {},
        "onboarding": row.get("onboarding") or {},
        "trial_ends_at": row.get("plan_expires_at"),
        "wallet": tokens.get_wallet(m.user_id).to_json(),
    }


@router.get("/me")
def me(m: CurrentMember) -> dict:
    return me_payload(m)


class ProfileIn(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    onboarding: dict[str, bool] | None = None


@router.patch("/me")
def update_me(body: ProfileIn, m: SessionMember) -> dict:
    if body.display_name is not None:
        db.execute("update members set display_name = %s where user_id = %s", [body.display_name, m.user_id])
    if body.onboarding is not None:
        db.execute(
            "update members set onboarding = onboarding || %s where user_id = %s",
            [body.onboarding, m.user_id],
        )
    return {"ok": True}


@router.delete("/me")
def delete_me(m: SessionMember) -> dict:
    """Delete my account and everything I made (projects cascade; files are removed by the cleanup task)."""
    if m.is_owner:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The owner account can't be deleted from the app.")
    from studio_shared import storage

    for p in db.fetch_all("select id from projects where created_by = %s", [m.user_id]):
        storage.delete_prefix(f"projects/{p['id']}/")
        storage.delete_prefix(f"sources/{p['id']}/")
    storage.delete_prefix(f"uploads/{m.user_id}/")
    storage.delete_prefix(f"brand/{m.user_id}/")
    db.execute("delete from projects where created_by = %s", [m.user_id])
    db.execute("delete from members where user_id = %s", [m.user_id])
    supabase_admin.delete_user(m.user_id)
    return {"ok": True}


@router.get("/members")
def list_members(m: CurrentMember) -> list[dict]:
    """Admins see everyone (use /admin/users for search); team members see their team; others see themselves."""
    if m.is_admin:
        q, args = (
            "select user_id, email, role, display_name, team, plan_id, created_at from members order by created_at",
            [],
        )
    elif m.team:
        q, args = (
            (
                "select user_id, email, role, display_name, team, created_at from members "
                "where team is not null order by created_at"
            ),
            [],
        )
    else:
        q, args = (
            "select user_id, email, role, display_name, team, created_at from members where user_id = %s",
            [m.user_id],
        )
    return db.fetch_all(q, args)


@router.get("/invites")
def list_invites(_: AdminMember) -> list[dict]:
    return db.fetch_all(
        "select id, email, role, team, plan_id, created_at from invites where accepted_at is null order by created_at desc"
    )


class InviteIn(BaseModel):
    email: EmailStr
    role: Literal["admin", "user"] = "user"
    team: Literal["staff", "creator"] | None = None
    plan_id: str | None = None


@router.post("/invites", status_code=201)
def create_invite(body: InviteIn, admin: AdminMember) -> dict:
    if body.role == "admin" and not admin.is_owner:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can invite admins")
    email = body.email.lower()
    if db.fetch_one("select 1 from members where lower(email) = %s", [email]):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "That person already has an account. Change their role or team in Admin → Users.",
        )
    if body.plan_id and not db.fetch_one("select 1 from plans where id = %s", [body.plan_id]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown plan")
    row = db.fetch_one(
        """insert into invites (email, role, team, plan_id, invited_by) values (%s, %s, %s, %s, %s)
           on conflict (lower(email)) where accepted_at is null
           do update set role = excluded.role, team = excluded.team, plan_id = excluded.plan_id
           returning id""",
        [email, body.role, body.team, body.plan_id, admin.user_id],
    )
    try:
        supabase_admin.invite(email, f"{get_settings().origins[0]}/auth/accept")
    except HTTPException:
        db.execute("delete from invites where id = %s", [row["id"]])
        raise
    audit(admin, "invite.create", "email", email, role=body.role, team=body.team, plan=body.plan_id)
    return {"id": row["id"], "email": email, "role": body.role, "team": body.team}


@router.delete("/invites/{invite_id}")
def revoke_invite(invite_id: str, admin: AdminMember) -> dict:
    db.execute("delete from invites where id = %s and accepted_at is null", [invite_id])
    audit(admin, "invite.revoke", "invite", invite_id)
    return {"ok": True}
