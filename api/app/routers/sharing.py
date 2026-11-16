"""Project sharing: invite people by email as viewer or editor; see what's shared with you."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from studio_shared import db
from studio_shared.notify import notify

from ..access import project_for
from ..auth import CurrentMember, SessionMember, audit
from ..plans import require_feature
from ..ratelimit import check_ip_rate

router = APIRouter(tags=["sharing"])
MAX_MEMBERS = 20


def _owner_project(project_id: str, m) -> dict:
    p = project_for(project_id, m)
    if str(p["created_by"]) != m.user_id and not m.is_admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the project's owner can manage who it's shared with"
        )
    return p


@router.get("/projects/{project_id}/members")
def list_members(project_id: str, m: CurrentMember) -> dict:
    p = project_for(project_id, m)
    owner = db.fetch_one(
        "select user_id, email, display_name from members where user_id = %s", [p["created_by"]]
    )
    people = db.fetch_all(
        """select pm.user_id, pm.role, pm.created_at, mb.email, mb.display_name
             from project_members pm join members mb on mb.user_id = pm.user_id
            where pm.project_id = %s order by pm.created_at""",
        [project_id],
    )
    return {"owner": owner, "members": people, "my_access": p.get("access")}


class ShareIn(BaseModel):
    email: EmailStr
    role: Literal["viewer", "editor"] = "viewer"


@router.post("/projects/{project_id}/members", status_code=201)
def add_member(project_id: str, body: ShareIn, m: SessionMember) -> dict:
    p = _owner_project(project_id, m)
    require_feature(m, "collaboration")
    check_ip_rate(m.user_id, "share-invite", limit=20)  # also stops probing which emails have accounts
    target = db.fetch_one(
        "select user_id, email from members where lower(email) = lower(%s)", [str(body.email)]
    )
    if not target:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No account with that email yet. Ask them to sign up first."
        )
    if str(target["user_id"]) == str(p["created_by"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That's the project's owner")
    if (
        db.fetch_one("select count(*) as n from project_members where project_id = %s", [project_id])["n"]
        >= MAX_MEMBERS
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"A project can be shared with up to {MAX_MEMBERS} people"
        )
    db.execute(
        """insert into project_members (project_id, user_id, role, added_by) values (%s,%s,%s,%s)
           on conflict (project_id, user_id) do update set role = excluded.role""",
        [project_id, target["user_id"], body.role, m.user_id],
    )
    path = "clipper" if p["type"] == "clip" else "story"
    notify(
        str(target["user_id"]),
        f"{m.display_name or m.email} shared “{p['title']}” with you",
        "You can edit it." if body.role == "editor" else "You can watch and download it.",
        link=f"/{path}/{project_id}",
    )
    audit(m, "project.share", "project", project_id, user=target["email"], role=body.role)
    return {"user_id": target["user_id"], "email": target["email"], "role": body.role}


class RoleIn(BaseModel):
    role: Literal["viewer", "editor"]


@router.patch("/projects/{project_id}/members/{user_id}")
def change_role(project_id: str, user_id: str, body: RoleIn, m: SessionMember) -> dict:
    _owner_project(project_id, m)
    try:
        row = db.fetch_one(
            "update project_members set role = %s where project_id = %s and user_id = %s returning role",
            [body.role, project_id, user_id],
        )
    except Exception as e:  # noqa: BLE001 - bad uuid
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not shared with that person") from e
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not shared with that person")
    return {"role": row["role"]}


@router.delete("/projects/{project_id}/members/{user_id}")
def remove_member(project_id: str, user_id: str, m: SessionMember) -> dict:
    """The owner removes someone, or you leave a project shared with you."""
    if user_id != m.user_id:
        _owner_project(project_id, m)
    try:
        db.execute(
            "delete from project_members where project_id = %s and user_id = %s", [project_id, user_id]
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from e
    return {"ok": True}


@router.get("/shared-with-me")
def shared_with_me(m: CurrentMember) -> list[dict]:
    return db.fetch_all(
        """select p.id, p.type, p.title, p.status, p.thumbnail_key, p.updated_at, pm.role,
                  coalesce(o.display_name, o.email) as owner_name
             from project_members pm join projects p on p.id = pm.project_id
             left join members o on o.user_id = p.created_by
            where pm.user_id = %s order by p.updated_at desc limit 100""",
        [m.user_id],
    )
