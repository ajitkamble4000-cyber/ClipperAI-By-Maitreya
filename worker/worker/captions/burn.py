"""Burn ASS captions (+ emoji overlays) onto a 1080x1920 video."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..media import ffmpeg
from .emoji import Overlay
from .style import fonts_dir


def caption_filter(ass: Path) -> str:
    return f"subtitles=filename='{ffmpeg.escape_filter_path(ass)}':fontsdir='{ffmpeg.escape_filter_path(fonts_dir())}'"


def burn(
    src: Path,
    ass: Path | None,
    out: Path,
    *,
    overlays: list[Overlay] | None = None,
    duration: float,
    on_progress: Callable[[float], None] | None = None,
    audio_args: list[str] | None = None,
) -> Path:
    inputs = ["-i", str(src)]
    chain = "[0:v]"
    parts: list[str] = []
    label = "v0"
    if ass:
        parts.append(f"{chain}{caption_filter(ass)}[{label}]")
    else:
        parts.append(f"{chain}null[{label}]")
    for i, ov in enumerate(overlays or []):
        inputs += ["-loop", "1", "-t", f"{duration:.3f}", "-i", str(ov.png)]
        nxt = f"v{i + 1}"
        parts.append(
            f"[{label}][{i + 1}:v]overlay=x={ov.x}:y={ov.y}:enable='between(t,{ov.start:.3f},{ov.end:.3f})'[{nxt}]"
        )
        label = nxt
    ffmpeg.run(
        [
            *inputs,
            "-filter_complex",
            ";".join(parts),
            "-map",
            f"[{label}]",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-profile:v",
            "high",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(ffmpeg.FPS),
            *(audio_args or ["-c:a", "copy"]),
            "-t",
            f"{duration:.3f}",
            "-movflags",
            "+faststart",
            str(out),
        ],
        duration=duration,
        on_progress=on_progress,
        what="Caption render",
    )
    return out
