"""Clipper job: ingest -> transcribe -> find moments -> render clips."""

from __future__ import annotations

import json
from typing import Any

import numpy as np
from studio_shared import app_settings, db, storage, usage
from studio_shared.gemini import CallContext, GeminiError, available, get_client

from ..media import audio, ffmpeg
from ..media.names import clip_filename
from ..pipeline import JobContext, Pipeline, Step, StepFailed
from ..transcribe import cache as tcache
from ..transcribe.base import Transcript
from ..transcribe.faster_whisper_impl import get_transcriber
from . import ingest
from .moments import basic, gemini_moments, validate
from .moments.schema import Candidate
from .render import pick_thumbnail, render_base, render_final

HOP = 0.5


def _params(ctx: JobContext) -> dict[str, Any]:
    p = ctx.params
    return {
        "n": int(max(1, min(20, p.get("num_clips", 5)))),
        "min_len": int(max(15, min(180, p.get("min_len", 20)))),
        "max_len": int(max(15, min(180, p.get("max_len", 60)))),
        "content_type": p.get("content_type", "podcast"),
        "reframe": p.get("reframe", "face"),
        "caption_style": p.get("caption_style") or {"preset": "bold_pop"},
        "language": p.get("language") or None,
        "visual": bool(p.get("visual_analysis")),
        "hook_overlay": bool(p.get("hook_overlay", True)),
        "force_basic": bool(p.get("force_basic")),
    }


# ---------------------------------------------------------------- steps
def step_transcribe(ctx: JobContext) -> dict[str, Any]:
    src = ingest.local_source(ctx)
    meta = ctx.outputs["ingest"]
    wav = ffmpeg.extract_audio(src, ctx.tmp / "audio.wav") if meta.get("has_audio", True) else None
    loud_key = ctx.job_key("loudness.json")
    curve = audio.loudness_curve(wav, HOP) if wav else np.zeros(0)
    storage.put_bytes(loud_key, json.dumps([round(float(x), 2) for x in curve]).encode(), "application/json")

    model = app_settings.get_row()["whisper_model"]
    tr = get_transcriber(model)
    lang = _params(ctx)["language"]
    lang = lang if lang in ("en", "hi") else None  # "hinglish"/auto -> let whisper detect
    cached = tcache.get(meta["hash"], tr.name)
    if cached:
        ctx.log("Using cached transcript")
        key = f"cache/transcripts/{meta['hash']}-{tr.name}.json"
        return {
            "transcript_key": key,
            "loudness_key": loud_key,
            "language": cached.language,
            "words": len(cached.words),
        }
    if not wav:
        t = Transcript(language=lang or "en", duration=meta["duration"], segments=[])
    else:
        ctx.progress(0.05, "Loading speech model")
        t = tr.transcribe(
            wav, language=lang, on_progress=lambda f: ctx.progress(0.05 + 0.95 * f, "Transcribing")
        )
    key = tcache.put(meta["hash"], tr.name, t)
    return {"transcript_key": key, "loudness_key": loud_key, "language": t.language, "words": len(t.words)}


def load_transcript(ctx: JobContext) -> Transcript:
    return Transcript.from_json(json.loads(storage.get_bytes(ctx.outputs["transcribe"]["transcript_key"])))


