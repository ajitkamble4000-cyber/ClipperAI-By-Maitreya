"""Project-level actions shared by Clipper and Story Studio."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from studio_shared import db, jobs, storage

from ..auth import CurrentMember
from ..queue import enqueue
from ..ratelimit import check_job_rate

router = APIRouter(prefix="/projects", tags=["projects"])


def get_project(project_id: str) -> dict:
    row = db.fetch_one("select * from projects where id = %s", [project_id])
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return row


@router.delete("/{project_id}")
def delete_project(project_id: str, m: CurrentMember) -> dict:
    p = get_project(project_id)
    if not (m.is_admin or str(p["created_by"]) == m.user_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the creator or an admin can delete a project")
    for j in db.fetch_all(
        "select id from jobs where project_id = %s and status in ('queued','running')", [project_id]
    ):
        jobs.cancel(j["id"])
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
    return {"ok": True}


@router.post("/{project_id}/zip", status_code=201)
def zip_project(project_id: str, m: CurrentMember) -> dict:
    p = get_project(project_id)
    if p["type"] != "clip":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only clip projects can be zipped")
    check_job_rate(m.user_id)
    job = jobs.create_job("clip_zip", project_id=project_id, params={}, user_id=m.user_id)
    enqueue(job)
    return job
