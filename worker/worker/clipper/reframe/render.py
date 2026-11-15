"""Build the ffmpeg video filter for each reframe mode (output 1080x1920)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ...media import ffmpeg
from ...media.ffmpeg import FPS, OUT_H, OUT_W, Probe

MODES = ("face", "action", "center", "blur")


def crop_width(p: Probe) -> int:
    w, h = p.display_size
    cw = int(round(h * 9 / 16)) // 2 * 2
    return min(cw, w // 2 * 2)


def is_vertical_enough(p: Probe) -> bool:
    w, h = p.display_size
    return w / max(1, h) <= 9 / 16 + 0.02


def blur_filter() -> str:
    return (
        f"split=2[bgsrc][fgsrc];"
        f"[bgsrc]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,crop={OUT_W}:{OUT_H},"
        f"boxblur=luma_radius=40:luma_power=3,eq=brightness=-0.08:saturation=1.1[bg];"
        f"[fgsrc]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1"
    )


def center_filter(p: Probe) -> str:
    if is_vertical_enough(p):
        return f"scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,crop={OUT_W}:{OUT_H},setsar=1"
    cw = crop_width(p)
    _, h = p.display_size
    return f"crop={cw}:{h}:(iw-{cw})/2:0,scale={OUT_W}:{OUT_H},setsar=1"


def dynamic_filter(p: Probe, path_centers: np.ndarray, cmd_file: Path) -> str:
    """Crop that follows `path_centers` (per output frame, 0..1) using sendcmd."""
    if is_vertical_enough(p):
        return center_filter(p)
    w, h = p.display_size
    cw = crop_width(p)
    xs = np.clip(np.round(path_centers * w - cw / 2), 0, w - cw).astype(int)
    lines = []
    last = None
    for i, x in enumerate(xs):
        if x != last:
            lines.append(f"{i / FPS:.4f} crop@rf x {x};")
            last = x
    cmd_file.write_text("\n".join(lines) + "\n")
    return (
        f"fps={FPS},sendcmd=f='{ffmpeg.escape_filter_path(cmd_file)}',"
        f"crop@rf=w={cw}:h={h}:x={xs[0]}:y=0,scale={OUT_W}:{OUT_H},setsar=1"
    )
