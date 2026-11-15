"""Filler-word and silence removal ('jump cuts') using word timestamps; captions are re-timed to match."""

from __future__ import annotations

import re
from pathlib import Path

from ..transcribe.base import Word
from . import ffmpeg

FILLERS = {"um", "umm", "uh", "uhh", "erm", "er", "hmm", "mm", "mhm", "ah", "eh"}
_NORM = re.compile(r"[^\w']+")


def is_filler(text: str) -> bool:
    return _NORM.sub("", text.lower()) in FILLERS


def _subtract(segs: list[list[float]], a: float, b: float) -> list[list[float]]:
    out: list[list[float]] = []
    for s0, s1 in segs:
        if b <= s0 or a >= s1:
            out.append([s0, s1])
            continue
        if a > s0:
            out.append([s0, a])
        if b < s1:
            out.append([b, s1])
    return out


def keep_segments(
    words: list[Word],
    duration: float,
    *,
    remove_silence: bool = True,
    remove_fillers: bool = True,
    max_gap: float = 0.45,
    pad: float = 0.12,
) -> list[tuple[float, float]]:
    """Time ranges to keep. Silence removal keeps speech (plus short padding) and drops pauses longer than
    `max_gap`; filler removal then cuts out "um/uh"-style words. With neither, the whole clip is kept."""
    if not (remove_silence or remove_fillers) or not words:
        return [(0.0, round(duration, 3))]
    segs: list[list[float]] = [[0.0, duration]]
    if remove_silence:
        spoken = [w for w in words if not (remove_fillers and is_filler(w.text))]
        if not spoken:
            return [(0.0, round(duration, 3))]
        segs = []
        for w in spoken:
            a, b = max(0.0, w.start - pad), min(duration, w.end + pad)
            if segs and a - segs[-1][1] <= max_gap:
                segs[-1][1] = max(segs[-1][1], b)
            else:
                segs.append([a, b])
        if segs[0][0] < 0.5:
            segs[0][0] = 0.0
    if remove_fillers:
        for w in words:
            if is_filler(w.text):
                segs = _subtract(segs, max(0.0, w.start - 0.03), min(duration, w.end + 0.03))
    return [(round(a, 3), round(b, 3)) for a, b in segs if b - a > 0.08]


def remap(words: list[Word], segs: list[tuple[float, float]]) -> list[Word]:
    """Move word times onto the cut timeline (words outside kept ranges are dropped)."""
    out: list[Word] = []
    offset = 0.0
    for a, b in segs:
        for w in words:
            if w.start >= a - 1e-6 and w.end <= b + 1e-6:
                out.append(Word(w.text, round(w.start - a + offset, 3), round(w.end - a + offset, 3), w.prob))
        offset += b - a
    return out


def apply(src: Path, segs: list[tuple[float, float]], out: Path) -> Path:
    expr = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in segs)
    ffmpeg.run(
        [
            "-i",
            str(src),
            "-vf",
            f"select='{expr}',setpts=N/FRAME_RATE/TB",
            "-af",
            f"aselect='{expr}',asetpts=N/SR/TB",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(ffmpeg.FPS),
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(out),
        ],
        what="Jump cuts",
    )
    return out


def saved_seconds(segs: list[tuple[float, float]], duration: float) -> float:
    return round(duration - sum(b - a for a, b in segs), 2)
