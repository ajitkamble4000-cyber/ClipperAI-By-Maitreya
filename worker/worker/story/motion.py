"""Standard motion (ffmpeg only): Ken Burns zoom/pan per scene, shake on dramatic beats, drift on pans,
and crossfade / whip transitions between scenes."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..media import ffmpeg
from ..media.ffmpeg import FPS, OUT_H, OUT_W

UPSCALE = 3  # zoompan on a 3x image avoids the 1-pixel stair-step jitter of plain zoompan
EASE = "(({p})*({p})*(3-2*({p})))"


def motion_expr(motion: str, frames: int) -> tuple[str, str, str]:
    p = f"(on/{max(1, frames - 1)})"
    e = EASE.format(p=p)
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    if motion == "zoom-in":
        return f"1+0.20*{e}", cx, cy
    if motion == "zoom-out":
        return f"1.20-0.20*{e}", cx, cy
    if motion == "pan-left":  # camera travels left; slight push-in gives a parallax-like drift
        return f"1.14+0.04*{e}", f"(iw-iw/zoom)*(1-{e})", cy
    if motion == "pan-right":
        return f"1.14+0.04*{e}", f"(iw-iw/zoom)*{e}", cy
    if motion == "shake":  # hard hit at the start, decaying
        amp = f"(iw*0.010*exp(-3*{p}))"
        return (f"1.10+0.04*{e}", f"{cx}+{amp}*sin(on*2.3)", f"{cy}+{amp}*cos(on*1.9)")
    return f"1+0.04*{e}", cx, cy  # static: barely-there push so the frame never looks frozen


def image_segment(
    image: Path, duration: float, motion: str, out: Path, on_progress: Callable[[float], None] | None = None
) -> Path:
    frames = max(2, round(duration * FPS))
    z, x, y = motion_expr(motion, frames)
    vf = (
        f"scale={OUT_W * UPSCALE}:{OUT_H * UPSCALE}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={OUT_W * UPSCALE}:{OUT_H * UPSCALE},"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={OUT_W}x{OUT_H}:fps={FPS},format=yuv420p"
    )
    ffmpeg.run(
        [
            "-i",
            str(image),
            "-vf",
            vf,
            "-frames:v",
            str(frames),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "16",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(FPS),
            str(out),
        ],
        duration=duration,
        on_progress=on_progress,
        what="Scene motion",
    )
    return out


def video_segment(video: Path, duration: float, out: Path) -> Path:
    """Fit a (Veo) clip to the scene: cover-crop to 9:16, slow down a little if short, then hold the last frame."""
    pr = ffmpeg.probe(video)
    speed = 1.0
    if pr.duration < duration:
        speed = max(pr.duration / duration, 1 / 1.5)
    pad = max(0.0, duration - pr.duration / speed)
    vf = (
        f"setpts=PTS/{speed:.4f},scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,crop={OUT_W}:{OUT_H},"
        f"fps={FPS},tpad=stop_mode=clone:stop_duration={pad + 0.1:.3f},format=yuv420p"
    )
    ffmpeg.run(
        [
            "-i",
            str(video),
            "-an",
            "-vf",
            vf,
            "-t",
            f"{duration:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "16",
            "-r",
            str(FPS),
            str(out),
        ],
        what="Scene video fit",
    )
    return out


def transition_for(prev_motion: str, next_motion: str, genre: str) -> tuple[str, float]:
    if next_motion == "shake" or genre in ("funny", "facts"):
        return "smoothleft", 0.25  # whip
    return "fade", 0.4  # crossfade


def join_segments(
    segs: list[Path],
    scene_durs: list[float],
    transitions: list[tuple[str, float]],
    out: Path,
    on_progress: Callable[[float], None] | None = None,
) -> Path:
    """Segments i<last are (scene_dur + T_i) long, so each transition starts exactly at the narration boundary."""
    if len(segs) == 1:
        ffmpeg.run(["-i", str(segs[0]), "-c", "copy", str(out)], what="Join")
        return out
    inputs: list[str] = []
    for s in segs:
        inputs += ["-i", str(s)]
    parts, label, offset = [], "[0:v]", 0.0
    for i in range(1, len(segs)):
        kind, t = transitions[i - 1]
        offset += scene_durs[i - 1]
        nxt = f"[x{i}]"
        parts.append(f"{label}[{i}:v]xfade=transition={kind}:duration={t:.3f}:offset={offset:.3f}{nxt}")
        label = nxt
    total = sum(scene_durs)
    ffmpeg.run(
        [
            *inputs,
            "-filter_complex",
            ";".join(parts),
            "-map",
            label,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "17",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(FPS),
            "-t",
            f"{total:.3f}",
            str(out),
        ],
        duration=total,
        on_progress=on_progress,
        what="Transitions",
    )
    return out
