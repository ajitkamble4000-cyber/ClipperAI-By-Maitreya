"""Build the ffmpeg video filter for each reframe mode, for any output size (default 1080x1920)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ...media import ffmpeg
from ...media.ffmpeg import FPS, OUT_H, OUT_W, Probe

MODES = ("face", "action", "center", "blur", "split")
Size = tuple[int, int]
VERTICAL: Size = (OUT_W, OUT_H)


def _aspect(size: Size) -> float:
    return size[0] / size[1]


def crop_width(p: Probe, size: Size = VERTICAL) -> int:
    """Width of the moving crop window in source pixels (full source height, output aspect)."""
    w, h = p.display_size
    cw = int(round(h * _aspect(size))) // 2 * 2
    return min(cw, w // 2 * 2)


def fits(p: Probe, size: Size = VERTICAL) -> bool:
    """Source is no wider than the output aspect: nothing to track, just scale and trim the edges."""
    w, h = p.display_size
    return w / max(1, h) <= _aspect(size) + 0.02


def is_vertical_enough(p: Probe) -> bool:  # kept for callers/tests written for 9:16
    return fits(p, VERTICAL)


def much_narrower(p: Probe, size: Size = VERTICAL) -> bool:
    """Source is a lot narrower than the output (e.g. a vertical phone video into 16:9): blur-fill, don't crop."""
    w, h = p.display_size
    return w / max(1, h) < _aspect(size) * 0.8


def blur_filter(size: Size = VERTICAL) -> str:
    ow, oh = size
    return (
        f"split=2[bgsrc][fgsrc];"
        f"[bgsrc]scale={ow}:{oh}:force_original_aspect_ratio=increase,crop={ow}:{oh},"
        f"boxblur=luma_radius=40:luma_power=3,eq=brightness=-0.08:saturation=1.1[bg];"
        f"[fgsrc]scale={ow}:{oh}:force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1"
    )


def center_filter(p: Probe, size: Size = VERTICAL) -> str:
    ow, oh = size
    if fits(p, size):
        if much_narrower(p, size):
            return blur_filter(size)
        return f"scale={ow}:{oh}:force_original_aspect_ratio=increase,crop={ow}:{oh},setsar=1"
    cw = crop_width(p, size)
    _, h = p.display_size
    return f"crop={cw}:{h}:(iw-{cw})/2:0,scale={ow}:{oh},setsar=1"


def dynamic_filter(p: Probe, path_centers: np.ndarray, cmd_file: Path, size: Size = VERTICAL) -> str:
    """Crop that follows `path_centers` (per output frame, 0..1) using sendcmd."""
    if fits(p, size):
        return center_filter(p, size)
    ow, oh = size
    w, h = p.display_size
    cw = crop_width(p, size)
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
        f"crop@rf=w={cw}:h={h}:x={xs[0]}:y=0,scale={ow}:{oh},setsar=1"
    )


def split_filter(p: Probe, speakers, size: Size = VERTICAL) -> str:
    """Two speakers, one panel each: stacked top/bottom for tall formats, side by side for 16:9."""
    ow, oh = size
    w, h = p.display_size
    stacked = oh >= ow
    pw, ph = (ow, oh // 2) if stacked else (ow // 2, oh)
    aspect = pw / ph
    panels = []
    for sp in speakers:
        # Frame the face in the upper part of its panel, with room around it.
        ch = min(h, max(int(sp.size * h * 3.2), int(h * 0.45)))
        cw = min(w // 2 * 2, int(ch * aspect) // 2 * 2)
        ch = min(h, int(cw / aspect)) // 2 * 2
        x = int(min(max(sp.cx * w - cw / 2, 0), w - cw))
        y = int(min(max(sp.cy * h - ch * 0.42, 0), h - ch))
        panels.append((cw, ch, x, y))
    (c1, c2) = panels
    stack = "vstack" if stacked else "hstack"
    return (
        f"split=2[spa][spb];"
        f"[spa]crop={c1[0]}:{c1[1]}:{c1[2]}:{c1[3]},scale={pw}:{ph},setsar=1[sp1];"
        f"[spb]crop={c2[0]}:{c2[1]}:{c2[2]}:{c2[3]},scale={pw}:{ph},setsar=1[sp2];"
        f"[sp1][sp2]{stack}=inputs=2,setsar=1"
    )
