"""Per-clip rendering: frame-accurate cut + 9:16 reframe + loudness (base), then captions (final)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import cv2

from ..captions.ass import build_ass
from ..captions.burn import burn
from ..captions.emoji import emoji_overlays
from ..captions.style import CaptionStyle, catalog
from ..media import ffmpeg, loudnorm
from ..media.ffmpeg import FPS, Probe
from ..transcribe.base import Word
from .reframe import detect, smooth
from .reframe import render as rf


def reframe_filter(
    src: Path,
    pr: Probe,
    start: float,
    end: float,
    mode: str,
    workdir: Path,
    on_progress: Callable[[float], None] | None = None,
) -> str:
    dur = end - start
    if mode == "blur":
        return rf.blur_filter()
    if mode == "center" or rf.is_vertical_enough(pr):
        return rf.center_filter(pr)
    w, h = pr.display_size
    crop_frac = rf.crop_width(pr) / w
    if mode == "action":
        samples = detect.motion_track(src, start, end, crop_frac)
        path = smooth.camera_path(
            samples, duration=dur, fps=FPS, crop_frac=crop_frac, dead_zone=0.18, max_speed=0.5, smooth_s=0.9
        )
    else:  # face
        samples = detect.face_track(src, start, end)
        found = sum(1 for _, v in samples if v is not None)
        if found < max(2, len(samples) * 0.15):
            # No (or very few) faces: fall back to the blurred-background fit rather than a random crop.
            return rf.blur_filter()
        path = smooth.camera_path(samples, duration=dur, fps=FPS, crop_frac=crop_frac)
    if on_progress:
        on_progress(1.0)
    return rf.dynamic_filter(pr, path, workdir / f"crop_{start:.2f}.cmd")


def render_base(
    src: Path,
    pr: Probe,
    start: float,
    end: float,
    mode: str,
    out: Path,
    workdir: Path,
    on_progress: Callable[[float], None] | None = None,
) -> Path:
    """Cut [start, end) frame-accurately (re-encode), reframe to 1080x1920@30, normalize audio to -14 LUFS."""
    dur = end - start
    p = on_progress or (lambda f: None)
    vf = reframe_filter(src, pr, start, end, mode, workdir, lambda f: p(0.25 * f))
    audio: list[str]
    if pr.has_audio:
        meas = loudnorm.measure(src, start=start, duration=dur)
        audio = [
            "-af",
            loudnorm.filter_for(meas) + ",aresample=48000",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
        ]
        amap = ["-map", "0:a:0"]
    else:  # silent source: add a silent track so every export has audio
        audio = ["-c:a", "aac", "-b:a", "128k", "-shortest"]
        amap = ["-map", "1:a"]
    inputs = ["-ss", f"{start:.3f}", "-i", str(src)]
    if not pr.has_audio:
        inputs += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    fc = f"[0:v]{vf},fps={FPS},format=yuv420p[v]"
    ffmpeg.run(
        [
            *inputs,
            "-t",
            f"{dur:.3f}",
            "-filter_complex",
            fc,
            "-map",
            "[v]",
            *amap,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-profile:v",
            "high",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(FPS),
            "-g",
            str(FPS * 2),
            *audio,
            "-movflags",
            "+faststart",
            str(out),
        ],
        duration=dur,
        on_progress=lambda f: p(0.25 + 0.75 * f),
        what="Clip render",
    )
    return out


def render_final(
    base: Path,
    words: list[Word],
    style_dict: dict | None,
    out: Path,
    workdir: Path,
    *,
    duration: float,
    hook: str | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> Path:
    style = CaptionStyle.from_dict(style_dict)
    ass = build_ass(words, style, workdir / f"{out.stem}.ass", hook=hook, hook_duration=min(3.0, duration))
    overlays = []
    if style.enabled and style.emoji:
        y = int(1920 * catalog()["positions"][style.position])
        overlays = emoji_overlays(words, style.words_per_line, y, workdir)
    return burn(base, ass, out, overlays=overlays, duration=duration, on_progress=on_progress)


def pick_thumbnail(video: Path, out: Path, duration: float) -> Path:
    """Auto-pick the sharpest frame from the first ~60% of the clip."""
    cap = cv2.VideoCapture(str(video))
    best_t, best_score = min(1.0, duration / 3), -1.0
    try:
        for i in range(10):
            t = duration * (0.05 + 0.55 * i / 9)
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, frame = cap.read()
            if not ok:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            sharp = cv2.Laplacian(gray, cv2.CV_64F).var()
            bright = gray.mean()
            score = sharp * (1.0 if 40 < bright < 220 else 0.3)
            if score > best_score:
                best_t, best_score = t, score
    finally:
        cap.release()
    return ffmpeg.thumbnail(video, out, best_t)
