"""Who may see / change what. Mirrors the RLS rules so the service-role API enforces the same thing:
a project belongs to its creator; admins see everything; Staff/Creator team members share a team library."""

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


def project_for(project_id: str, m: Member) -> dict[str, Any]:
    project_id = _uuid(project_id)
    row = db.fetch_one(
        "select p.*, cm.team as creator_team from projects p left join members cm on cm.user_id = p.created_by "
        "where p.id = %s",
        [project_id],
    )
    if not row or not _visible(row, m):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return row


def can_delete(project: dict[str, Any], m: Member) -> bool:
    return str(project["created_by"]) == m.user_id or m.is_admin


def clip_for(clip_id: str, m: Member) -> dict[str, Any]:
    clip_id = _uuid(clip_id)
    row = db.fetch_one("select * from clips where id = %s", [clip_id])
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    project_for(str(row["project_id"]), m)
    return row


def scene_for(scene_id: str, m: Member) -> dict[str, Any]:
    scene_id = _uuid(scene_id)
    row = db.fetch_one("select * from scenes where id = %s", [scene_id])
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    project_for(str(row["project_id"]), m)
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