def step_moments(ctx: JobContext) -> dict[str, Any]:
    o = _params(ctx)
    meta = ctx.outputs["ingest"]
    t = load_transcript(ctx)
    curve = np.array(
        json.loads(storage.get_bytes(ctx.outputs["transcribe"]["loudness_key"])), dtype=np.float32
    )
    peaks = [(p.time, p.score) for p in audio.find_peaks(curve, HOP)]
    min_len, max_len = min(o["min_len"], o["max_len"]), max(o["min_len"], o["max_len"])
    duration = float(meta["duration"])
    if duration < min_len:
        min_len = max(5, int(duration * 0.5))
        max_len = max(min_len, int(duration))
    fallback = basic.find(
        t,
        n=o["n"],
        min_len=min_len,
        max_len=max_len,
        duration=duration,
        loudness=curve,
        hop=HOP,
        content_type=o["content_type"],
    )
    cands: list[Candidate] = []
    mode = "basic"
    reason = None
    if o["force_basic"]:
        reason = "basic mode requested"
    elif not available():
        reason = "no Gemini key or text model configured"
    elif not usage.premium_allowed():
        reason = "monthly AI budget reached"
    else:
        try:
            gem = get_client(CallContext(ctx.user_id, ctx.project_id, ctx.job_id))
            video_part, uploaded = None, None
            if o["visual"]:
                ctx.progress(0.1, "Sending video to Gemini for visual analysis")
                if ctx.params.get("url") and "youtu" in ctx.params["url"]:
                    video_part = gem.video_part(youtube_url=ctx.params["url"])
                else:
                    proxy = ctx.tmp / "proxy.mp4"  # small low-res copy keeps upload fast and under limits
                    ffmpeg.run(
                        [
                            "-i",
                            str(ingest.local_source(ctx)),
                            "-vf",
                            "scale=-2:360,fps=2",
                            "-c:v",
                            "libx264",
                            "-preset",
                            "veryfast",
                            "-crf",
                            "32",
                            "-c:a",
                            "aac",
                            "-b:a",
                            "48k",
                            "-ac",
                            "1",
                            str(proxy),
                        ],
                        what="Preview encode",
                    )
                    uploaded = gem.upload_file(proxy)
                    video_part = gem.video_part(file=uploaded)
            ctx.progress(0.3, "Finding the best moments")
            try:
                cands = gemini_moments.find(
                    gem,
                    t,
                    n=o["n"],
                    min_len=min_len,
                    max_len=max_len,
                    content_type=o["content_type"],
                    language=o["language"],
                    peaks=peaks,
                    duration=duration,
                    video_part=video_part,
                    on_progress=lambda f: ctx.progress(0.3 + 0.6 * f, "Finding the best moments"),
                )
            finally:
                if uploaded:
                    gem.delete_file(uploaded)
            mode = "ai"
        except GeminiError as e:
            reason = str(e)
            ctx.log(f"Gemini unavailable, using basic mode: {e}", "warn")
    if mode == "basic":
        ctx.log(f"Basic mode ({reason})")
        cands = fallback
    final = validate.finalize(
        cands, t, n=o["n"], min_len=min_len, max_len=max_len, duration=duration, fallback=fallback
    )
    if not final:
        raise StepFailed("No usable moments were found in this video. Try a different clip length range.")

    source_id = meta["source_id"]
    db.execute("delete from clips where project_id = %s", [ctx.project_id])
    ids = []
    for i, c in enumerate(final, start=1):
        row = db.fetch_one(
            """insert into clips (project_id, source_id, idx, start_s, end_s, title, hook_text, description, hashtags,
                                  virality_score, reason, mode, reframe, caption_style, status, filename, duration_s)
               values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s,%s) returning id""",
            [
                ctx.project_id,
                source_id,
                i,
                c.start,
                c.end,
                c.title,
                c.hook_text,
                c.description,
                c.hashtags,
                c.virality_score,
                c.reason,
                c.mode,
                o["reframe"],
                o["caption_style"],
                clip_filename(i, c.title),
                round(c.end - c.start, 3),
            ],
        )
        ids.append(str(row["id"]))
    db.execute(
        "update projects set meta = meta || %s where id = %s",
        [
            {
                "transcript_key": ctx.outputs["transcribe"]["transcript_key"],
                "source_id": source_id,
                "mode": mode,
                "options": o,
            },
            ctx.project_id,
        ],
    )
    return {"clip_ids": ids, "mode": mode, "basic_reason": reason}


