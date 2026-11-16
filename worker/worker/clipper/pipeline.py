"""Clipper job: ingest -> transcribe -> find moments (or the whole video) -> render clips.

Modes: "clips" finds the best moments; "captions" captions the whole video; "auto" captions short videos whole
(and refunds the difference in tokens) and clips long ones. Every clip can be rendered in 9:16, 1:1, 4:5 or
16:9, with jump cuts, translated captions, keyword emphasis, a progress bar, the brand kit and the free-plan
watermark."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from studio_shared import db, storage, tokens, usage
from studio_shared.gemini import AIError, CallContext, available, get_client

from ..captions.ass import ASPECTS, canvas_for
from ..media import audio, ffmpeg, jumpcut
from ..media.names import clip_filename
from ..media.overlays import OverlayOptions
from ..pipeline import JobContext, Pipeline, Step, StepFailed
from ..transcribe import cache as tcache
from ..transcribe.base import Transcript
from ..transcribe.faster_whisper_impl import transcriber_from_settings
from . import ingest, whole
from .moments import basic, gemini_moments, validate
from .moments.schema import Candidate
from .render import pick_thumbnail, render_base, render_final

HOP = 0.5
CAPTIONS_MAX_S = 15 * 60
RENDER_OPT_KEYS = (
    "watermark",
    "progress_bar",
    "brand",
    "keyword_emphasis",
    "emphasis_words",
    "remove_silence",
    "remove_fillers",
    "translate_to",
    "music",
)


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
        "mode": p.get("mode") if p.get("mode") in ("auto", "clips", "captions") else "clips",
        "aspect": p.get("aspect") if p.get("aspect") in ASPECTS else "9:16",
        "auto_whole_max_s": int(max(15, min(180, p.get("auto_whole_max_s", 90)))),
    }


def _meta_options(ctx: JobContext, o: dict[str, Any]) -> dict[str, Any]:
    """Options shown on the project page (no brand details)."""
    extra = ("translate_to", "remove_silence", "remove_fillers", "keyword_emphasis", "progress_bar")
    return {**o, **{k: ctx.params[k] for k in extra if ctx.params.get(k)}}


def render_opts(params: dict[str, Any]) -> dict[str, Any]:
    """Per-clip render options stored on the clip, so re-renders look the same."""
    return {k: params[k] for k in RENDER_OPT_KEYS if params.get(k)}


# ---------------------------------------------------------------- steps
def step_transcribe(ctx: JobContext) -> dict[str, Any]:
    src = ingest.local_source(ctx)
    meta = ctx.outputs["ingest"]
    wav = ffmpeg.extract_audio(src, ctx.tmp / "audio.wav") if meta.get("has_audio", True) else None
    loud_key = ctx.job_key("loudness.json")
    curve = audio.loudness_curve(wav, HOP) if wav else np.zeros(0)
    storage.put_bytes(loud_key, json.dumps([round(float(x), 2) for x in curve]).encode(), "application/json")

    tr = transcriber_from_settings()
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
    if o["mode"] == "captions" and duration > CAPTIONS_MAX_S:
        raise StepFailed(
            f"Captions mode works on videos up to {CAPTIONS_MAX_S // 60} minutes (this one is "
            f"{duration / 60:.0f}). Use Clips mode for long videos. Your tokens were refunded."
        )
    if o["mode"] == "captions" or (o["mode"] == "auto" and duration <= o["auto_whole_max_s"]):
        return _whole(ctx, o, t, meta, duration)
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
            whole_video = getattr(gem, "supports_video_input", lambda: True)()
            if o["visual"] and not whole_video:
                # Providers without video input look at sampled frames instead (any vision model).
                ctx.progress(0.1, "Sampling frames for visual analysis")
                from studio_shared.ai.client import ImageParts

                from ..media.frames import sample_jpegs

                video_part = ImageParts(sample_jpegs(ingest.local_source(ctx), float(meta["duration"])))
            elif o["visual"]:
                ctx.progress(0.1, "Sending video to the AI for visual analysis")
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
        except AIError as e:
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
                                  virality_score, reason, mode, reframe, caption_style, status, filename, duration_s,
                                  aspect, render_opts)
               values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s,%s,%s,%s) returning id""",
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
                o["aspect"],
                db.jsonb(render_opts(ctx.params)),
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
                "options": _meta_options(ctx, o),
            },
            ctx.project_id,
        ],
    )
    return {"clip_ids": ids, "mode": mode, "basic_reason": reason}


