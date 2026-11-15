"""Align recognized words (whisper on the voiceover) to the known script words.

Captions use the SCRIPT spelling with the AUDIO timing; scene boundaries come from where each scene's
first and last script word were spoken."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from ..transcribe.base import Word

_NORM = re.compile(r"[^\w]+", re.U)


def norm(w: str) -> str:
    return _NORM.sub("", w.lower())


def script_words(scene_texts: list[str]) -> tuple[list[str], list[int]]:
    words, owner = [], []
    for i, t in enumerate(scene_texts):
        for w in t.split():
            words.append(w)
            owner.append(i)
    return words, owner


@dataclass
class Alignment:
    words: list[Word]  # script words with audio times
    scenes: list[tuple[float, float]]  # per scene (start, end) in the narration audio
    matched_ratio: float


def align(scene_texts: list[str], heard: list[Word], audio_duration: float) -> Alignment:
    sw, owner = script_words(scene_texts)
    if not sw:
        return Alignment([], [(0.0, audio_duration)] * len(scene_texts), 0.0)
    a = [norm(w) for w in sw]
    b = [norm(w.text) for w in heard]
    times: list[tuple[float, float] | None] = [None] * len(sw)
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    matched = 0
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            hw = heard[blk.b + k]
            times[blk.a + k] = (hw.start, hw.end)
            matched += 1
    # Words in replaced/inserted regions: spread them over the heard words of the same region.
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("replace", "delete") and i2 > i1:
            if tag == "replace" and j2 > j1:
                t0, t1 = heard[j1].start, heard[j2 - 1].end
            else:
                prev = next((times[k] for k in range(i1 - 1, -1, -1) if times[k]), None)
                nxt = next((times[k] for k in range(i2, len(sw)) if times[k]), None)
                t0 = prev[1] if prev else 0.0
                t1 = nxt[0] if nxt else (t0 + 0.3 * (i2 - i1))
            step = max(0.05, (t1 - t0) / (i2 - i1))
            for n, k in enumerate(range(i1, i2)):
                times[k] = (t0 + n * step, t0 + (n + 1) * step)
    for k, t in enumerate(times):
        if t is None:  # should not happen, but keep monotonic
            prev = times[k - 1] if k else (0.0, 0.0)
            times[k] = (prev[1], prev[1] + 0.2)
    # Monotonic, non-overlapping
    out: list[Word] = []
    last_end = 0.0
    for w, (s, e) in zip(sw, times, strict=True):
        s = max(s, last_end)
        e = max(e, s + 0.05)
        out.append(Word(w, round(s, 3), round(e, 3)))
        last_end = e
    # Scene spans: from the first word's start to the next scene's first word start (pauses included).
    n = len(scene_texts)
    firsts: list[float | None] = [None] * n
    lasts: list[float | None] = [None] * n
    for w, o in zip(out, owner, strict=True):
        if firsts[o] is None:
            firsts[o] = w.start
        lasts[o] = w.end
    spans: list[tuple[float, float]] = []
    for i in range(n):
        if firsts[i] is None:  # empty scene: give it a short beat
            prev_end = spans[-1][1] if spans else 0.0
            spans.append((prev_end, prev_end + 1.5))
            continue
        start = 0.0 if i == 0 else spans[-1][1]
        nxt = next((firsts[j] for j in range(i + 1, n) if firsts[j] is not None), None)
        end = nxt if nxt is not None else max(audio_duration, lasts[i] or 0)
        spans.append((round(start, 3), round(max(end, start + 0.8), 3)))
    return Alignment(out, spans, matched / len(sw))
