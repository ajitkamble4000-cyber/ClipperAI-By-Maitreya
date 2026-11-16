"""More ways out: MP3 audio and a GIF preview of a clip, and compilations (several clips joined into one video)."""

from __future__ import annotations

from typing import Any

from studio_shared import db, storage

from ..media import ffmpeg, loudnorm
from ..media.names import slugify
from ..pipeline import JobContext, Pipeline, Step, StepFailed


def _clip(clip_id: str) -> dict[str, Any]:
    c = db.fetch_one("select * from clips where id = %s", [clip_id])
    if not c or c["status"] != "ready" or not c["video_key"]:
        raise StepFailed("The clip isn't ready yet.")
    return c


def step_export(ctx: JobContext) -> dict[str, Any]:
    c = _clip(ctx.params["clip_id"])
    fmt = ctx.params.get("format")
    src = ctx.fetch(c["video_key"], "clip.mp4")
    base = (c["filename"] or "clip.mp4").rsplit(".", 1)[0]
    if fmt == "mp3":
        out = ctx.tmp / f"{base}.mp3"
        ffmpeg.run(["-i", str(src), "-vn", "-c:a", "libmp3lame", "-b:a", "192k", str(out)], what="MP3 export")
        mime = "audio/mpeg"
    elif fmt == "gif":
        out = ctx.tmp / f"{base}.gif"
        dur = min(6.0, float(c["duration_s"] or 6))
        ffmpeg.run(
            [
                "-t",
                f"{dur:.2f}",
                "-i",
                str(src),
                "-filter_complex",
                "fps=12,scale=360:-2:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer",
                "-loop",
                "0",
                str(out),
            ],
            what="GIF export",
        )
        mime = "image/gif"
    else:
        raise StepFailed("Unknown export format")
    key = f"projects/{c['project_id']}/clips/{c['id']}/exports/{ctx.job_id[:8]}/{out.name}"
    storage.upload_file(out, key, mime)
    return {"key": key, "filename": out.name, "format": fmt}


def step_compile(ctx: JobContext) -> dict[str, Any]:
    ids = [str(x) for x in ctx.params.get("clip_ids") or []]
    rows = {str(r["id"]): r for r in db.fetch_all("select * from clips where id = any(%s::uuid[])", [ids])}
    clips = [rows[i] for i in ids if i in rows]
    if len(clips) < 2:
        raise StepFailed("Pick at least two finished clips.")
    if any(c["status"] != "ready" or not c["video_key"] for c in clips):
        raise StepFailed("All clips must be finished first.")
    if len({c.get("aspect") or "9:16" for c in clips}) > 1:
        raise StepFailed("All clips need the same format (e.g. all 9:16) to be joined.")
    fade = ctx.params.get("transition") == "fade"
    files, durs = [], []
    for i, c in enumerate(clips):
        ctx.check_canceled()
        files.append(ctx.fetch(c["video_key"], f"part_{i}.mp4"))
        durs.append(ffmpeg.probe(files[-1]).duration)
        ctx.progress(0.3 * (i + 1) / len(clips), "Collecting clips")
    pr = ffmpeg.probe(files[0])
    w, h = pr.display_size
    inputs: list[str] = []
    parts: list[str] = []
    for i, f in enumerate(files):
        inputs += ["-i", str(f)]
        parts.append(
            f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,"
            f"fps={ffmpeg.FPS},format=yuv420p,setsar=1[v{i}]"
        )
        parts.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo[a{i}]")
    if fade:
        d = 0.4
        vlabel, alabel, offset = "[v0]", "[a0]", 0.0
        for i in range(1, len(files)):
            offset += durs[i - 1] - d
            parts.append(f"{vlabel}[v{i}]xfade=transition=fade:duration={d}:offset={offset:.3f}[vx{i}]")
            parts.append(f"{alabel}[a{i}]acrossfade=d={d}[ax{i}]")
            vlabel, alabel = f"[vx{i}]", f"[ax{i}]"
        total = sum(durs) - d * (len(files) - 1)
    else:
        parts.append(
            "".join(f"[v{i}][a{i}]" for i in range(len(files))) + f"concat=n={len(files)}:v=1:a=1[vx][ax]"
        )
        vlabel, alabel = "[vx]", "[ax]"
        total = sum(durs)
    title = (ctx.params.get("title") or "compilation").strip()[:80]
    out = ctx.tmp / f"{slugify(title) or 'compilation'}.mp4"
    joined = ctx.tmp / "joined.mp4"
    ffmpeg.run(
        [
            *inputs,
            "-filter_complex",
            ";".join(parts),
            "-map",
            vlabel,
            "-map",
            alabel,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "19",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(joined),
        ],
        duration=total,
        on_progress=lambda f: ctx.progress(0.3 + 0.55 * f, "Joining clips"),
        what="Compilation",
    )
    meas = loudnorm.measure(joined)
    ffmpeg.run(
        [
            "-i",
            str(joined),
            "-c:v",
            "copy",
            "-af",
            loudnorm.filter_for(meas),
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
            str(out),
        ],
        what="Loudness",
    )
    key = f"projects/{ctx.project_id}/exports/{ctx.job_id[:8]}/{out.name}"
    storage.upload_file(out, key, "video/mp4")
    return {"key": key, "filename": out.name, "clips": len(clips), "duration": round(total, 2)}


def build_export(params: dict) -> Pipeline:
    return Pipeline(
        [Step("export", step_export, label="Exporting")], finalize=lambda ctx: ctx.outputs["export"]
    )


def build_compile(params: dict) -> Pipeline:
    return Pipeline(
        [Step("compile", step_compile, label="Making the compilation")],
        finalize=lambda ctx: ctx.outputs["compile"],
    )
