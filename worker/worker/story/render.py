"""Story render: scene motion segments (cached) -> transitions -> music/SFX mix -> captions + hook -> final MP4.

Re-rendering never regenerates images or voice; motion segments are cached per (image, duration, motion)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from studio_shared import db, storage

from ..captions.ass import AssBuilder
from ..captions.burn import caption_filter
from ..captions.style import CaptionStyle
from ..media import ffmpeg, loudnorm
from ..media.ffmpeg import FPS
from ..media.names import slugify
from ..pipeline import JobContext, Pipeline, Step, StepFailed
from ..transcribe.base import Word
from . import assets, presets
from .builtin_sfx import ensure_builtin_sfx
from .motion import image_segment, join_segments, transition_for, video_segment
from .sound import mix, pick_music, plan_sfx

TAIL = 0.7  # seconds of picture after the last word


def texts_hash(scenes: list[dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps([s["narration"].strip() for s in scenes]).encode()).hexdigest()[:16]


def _load(ctx: JobContext) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    st = db.fetch_one("select * from stories where project_id = %s", [ctx.project_id])
    scenes = db.fetch_all("select * from scenes where project_id = %s order by idx", [ctx.project_id])
    if not st or not scenes:
        raise StepFailed("The storyboard is empty.")
    missing = [s["idx"] + 1 for s in scenes if not s["image_key"] and not s["video_key"]]
    if missing:
        raise StepFailed(
            f"Scene {', '.join(map(str, missing))} has no image yet. Generate or upload images first."
        )
    if not st["narration_key"] or not st["alignment_key"]:
        raise StepFailed("Generate the voiceover first (Voice step).")
    al = json.loads(storage.get_bytes(st["alignment_key"]))
    if al.get("texts_hash") and al["texts_hash"] != texts_hash(scenes):
        raise StepFailed(
            "The narration changed after the voiceover was made. Regenerate the voice, then render."
        )
    if len(al["scenes"]) != len(scenes):
        raise StepFailed(
            "Scenes were added or removed after the voiceover was made. Regenerate the voice, then render."
        )
    return st, scenes, al


def scene_durations(al: dict[str, Any]) -> list[float]:
    spans = al["scenes"]
    durs = [max(0.8, b - a) for a, b in spans]
    durs[-1] = max(0.8, al["duration"] - spans[-1][0] + TAIL)
    return [round(d, 3) for d in durs]


def step_segments(ctx: JobContext) -> dict[str, Any]:
    st, scenes, al = _load(ctx)
    durs = scene_durations(al)
    trans = [
        transition_for(scenes[i]["camera_motion"], scenes[i + 1]["camera_motion"], st["genre"])
        for i in range(len(scenes) - 1)
    ]
    keys = []
    for i, s in enumerate(scenes):
        ctx.check_canceled()
        seg_len = durs[i] + (trans[i][1] if i < len(trans) else 0.0)
        use_video = bool(s["video_key"]) and s["use_premium"] and st["motion_mode"] == "premium"
        src_key = s["video_key"] if use_video else s["image_key"]
        h = assets.key_for(kind="segment", src=src_key, dur=round(seg_len, 2), motion=s["camera_motion"], v=2)
        cached = assets.get(h)
        if cached and storage.exists(cached):
            keys.append(cached)
        else:
            out = ctx.tmp / f"seg_{i}.mp4"
            src = ctx.fetch(src_key, f"src_{i}{Path(src_key).suffix}")

            def prog(f: float, i: int = i) -> None:
                ctx.progress((i + f) / len(scenes), f"Animating scene {i + 1} of {len(scenes)}")

            if use_video:
                video_segment(src, seg_len, out)
            else:
                image_segment(src, seg_len, s["camera_motion"], out, prog)
            key = f"assets/{h}.mp4"
            storage.upload_file(out, key, "video/mp4")
            assets.put(h, "segment", key)
            keys.append(key)
        ctx.progress((i + 1) / len(scenes), f"Animating scene {i + 1} of {len(scenes)}")
    return {"segments": keys, "durations": durs, "transitions": trans}


def step_compose(ctx: JobContext) -> dict[str, Any]:
    st, scenes, al = _load(ctx)
    o = ctx.outputs["segments"]
    durs, trans = o["durations"], [tuple(t) for t in o["transitions"]]
    total = round(sum(durs), 3)
    segs = [ctx.fetch(k, f"seg_{i}.mp4") for i, k in enumerate(o["segments"])]
    video = join_segments(
        segs, durs, trans, ctx.tmp / "video.mp4", lambda f: ctx.progress(0.6 * f, "Joining scenes")
    )

    # Audio: voice + ducked music + SFX
    ctx.progress(0.62, "Mixing audio")
    ensure_builtin_sfx(ctx.tmp)
    voice = ctx.fetch(st["narration_key"], "narration" + Path(st["narration_key"]).suffix)
    track = pick_music(st)
    music = ctx.fetch(track["r2_key"], "music" + Path(track["r2_key"]).suffix) if track else None
    starts = [sum(durs[:i]) for i in range(len(durs))]
    sfx = plan_sfx(scenes, starts, ctx.fetch, st["sfx_enabled"])
    audio = mix(
        voice, total, ctx.tmp / "mix.wav", music=music, music_volume=float(st["music_volume"]), sfx=sfx
    )

    # Captions from aligned script words + hook overlay + per-scene on-screen text
    genre = presets.genre(st["genre"])
    style = CaptionStyle.from_dict(st["caption_style"] or {"preset": genre["captions"]})
    b = AssBuilder(style)
    b.add_words([Word(**w) for w in al["words"]])
    if st["hook_overlay"] and st["hook_text"]:
        b.add_hook(st["hook_text"], min(3.0, total))
    for i, s in enumerate(scenes):
        if s["on_screen_text"].strip() and not (i == 0 and st["hook_overlay"] and st["hook_text"]):
            b.add_hook(s["on_screen_text"], min(2.5, durs[i]), start=starts[i] + 0.15, y_frac=0.3)
    ass = b.write(ctx.tmp / "captions.ass")

    ctx.progress(0.7, "Final render")
    meas = loudnorm.measure(audio)
    name = f"{slugify(st['title'] or 'story')}.mp4"
    final = ctx.tmp / name
    ffmpeg.run(
        [
            "-i",
            str(video),
            "-i",
            str(audio),
            "-filter_complex",
            f"[0:v]{caption_filter(ass)},format=yuv420p[v]",
            "-map",
            "[v]",
            "-map",
            "1:a",
            "-af",
            loudnorm.filter_for(meas) + ",aresample=48000",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "19",
            "-profile:v",
            "high",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(FPS),
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-t",
            f"{total:.3f}",
            "-movflags",
            "+faststart",
            str(final),
        ],
        duration=total,
        on_progress=lambda f: ctx.progress(0.7 + 0.28 * f, "Final render"),
        what="Final render",
    )
    thumb = ffmpeg.thumbnail(final, ctx.tmp / "thumb.jpg", min(total * 0.15, 2.0))
    rev = ctx.job_id[:8]
    key = f"projects/{ctx.project_id}/renders/{rev}/{name}"
    tkey = f"projects/{ctx.project_id}/renders/{rev}/thumb.jpg"
    storage.upload_file(final, key, "video/mp4")
    storage.upload_file(thumb, tkey, "image/jpeg")
    db.execute(
        "update stories set render_key = %s, thumb_key = %s where project_id = %s",
        [key, tkey, ctx.project_id],
    )
    db.execute("update projects set thumbnail_key = %s where id = %s", [tkey, ctx.project_id])
    return {
        "render_key": key,
        "thumb_key": tkey,
        "duration": total,
        "music": track["name"] if track else None,
        "sfx": len(sfx),
        "filename": name,
    }


def build_render(params: dict) -> Pipeline:
    return Pipeline(
        [
            Step("segments", step_segments, weight=3, label="Animating scenes"),
            Step("compose", step_compose, weight=2, label="Composing"),
        ],
        finalize=lambda c: c.outputs["compose"],
    )