def render_one(
    ctx: JobContext,
    clip: dict[str, Any],
    t: Transcript,
    *,
    hook_overlay: bool,
    progress=lambda f: None,
    reuse_base: bool = False,
) -> dict[str, Any]:
    start, end = float(clip["start_s"]), float(clip["end_s"])
    dur = round(end - start, 3)
    pid = clip["project_id"]
    base_key = f"projects/{pid}/clips/{clip['id']}/base.mp4"
    base = ctx.tmp / f"base_{clip['idx']}.mp4"
    if reuse_base and clip.get("base_key") and storage.exists(clip["base_key"]):
        ctx.fetch(clip["base_key"], base.name)
        base = ctx.tmp / "dl" / base.name
        progress(0.6)
    else:
        src = ingest.local_source(ctx) if "ingest" in ctx.outputs else _source_for_clip(ctx, clip)
        pr = ffmpeg.probe(src)
        render_base(src, pr, start, end, clip["reframe"], base, ctx.tmp, lambda f: progress(0.6 * f))
        storage.upload_file(base, base_key, "video/mp4")
    words = t.slice(start, end)
    final = ctx.tmp / clip["filename"]
    render_final(
        base,
        words,
        clip["caption_style"],
        final,
        ctx.tmp,
        duration=dur,
        hook=clip["hook_text"] if hook_overlay else None,
        on_progress=lambda f: progress(0.6 + 0.35 * f),
    )
    thumb = pick_thumbnail(final, ctx.tmp / f"thumb_{clip['idx']}.jpg", dur)
    video_key = f"projects/{pid}/clips/{clip['id']}/{clip['filename']}"
    thumb_key = f"projects/{pid}/clips/{clip['id']}/thumb.jpg"
    storage.upload_file(final, video_key, "video/mp4")
    storage.upload_file(thumb, thumb_key, "image/jpeg")
    db.execute(
        "update clips set status = 'ready', base_key = %s, video_key = %s, thumb_key = %s, duration_s = %s "
        "where id = %s",
        [base_key, video_key, thumb_key, dur, clip["id"]],
    )
    progress(1.0)
    return {"video_key": video_key, "thumb_key": thumb_key}


def _source_for_clip(ctx: JobContext, clip: dict[str, Any]):
    src = db.fetch_one("select * from sources where id = %s", [clip["source_id"]])
    if not src or src["deleted_at"] or not src["r2_key"] or not storage.exists(src["r2_key"]):
        raise StepFailed(
            "The original video was deleted after the retention period, so the cut can't be changed. "
            "Caption style can still be changed."
        )
    from pathlib import Path

    return ctx.fetch(src["r2_key"], "source" + Path(src["r2_key"]).suffix)


def step_render(ctx: JobContext) -> dict[str, Any]:
    o = _params(ctx)
    t = load_transcript(ctx)
    ids = ctx.outputs["moments"]["clip_ids"]
    clips = db.fetch_all("select * from clips where id = any(%s) order by idx", [ids])
    done = 0
    for i, c in enumerate(clips):
        ctx.check_canceled()
        if c["status"] == "ready" and c["video_key"] and storage.exists(c["video_key"]):
            done += 1
            continue  # resumed job: this clip was finished before the crash
        db.execute("update clips set status = 'rendering' where id = %s", [c["id"]])
        try:
            render_one(
                ctx,
                c,
                t,
                hook_overlay=o["hook_overlay"],
                progress=lambda f, i=i: ctx.progress(
                    (i + f) / len(clips), f"Rendering clip {i + 1} of {len(clips)}"
                ),
            )
        except Exception:
            db.execute("update clips set status = 'failed' where id = %s", [c["id"]])
            raise
        done += 1
        if i == 0:
            db.execute(
                "update projects set thumbnail_key = %s where id = %s",
                [f"projects/{ctx.project_id}/clips/{c['id']}/thumb.jpg", ctx.project_id],
            )
    return {"rendered": done}


def build(params: dict[str, Any]) -> Pipeline:
    return Pipeline(
        [
            Step("ingest", ingest.run, weight=1, label="Getting the video"),
            Step("transcribe", step_transcribe, weight=3, label="Transcribing"),
            Step("moments", step_moments, weight=1.5, label="Finding moments"),
            Step("render", step_render, weight=6, label="Rendering clips"),
        ],
        finalize=lambda ctx: {
            "clips": ctx.outputs["moments"]["clip_ids"],
            "mode": ctx.outputs["moments"]["mode"],
            "basic_reason": ctx.outputs["moments"].get("basic_reason"),
        },
    )
