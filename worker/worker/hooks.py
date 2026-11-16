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
    if status == "failed":
        from studio_shared import tokens

        tokens.refund_job(str(job["id"]), "job failed")  # nobody pays for a job that didn't deliver
        _notify(job, "failed", result.get("error"))
    elif status == "succeeded":
        _notify(job, "succeeded", None)
        if job["kind"] in ("clip", "story_render") and job.get("created_by"):
            try:  # a friend's first finished video unlocks the referral reward for both of them
                from studio_shared.growth import maybe_reward_referral

                maybe_reward_referral(str(job["created_by"]))
            except Exception:  # noqa: BLE001 - rewards must never break a finished job
                import logging

                logging.getLogger(__name__).exception("referral reward failed")
    new = _PROJECT_STATUS.get((job["kind"], status))
    if new and job.get("project_id"):
        db.execute("update projects set status = %s where id = %s", [new, job["project_id"]])


def _notify(job: dict[str, Any], status: str, error: str | None) -> None:
    """In-app notification for the job's owner (the bell in the app)."""
    if not job.get("created_by") or job["kind"] in (
        "dummy",
        "clip_zip",
        "story_scene_ai",
        "story_image_one",
        "thumbnail",
        "title_variants",
    ):
        return
    try:
        title_row = (
            db.fetch_one("select title, type from projects where id = %s", [job.get("project_id")])
            if job.get("project_id")
            else None
        )
        name = (title_row or {}).get("title") or "Your job"
        label = {
            "clip": "clips are ready",
            "clip_rerender": "clip was re-rendered",
            "story_render": "video is ready",
            "story_script": "script is ready",
            "story_images": "images are ready",
            "story_voice": "voiceover is ready",
            "story_veo": "AI video clips are ready",
            "story_characters": "characters are ready",
        }.get(job["kind"], "job finished")
        link = None
        if title_row:
            link = f"/{'clipper' if title_row['type'] == 'clip' else 'story'}/{job['project_id']}"
        if status == "failed":
            db.execute(
                "insert into notifications (user_id, kind, title, body, link) values (%s,'error',%s,%s,%s)",
                [job["created_by"], f"{name}: failed (tokens refunded)", (error or "")[:300], link],
            )
        else:
            db.execute(
                "insert into notifications (user_id, kind, title, body, link) values (%s,'success',%s,'',%s)",
                [job["created_by"], f"{name}: {label}", link],
            )
    except Exception:  # noqa: BLE001 - notifications must never break a job
        pass
