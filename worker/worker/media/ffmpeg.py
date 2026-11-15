"""ffmpeg / ffprobe wrappers with progress reporting and readable errors."""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..pipeline import StepFailed

OUT_W, OUT_H, FPS = 1080, 1920, 30


@dataclass
class Probe:
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool
    has_video: bool
    rotation: int = 0
    video_codec: str | None = None
    audio_codec: str | None = None
    sample_rate: int | None = None

    @property
    def display_size(self) -> tuple[int, int]:
        return (self.height, self.width) if self.rotation in (90, 270) else (self.width, self.height)


def probe(path: Path | str) -> Probe:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        ).stdout
    except subprocess.CalledProcessError as e:
        raise StepFailed(f"This file could not be read as a video ({e.stderr.strip()[:200]})") from e
    data = json.loads(out)
    v = next(
        (
            s
            for s in data.get("streams", [])
            if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")
        ),
        None,
    )
    a = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    fps = 0.0
    if v:
        num, _, den = (v.get("avg_frame_rate") or v.get("r_frame_rate") or "0/1").partition("/")
        fps = float(num) / float(den or 1) if float(den or 1) else 0.0
    rot = 0
    if v:
        rot = int(v.get("tags", {}).get("rotate", 0) or 0)
        for sd in v.get("side_data_list", []) or []:
            if "rotation" in sd:
                rot = int(sd["rotation"])
        rot %= 360
    dur = float(data.get("format", {}).get("duration") or (v or a or {}).get("duration") or 0)
    return Probe(
        duration=dur,
        width=int(v["width"]) if v else 0,
        height=int(v["height"]) if v else 0,
        fps=round(fps, 3),
        has_audio=a is not None,
        has_video=v is not None,
        rotation=rot,
        video_codec=v.get("codec_name") if v else None,
        audio_codec=a.get("codec_name") if a else None,
        sample_rate=int(a["sample_rate"]) if a and a.get("sample_rate") else None,
    )


_TIME = re.compile(r"out_time_us=(\d+)")


def run(
    args: list[str],
    *,
    duration: float | None = None,
    on_progress: Callable[[float], None] | None = None,
    what: str = "ffmpeg",
    timeout: float | None = None,
) -> None:
    """Run ffmpeg. `duration` (seconds of output) lets us report 0..1 progress."""
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-progress", "pipe:1", *args]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert proc.stdout and proc.stderr
    try:
        for line in proc.stdout:
            if on_progress and duration:
                m = _TIME.match(line.strip())
                if m:
                    on_progress(min(1.0, int(m.group(1)) / 1e6 / duration))
        err = proc.stderr.read()
        rc = proc.wait(timeout=timeout)
    except BaseException:
        proc.kill()
        raise
    if rc != 0:
        raise StepFailed(f"{what} failed: {err.strip()[-600:] or f'exit code {rc}'}")


def extract_audio(
    src: Path, dst: Path, *, rate: int = 16000, start: float | None = None, dur: float | None = None
) -> Path:
    args: list[str] = []
    if start is not None:
        args += ["-ss", f"{start:.3f}"]
    args += ["-i", str(src)]
    if dur is not None:
        args += ["-t", f"{dur:.3f}"]
    run([*args, "-vn", "-ac", "1", "-ar", str(rate), "-c:a", "pcm_s16le", str(dst)], what="Audio extraction")
    return dst


def thumbnail(src: Path, dst: Path, at: float) -> Path:
    run(
        ["-ss", f"{max(0.0, at):.3f}", "-i", str(src), "-frames:v", "1", "-q:v", "3", str(dst)],
        what="Thumbnail",
    )
    return dst


def escape_filter_path(p: Path | str) -> str:
    """Escape a path for use inside an ffmpeg filter argument (subtitles=..., sendcmd=...)."""
    s = str(p).replace("\\", "/")
    return (
        s.replace(":", r"\:").replace("'", r"\'").replace(",", r"\,").replace("[", r"\[").replace("]", r"\]")
    )
