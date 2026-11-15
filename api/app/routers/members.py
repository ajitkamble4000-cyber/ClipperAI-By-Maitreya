"""Members and invites (admin manages; everyone can see the team)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from studio_shared import db
from studio_shared.config import get_settings

from .. import supabase_admin
from ..auth import AdminMember, CurrentMember

router = APIRouter(tags=["members"])


@router.get("/me")
def me(m: CurrentMember) -> dict:
    return {"user_id": m.user_id, "email": m.email, "role": m.role, "display_name": m.display_name}


class ProfileIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)


@router.patch("/me")
def update_me(body: ProfileIn, m: CurrentMember) -> dict:
    db.execute("update members set display_name = %s where user_id = %s", [body.display_name, m.user_id])
    return {"ok": True}


@router.get("/members")
def list_members(_: CurrentMember) -> list[dict]:
    return db.fetch_all(
        "select user_id, email, role, display_name, created_at from members order by created_at"
    )


@router.get("/invites")
def list_invites(_: AdminMember) -> list[dict]:
    return db.fetch_all(
        "select id, email, role, created_at from invites where accepted_at is null order by created_at desc"
    )


class InviteIn(BaseModel):
    email: EmailStr
    role: Literal["admin", "member"] = "member"


@router.post("/invites", status_code=201)
def create_invite(body: InviteIn, admin: AdminMember) -> dict:
    email = body.email.lower()
    if db.fetch_one("select 1 from members where lower(email) = %s", [email]):
        raise HTTPException(status.HTTP_409_CONFLICT, "That person is already a member")
    row = db.fetch_one(
        """insert into invites (email, role, invited_by) values (%s, %s, %s)
           on conflict (lower(email)) where accepted_at is null do update set role = excluded.role
           returning id""",
        [email, body.role, admin.user_id],
    )
    redirect = f"{get_settings().origins[0]}/auth/accept"
    try:
        supabase_admin.invite(email, redirect)
    except HTTPException:
        db.execute("delete from invites where id = %s", [row["id"]])
        raise
    return {"id": row["id"], "email": email, "role": body.role}


@router.delete("/invites/{invite_id}")
def revoke_invite(invite_id: str, _: AdminMember) -> dict:
    db.execute("delete from invites where id = %s and accepted_at is null", [invite_id])
    return {"ok": True}


class RoleIn(BaseModel):
    role: Literal["admin", "member"]


def _admin_count() -> int:
    row = db.fetch_one("select count(*) as n from members where role = 'admin'")
    return int(row["n"]) if row else 0


@router.patch("/members/{user_id}")
def set_role(user_id: str, body: RoleIn, admin: AdminMember) -> dict:
    if user_id == admin.user_id and body.role != "admin" and _admin_count() <= 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You are the only admin")
    db.execute("update members set role = %s where user_id = %s", [body.role, user_id])
    return {"ok": True}


@router.delete("/members/{user_id}")
def remove_member(user_id: str, admin: AdminMember) -> dict:
    if user_id == admin.user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot remove yourself")
    db.execute("delete from members where user_id = %s", [user_id])
    supabase_admin.delete_user(user_id)
    return {"ok": True}
