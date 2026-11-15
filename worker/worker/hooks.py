"""Side effects after a job ends (e.g. update project status). Extended per job kind."""

from __future__ import annotations

from typing import Any

from studio_shared import db

_PROJECT_STATUS = {
    ("clip", "succeeded"): "ready",
    ("clip", "failed"): "failed",
    ("story_render", "succeeded"): "rendered",
    ("story_render", "failed"): "render_failed",
}


def on_job_started(job: dict[str, Any]) -> None:
    status = {"clip": "processing", "story_render": "rendering"}.get(job["kind"])
    if status and job.get("project_id"):
        db.execute("update projects set status = %s where id = %s", [status, job["project_id"]])


def on_job_finished(job: dict[str, Any], status: str, result: dict[str, Any]) -> None:
    new = _PROJECT_STATUS.get((job["kind"], status))
    if new and job.get("project_id"):
        db.execute("update projects set status = %s where id = %s", [new, job["project_id"]])
