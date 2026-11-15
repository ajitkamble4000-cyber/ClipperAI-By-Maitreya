"""Premium motion: image-to-video with Veo for chosen scenes.

Each scene's operation name is stored on the scene as soon as it is submitted, so a crashed or restarted
worker resumes polling instead of submitting (and paying for) a second generation. Scenes fail
independently and can be retried one by one."""

from __future__ import annotations

import logging
import time
from typing import Any

from studio_shared import app_settings, db, storage, usage
from studio_shared.gemini import CallContext, GeminiError, get_client
from studio_shared.veo_math import veo_seconds

from ..pipeline import JobContext, Pipeline, Step, StepFailed
from . import assets

log = logging.getLogger(__name__)
POLL_EVERY = 10.0
OP_TIMEOUT = 15 * 60

MOTION_HINT = {
    "zoom-in": "slow cinematic push-in",
    "zoom-out": "slow pull-back revealing scale",
    "pan-left": "smooth camera pan to the left",
    "pan-right": "smooth camera pan to the right",
    "shake": "sudden impact with camera shake",
    "static": "locked-off camera, subtle natural motion",
}


def veo_prompt(scene: dict[str, Any]) -> str:
    return (
        f"{scene['image_prompt'].strip()} Animate this image: {MOTION_HINT.get(scene['camera_motion'], 'subtle motion')}, "
        "natural realistic movement of the subject and environment, cinematic. No text or captions."
    )


def _targets(ctx: JobContext) -> list[dict[str, Any]]:
    ids = ctx.params.get("scene_ids") or []
    rows = db.fetch_all(
        "select * from scenes where project_id = %s and id = any(%s) order by idx", [ctx.project_id, ids]
    )
    missing = [r["idx"] + 1 for r in rows if not r["image_key"]]
    if missing:
        raise StepFailed(f"Scene {', '.join(map(str, missing))} needs an image before it can become a video.")
    return rows


def run_veo(ctx: JobContext) -> dict[str, Any]:
    scenes = _targets(ctx)
    if not scenes:
        raise StepFailed("No scenes selected for AI video.")
    gem = get_client(CallContext(ctx.user_id, ctx.project_id, ctx.job_id))
    model = app_settings.model_for("video")
    if not model:
        raise StepFailed("No video (Veo) model is selected. An admin can choose one in Settings → AI.")
    pending: dict[str, dict[str, Any]] = {}
    done: list[str] = []
    failed: dict[str, str] = {}

    # Submit (or resume) each scene.
    for s in scenes:
        ctx.check_canceled()
        secs = veo_seconds(s)
        prompt = veo_prompt(s)
        h = assets.key_for(kind="veo", image=s["image_key"], prompt=prompt, seconds=secs, model=model)
        cached = assets.get(h)
        if cached and storage.exists(cached):
            db.execute(
                "update scenes set video_key = %s, video_status = 'done', veo_error = null, veo_operation = null "
                "where id = %s",
                [cached, s["id"]],
            )
            done.append(str(s["id"]))
            continue
        if s["veo_operation"] and s["video_status"] == "running":
            op = gem.operation_from_name(s["veo_operation"])
            ctx.log(f"Scene {s['idx'] + 1}: resuming Veo operation")
        else:
            try:
                usage.assert_premium_allowed()
                img = storage.get_bytes(s["image_key"])
                op = gem.start_video(prompt=prompt, image=img, mime="image/png", seconds=secs)
            except GeminiError as e:
                failed[str(s["id"])] = str(e)
                db.execute(
                    "update scenes set video_status = 'failed', veo_error = %s where id = %s",
                    [str(e)[:500], s["id"]],
                )
                continue
            db.execute(
                "update scenes set video_status = 'running', veo_operation = %s, veo_error = null, "
                "veo_started_at = now() where id = %s",
                [op.name, s["id"]],
            )
        pending[str(s["id"])] = {"op": op, "scene": s, "hash": h, "secs": secs, "since": time.monotonic()}
    total = len(scenes)

    # Poll until every operation finishes.
    while pending:
        ctx.check_canceled()
        ctx.progress(
            (len(done) + len(failed)) / total, f"AI video: {len(done)} done, {len(pending)} rendering"
        )
        time.sleep(POLL_EVERY)
        for sid, p in list(pending.items()):
            s = p["scene"]
            try:
                op = gem.get_operation(p["op"])
            except GeminiError as e:
                log.warning("poll failed for %s: %s", sid, e)
                continue
            p["op"] = op
            err = getattr(op, "error", None)
            if op.done and not err:
                try:
                    data = gem.download_video(op, model=model, seconds=p["secs"])
                except GeminiError as e:
                    err = str(e)
                else:
                    usage.record(
                        model=model,
                        kind="video",
                        user_id=ctx.user_id,
                        project_id=ctx.project_id,
                        job_id=ctx.job_id,
                        seconds=p["secs"],
                        meta={"scene_id": sid},
                    )
                    key = f"assets/{p['hash']}.mp4"
                    storage.put_bytes(key, data, "video/mp4")
                    assets.put(p["hash"], "video", key, {"scene_id": sid})
                    db.execute(
                        "update scenes set video_key = %s, video_status = 'done', veo_operation = null "
                        "where id = %s",
                        [key, sid],
                    )
                    done.append(sid)
                    pending.pop(sid)
                    continue
            if err or time.monotonic() - p["since"] > OP_TIMEOUT:
                msg = str(err.get("message") if isinstance(err, dict) else err) if err else "timed out"
                failed[sid] = msg
                db.execute(
                    "update scenes set video_status = 'failed', veo_error = %s, veo_operation = null where id = %s",
                    [msg[:500], sid],
                )
                ctx.log(f"Scene {s['idx'] + 1}: Veo failed ({msg})", "warn")
                pending.pop(sid)
    if failed and not done:
        raise StepFailed(
            f"AI video failed for every scene ({next(iter(failed.values()))}). Retry, or use standard motion."
        )
    return {"done": len(done), "failed": len(failed)}


def build_veo(params: dict) -> Pipeline:
    return Pipeline([Step("veo", run_veo, label="AI video (Veo)")], finalize=lambda c: c.outputs["veo"])