def _whole(ctx: JobContext, o: dict[str, Any], t: Transcript, meta: dict[str, Any], duration: float) -> dict:
    """One clip covering the whole video (captions tool, or a short video in auto mode)."""
    if o["mode"] == "auto":
        tk = ctx.params.get("_tokens") or {}
        whole_cost, _ = tokens.quote("clip", {**(tk.get("params") or {}), "mode": "captions"})
        diff = int(tk.get("cost") or 0) - whole_cost
        if diff > 0:
            back = tokens.partial_refund(ctx.job_id, diff, "auto: short video captioned whole")
            if back:
                ctx.log(f"Short video: captioned whole, {back} tokens returned")
    info = None
    reason = None
    if available():
        try:
            gem = get_client(CallContext(ctx.user_id, ctx.project_id, ctx.job_id))
            info = whole.describe(gem, t, source_title=meta.get("title"), language=None)
        except AIError as e:
            reason = str(e)
            ctx.log(f"AI title unavailable: {e}", "warn")
    info = info or whole.basic(t, meta.get("title"))
    db.execute("delete from clips where project_id = %s", [ctx.project_id])
    row = db.fetch_one(
        """insert into clips (project_id, source_id, idx, start_s, end_s, title, hook_text, description, hashtags,
                              virality_score, reason, mode, reframe, caption_style, status, filename, duration_s,
                              aspect, render_opts)
           values (%s,%s,1,0,%s,%s,%s,%s,%s,0,%s,'whole',%s,%s,'pending',%s,%s,%s,%s) returning id""",
        [
            ctx.project_id,
            meta["source_id"],
            round(duration, 3),
            info.title,
            info.hook_text,
            info.description,
            info.hashtags,
            "Whole video with captions",
            o["reframe"],
            o["caption_style"],
            clip_filename(1, info.title),
            round(duration, 3),
            o["aspect"],
            db.jsonb(render_opts(ctx.params)),
        ],
    )
    # Uploads only have a filename as their title: prefer the AI title. Links keep the source's real title.
    from_upload = bool(ctx.params.get("upload_id"))
    db.execute(
        "update projects set meta = meta || %s, title = case when title in ('Untitled', 'Captioned video', "
        "'Quick video', '') or (%s and title = %s) then %s else title end where id = %s",
        [
            {
                "transcript_key": ctx.outputs["transcribe"]["transcript_key"],
                "source_id": meta["source_id"],
                "mode": "whole",
                "options": _meta_options(ctx, o),
            },
            from_upload,
            meta.get("title") or "",
            info.title[:120],
            ctx.project_id,
        ],
    )
    return {"clip_ids": [str(row["id"])], "mode": "whole", "basic_reason": reason}


def _translate(ctx: JobContext, words: list, target: str, source_language: str | None) -> list:
    from ..captions.translate import translate_words

    if not words:
        return words
    try:
        gem = get_client(CallContext(ctx.user_id, ctx.project_id, ctx.job_id))
        return translate_words(words, target, gem, source_language=source_language)
    except AIError as e:
        ctx.log(f"Translation unavailable, keeping the original captions: {e}", "warn")
        back = tokens.partial_refund(ctx.job_id, tokens.price("translation"), "translation unavailable")
        if back:
            ctx.log(f"{back} translation tokens returned")
        return words


def _words_json(words: list) -> bytes:
    return json.dumps(
        [{"text": w.text, "start": round(w.start, 3), "end": round(w.end, 3)} for w in words]
    ).encode()


