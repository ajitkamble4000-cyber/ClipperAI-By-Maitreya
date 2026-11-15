"""Project-level actions shared by Clipper and Story Studio."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from studio_shared import db, jobs, storage, tokens

from ..access import can_delete, project_for
from ..auth import CurrentMember, audit
from ..plans import launch

router = APIRouter(prefix="/projects", tags=["projects"])


def get_project(project_id: str, m) -> dict:
    return project_for(project_id, m)


@router.delete("/{project_id}")
def delete_project(project_id: str, m: CurrentMember) -> dict:
    p = get_project(project_id, m)
    if not can_delete(p, m):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the creator or an admin can delete a project")
    for j in db.fetch_all(
        "select id from jobs where project_id = %s and status in ('queued','running')", [project_id]
    ):
        jobs.cancel(j["id"])
        tokens.refund_job(str(j["id"]), "project deleted")
    for s in db.fetch_all(
        "select r2_key from sources where project_id = %s and r2_key is not null", [project_id]
    ):
        try:
            storage.delete(s["r2_key"])
        except Exception:  # noqa: BLE001
            pass
    storage.delete_prefix(f"projects/{project_id}/")
    storage.delete_prefix(f"sources/{project_id}/")
    db.execute("delete from projects where id = %s", [project_id])
    if str(p["created_by"]) != m.user_id:
        audit(m, "project.delete", "project", project_id, title=p["title"])
    return {"ok": True}


@router.post("/{project_id}/zip", status_code=201)
def zip_project(project_id: str, m: CurrentMember) -> dict:
    p = get_project(project_id, m)
    if p["type"] != "clip":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only clip projects can be zipped")
    job = launch(m, "clip_zip", project_id, {})
    return job
