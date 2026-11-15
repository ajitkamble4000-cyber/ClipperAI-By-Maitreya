"""Admin panel API. Admins manage users (plan, team, suspension, tokens); only the owner manages admins."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from studio_shared import db

from .. import supabase_admin
from ..auth import AdminMember, OwnerMember, audit

router = APIRouter(prefix="/admin", tags=["admin"])

USER_COLS = """m.user_id, m.email, m.role, m.display_name, m.plan_id, m.team, m.status, m.suspended_reason,
               m.created_at, m.last_seen_at,
               (select count(*) from projects p where p.created_by = m.user_id) as projects"""


def _target(user_id: str) -> dict[str, Any]:
    row = db.fetch_one(f"select {USER_COLS} from members m where m.user_id = %s", [user_id])
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return row


def _guard(actor, target: dict[str, Any]) -> None:
    """Admins can't act on the owner or on other admins; only the owner can."""
    if target["role"] == "owner" and not actor.is_owner:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Nobody but the owner can change the owner account")
    if target["role"] == "admin" and not actor.is_owner and str(target["user_id"]) != actor.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can manage admins")


@router.get("/users")
def list_users(
    _: AdminMember,
    q: str | None = Query(default=None, max_length=100),
    role: str | None = None,
    plan: str | None = None,
    team: str | None = None,
    status_: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
) -> dict:
    where, args = ["true"], []
    if q:
        where.append("(m.email ilike %s or m.display_name ilike %s)")
        args += [f"%{q}%", f"%{q}%"]
    for col, val in (("m.role", role), ("m.plan_id", plan), ("m.status", status_)):
        if val:
            where.append(f"{col} = %s")
            args.append(val)
    if team == "none":
        where.append("m.team is null")
    elif team:
        where.append("m.team = %s")
        args.append(team)
    w = " and ".join(where)
    total = db.fetch_one(f"select count(*) as n from members m where {w}", args)["n"]
    rows = db.fetch_all(
        f"select {USER_COLS} from members m where {w} order by m.created_at desc limit %s offset %s",
        [*args, per_page, (page - 1) * per_page],
    )
    return {"total": total, "page": page, "per_page": per_page, "users": rows}


@router.get("/users/{user_id}")
def get_user(user_id: str, _: AdminMember) -> dict:
    u = _target(user_id)
    u["recent_projects"] = db.fetch_all(
        "select id, type, title, status, created_at from projects where created_by = %s order by created_at desc limit 20",
        [user_id],
    )
    u["recent_jobs"] = db.fetch_all(
        "select id, kind, status, error, created_at from jobs where created_by = %s order by created_at desc limit 20",
        [user_id],
    )
    return u


class UserPatch(BaseModel):
    plan_id: str | None = None
    team: Literal["staff", "creator", "none"] | None = None
    status: Literal["active", "suspended"] | None = None
    suspended_reason: str | None = Field(default=None, max_length=300)
    display_name: str | None = Field(default=None, max_length=80)


@router.patch("/users/{user_id}")
def patch_user(user_id: str, body: UserPatch, admin: AdminMember) -> dict:
    target = _target(user_id)
    _guard(admin, target)
    sets: dict[str, Any] = {}
    if body.plan_id is not None:
        if not db.fetch_one("select 1 from plans where id = %s", [body.plan_id]):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown plan")
        sets["plan_id"] = body.plan_id
    if body.team is not None:
        sets["team"] = None if body.team == "none" else body.team
    if body.status is not None:
        if str(target["user_id"]) == admin.user_id and body.status == "suspended":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can't suspend yourself")
        sets["status"] = body.status
        sets["suspended_reason"] = body.suspended_reason if body.status == "suspended" else None
    if body.display_name is not None:
        sets["display_name"] = body.display_name
    if not sets:
        return target
    cols = ", ".join(f"{k} = %({k})s" for k in sets)
    db.execute(f"update members set {cols} where user_id = %(id)s", {**sets, "id": user_id})
    if "plan_id" in sets or "team" in sets:
        from studio_shared import tokens

        tokens.on_plan_change(user_id, actor_id=admin.user_id)
    audit(admin, "user.update", "user", user_id, email=target["email"], **{k: v for k, v in sets.items()})
    return _target(user_id)


class RoleIn(BaseModel):
    role: Literal["admin", "user"]


@router.put("/users/{user_id}/role")
def set_role(user_id: str, body: RoleIn, owner: OwnerMember) -> dict:
    """Owner only: make someone an admin or take admin away."""
    target = _target(user_id)
    if target["role"] == "owner":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The owner's role can't be changed")
    db.execute("update members set role = %s where user_id = %s", [body.role, user_id])
    audit(owner, "user.role", "user", user_id, email=target["email"], role=body.role)
    return _target(user_id)


@router.delete("/users/{user_id}")
def delete_user(user_id: str, admin: AdminMember) -> dict:
    target = _target(user_id)
    _guard(admin, target)
    if str(target["user_id"]) == admin.user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Use Account settings to delete your own account")
    from studio_shared import storage

    for p in db.fetch_all("select id from projects where created_by = %s", [user_id]):
        storage.delete_prefix(f"projects/{p['id']}/")
        storage.delete_prefix(f"sources/{p['id']}/")
    storage.delete_prefix(f"uploads/{user_id}/")
    storage.delete_prefix(f"brand/{user_id}/")
    db.execute("delete from projects where created_by = %s", [user_id])
    db.execute("delete from members where user_id = %s", [user_id])
    supabase_admin.delete_user(user_id)
    audit(admin, "user.delete", "user", user_id, email=target["email"])
    return {"ok": True}


@router.get("/admins")
def list_admins(_: AdminMember) -> list[dict]:
    return db.fetch_all(
        f"select {USER_COLS} from members m where m.role in ('owner','admin') order by m.role desc, m.created_at"
    )


@router.get("/audit")
def audit_log(
    _: AdminMember, limit: int = Query(default=100, ge=1, le=500), action: str | None = None
) -> list[dict]:
    if action:
        return db.fetch_all(
            "select * from audit_log where action like %s order by ts desc limit %s", [f"{action}%", limit]
        )
    return db.fetch_all("select * from audit_log order by ts desc limit %s", [limit])


# ---------------------------------------------------------------- announcements
class AnnouncementIn(BaseModel):
    message: str = Field(min_length=3, max_length=500)
    level: Literal["info", "warning", "success"] = "info"
    expires_at: datetime | None = None


@router.get("/announcements")
def list_announcements(_: AdminMember) -> list[dict]:
    return db.fetch_all("select * from announcements order by created_at desc limit 50")


@router.post("/announcements", status_code=201)
def create_announcement(body: AnnouncementIn, admin: AdminMember) -> dict:
    row = db.fetch_one(
        "insert into announcements (message, level, expires_at, created_by) values (%s,%s,%s,%s) returning *",
        [body.message, body.level, body.expires_at, admin.user_id],
    )
    audit(admin, "announcement.create", "announcement", str(row["id"]), message=body.message)
    return row


@router.delete("/announcements/{aid}")
def end_announcement(aid: str, admin: AdminMember) -> dict:
    db.execute("update announcements set active = false where id = %s", [aid])
    audit(admin, "announcement.end", "announcement", aid)
    return {"ok": True}