def render_one(
    ctx: JobContext,
    clip: dict[str, Any],
    t: Transcript,
    *,
    hook_overlay: bool,
    progress=lambda f: None,
    reuse_base: bool = False,
) -> dict[str, Any]:
    from ..transcribe.base import Word

    start, end = float(clip["start_s"]), float(clip["end_s"])
    dur = round(end - start, 3)
    pid = clip["project_id"]
    ro = clip.get("render_opts") or {}
    canvas = canvas_for(clip.get("aspect"))
    base_key = f"projects/{pid}/clips/{clip['id']}/base.mp4"
    base = ctx.tmp / f"base_{clip['idx']}.mp4"
    words: list[Word] | None = None
    if reuse_base and clip.get("base_key") and storage.exists(clip["base_key"]):
        ctx.fetch(clip["base_key"], base.name)
        base = ctx.tmp / "dl" / base.name
        if clip.get("duration_s"):
            dur = float(clip["duration_s"])  # jump cuts may have shortened the base
        if clip.get("words_key") and storage.exists(clip["words_key"]):
            words = [
                Word(w["text"], w["start"], w["end"])
                for w in json.loads(storage.get_bytes(clip["words_key"]))
            ]
        progress(0.6)
    else:
        src = ingest.local_source(ctx) if "ingest" in ctx.outputs else _source_for_clip(ctx, clip)
        pr = ffmpeg.probe(src)
        render_base(
            src,
            pr,
            start,
            end,
            clip["reframe"],
            base,
            ctx.tmp,
            lambda f: progress(0.5 * f),
            size=(canvas.w, canvas.h),
        )
        words = t.slice(start, end)
        if ro.get("remove_silence") or ro.get("remove_fillers"):
            segs = jumpcut.keep_segments(
                words,
                dur,
                remove_silence=bool(ro.get("remove_silence")),
                remove_fillers=bool(ro.get("remove_fillers")),
            )
            if jumpcut.saved_seconds(segs, dur) >= 0.3:
                cut = ctx.tmp / f"cut_{clip['idx']}.mp4"
                jumpcut.apply(base, segs, cut)
                base = cut
                words = jumpcut.remap(words, segs)
                dur = round(sum(b - a for a, b in segs), 3)
        progress(0.55)
        if ro.get("translate_to"):
            words = _translate(ctx, words, ro["translate_to"], t.language)
        storage.upload_file(base, base_key, "video/mp4")
    if words is None:
        words = t.slice(start, end)
    progress(0.6)
    if (ro.get("music") or {}).get("mood", "none") != "none":
        from .music import add_music

        proj = db.fetch_one("select meta from projects where id = %s", [pid]) or {}
        content_type = ((proj.get("meta") or {}).get("options") or {}).get("content_type", "other")
        base = add_music(
            base,
            dur,
            ro["music"],
            content_type=content_type,
            seed=str(clip["id"]),
            tmp=ctx.tmp,
            fetch=ctx.fetch,
        )
    brand = OverlayOptions.from_params(ro, lambda k: ctx.fetch(k, "brand_logo" + Path(k).suffix.lower()))
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
        canvas=canvas,
        emphasis=bool(ro.get("keyword_emphasis")),
        emphasis_words=ro.get("emphasis_words"),
        brand=brand,
    )
    thumb = pick_thumbnail(final, ctx.tmp / f"thumb_{clip['idx']}.jpg", dur)
    # A fresh key per render so browsers never show a cached old version after a re-render.
    rev = ctx.job_id[:8]
    video_key = f"projects/{pid}/clips/{clip['id']}/{rev}/{clip['filename']}"
    thumb_key = f"projects/{pid}/clips/{clip['id']}/{rev}/thumb.jpg"
    words_key = f"projects/{pid}/clips/{clip['id']}/{rev}/words.json"
    storage.upload_file(final, video_key, "video/mp4")
    storage.upload_file(thumb, thumb_key, "image/jpeg")
    storage.put_bytes(words_key, _words_json(words), "application/json")
    for old in (clip.get("video_key"), clip.get("thumb_key"), clip.get("words_key")):
        if old and old not in (video_key, thumb_key, words_key):
            try:
                storage.delete(old)
            except Exception:  # noqa: BLE001
                pass
    language = ro.get("translate_to") or t.language
    db.execute(
        "update clips set status = 'ready', base_key = %s, video_key = %s, thumb_key = %s, words_key = %s, "
        "duration_s = %s, language = %s where id = %s",
        [base_key, video_key, thumb_key, words_key, dur, language, clip["id"]],
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
                "update projects set thumbnail_key = (select thumb_key from clips where id = %s) where id = %s",
                [c["id"], ctx.project_id],
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
