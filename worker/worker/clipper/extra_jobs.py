"""Clip re-render (nudged times / new caption style / new reframe) and 'download all as ZIP'."""

from __future__ import annotations

import json
import zipfile
from typing import Any

from studio_shared import db, storage

from ..media.names import slugify
from ..pipeline import JobContext, Pipeline, Step, StepFailed
from ..transcribe.base import Transcript
from .pipeline import render_one


def _rerender(ctx: JobContext) -> dict[str, Any]:
    p = ctx.params
    clip = db.fetch_one("select * from clips where id = %s", [p["clip_id"]])
    if not clip:
        raise StepFailed("Clip not found")
    proj = db.fetch_one("select meta from projects where id = %s", [clip["project_id"]])
    tkey = (proj or {}).get("meta", {}).get("transcript_key")
    if not tkey:
        raise StepFailed("This project has no transcript; re-run the clip job.")
    t = Transcript.from_json(json.loads(storage.get_bytes(tkey)))
    updates: dict[str, Any] = {}
    cut_changed = False
    if p.get("start") is not None or p.get("end") is not None:
        s = float(p.get("start", clip["start_s"]))
        e = float(p.get("end", clip["end_s"]))
        if e - s < 3:
            raise StepFailed("A clip must be at least 3 seconds long.")
        updates["start_s"], updates["end_s"] = round(max(0.0, s), 3), round(e, 3)
        cut_changed = True
    if p.get("reframe") and p["reframe"] != clip["reframe"]:
        updates["reframe"] = p["reframe"]
        cut_changed = True
    if p.get("caption_style") is not None:
        updates["caption_style"] = p["caption_style"]
    if updates:
        cols = ", ".join(f"{k} = %({k})s" for k in updates)
        db.execute(
            f"update clips set {cols}, status = 'rendering' where id = %(id)s", {**updates, "id": clip["id"]}
        )
    else:
        db.execute("update clips set status = 'rendering' where id = %s", [clip["id"]])
    clip = db.fetch_one("select * from clips where id = %s", [clip["id"]])
    hook = bool((proj["meta"].get("options") or {}).get("hook_overlay", True)) if proj else True
    try:
        out = render_one(ctx, clip, t, hook_overlay=hook, reuse_base=not cut_changed, progress=ctx.progress)
    except Exception:
        db.execute("update clips set status = 'ready' where id = %s and video_key is not null", [clip["id"]])
        db.execute("update clips set status = 'failed' where id = %s and video_key is null", [clip["id"]])
        raise
    return out


def _zip(ctx: JobContext) -> dict[str, Any]:
    pid = ctx.project_id
    proj = db.fetch_one("select title from projects where id = %s", [pid])
    clips = db.fetch_all(
        "select filename, video_key, title, description, hashtags from clips where project_id = %s "
        "and status = 'ready' and video_key is not null order by idx",
        [pid],
    )
    if not clips:
        raise StepFailed("No finished clips to download yet.")
    path = ctx.tmp / "clips.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as z:
        lines = []
        for i, c in enumerate(clips):
            ctx.check_canceled()
            local = ctx.fetch(c["video_key"], c["filename"])
            z.write(local, c["filename"])
            lines.append(
                f"{c['filename']}\nTitle: {c['title']}\n{c['description']}\n{' '.join(c['hashtags'])}\n"
            )
            ctx.progress((i + 1) / len(clips), f"Packing {i + 1}/{len(clips)}")
        z.writestr("metadata.txt", "\n".join(lines))
    name = f"{slugify(proj['title'] if proj else 'clips')}.zip"
    key = f"projects/{pid}/exports/{ctx.job_id}/{name}"
    storage.upload_file(path, key, "application/zip")
    return {"key": key, "filename": name}


def build_rerender(params: dict) -> Pipeline:
    return Pipeline(
        [Step("render", _rerender, label="Re-rendering clip")], finalize=lambda ctx: ctx.outputs["render"]
    )


def build_zip(params: dict) -> Pipeline:
    return Pipeline([Step("zip", _zip, label="Preparing ZIP")], finalize=lambda ctx: ctx.outputs["zip"])
