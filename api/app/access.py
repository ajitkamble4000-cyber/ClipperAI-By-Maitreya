"""Who may see / change what. Mirrors the RLS rules so the service-role API enforces the same thing:
a project belongs to its creator; admins see everything; Staff/Creator team members share a team library;
a project can also be shared with specific people as viewer (watch/download) or editor (change it)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, status
from studio_shared import db

from .auth import Member

NOT_FOUND = "Not found"


def _uuid(value: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from e


def _visible(project: dict[str, Any], m: Member) -> bool:
    if str(project["created_by"]) == m.user_id or m.is_admin:
        return True
    return bool(m.team and project.get("creator_team"))


VIEW_ONLY = "You can view this project but not change it. Ask its owner for editor access."


def share_role(project_id: str, m: Member) -> str | None:
    row = db.fetch_one(
        "select role from project_members where project_id = %s and user_id = %s", [project_id, m.user_id]
    )
    return row["role"] if row else None


def project_for(project_id: str, m: Member, write: bool = False) -> dict[str, Any]:
    """The project if `m` may see it (404 otherwise). With write=True, viewers get a clear 403."""
    project_id = _uuid(project_id)
    row = db.fetch_one(
        "select p.*, cm.team as creator_team from projects p left join members cm on cm.user_id = p.created_by "
        "where p.id = %s",
        [project_id],
    )
    if row and _visible(row, m):
        row["access"] = (
            "owner" if str(row["created_by"]) == m.user_id else "team" if not m.is_admin else "admin"
        )
        return row
    role = share_role(project_id, m) if row else None
    if not role:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    if write and role != "editor":
        raise HTTPException(status.HTTP_403_FORBIDDEN, VIEW_ONLY)
    row["access"] = role
    return row


def can_delete(project: dict[str, Any], m: Member) -> bool:
    return str(project["created_by"]) == m.user_id or m.is_admin


def clip_for(clip_id: str, m: Member, write: bool = True) -> dict[str, Any]:
    clip_id = _uuid(clip_id)
    row = db.fetch_one("select * from clips where id = %s", [clip_id])
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    project_for(str(row["project_id"]), m, write=write)
    return row


def scene_for(scene_id: str, m: Member, write: bool = True) -> dict[str, Any]:
    scene_id = _uuid(scene_id)
    row = db.fetch_one("select * from scenes where id = %s", [scene_id])
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    project_for(str(row["project_id"]), m, write=write)
    return row


def job_for(job_id: str, m: Member) -> dict[str, Any]:
    job_id = _uuid(job_id)
    row = db.fetch_one("select * from jobs where id = %s", [job_id])
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    if str(row["created_by"]) == m.user_id or m.is_admin:
        return row
    if row["project_id"]:
        project_for(str(row["project_id"]), m)
        return row
    raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)


def key_allowed(key: str, m: Member) -> bool:
    """May this user get a signed URL for this storage key?"""
    if ".." in key or key.startswith("/"):
        return False
    parts = key.split("/")
    if key.startswith(("assets/", "library/")):
        return True  # content-addressed (unguessable) or the shared library
    if parts[0] in ("uploads", "brand"):
        return len(parts) > 1 and (parts[1] == m.user_id or m.is_admin)
    if parts[0] in ("projects", "sources") and len(parts) > 1:
        try:
            project_for(parts[1], m)
            return True
        except HTTPException:
            return False
    if parts[0] == "jobs" and len(parts) > 1:
        try:
            job_for(parts[1], m)
            return True
        except HTTPException:
            return False
    return False
