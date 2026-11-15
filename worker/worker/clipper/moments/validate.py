"""Make model output trustworthy: snap to word/sentence boundaries, enforce length, drop overlaps, sort."""

from __future__ import annotations

import re

from ...transcribe.base import Transcript, Word
from .schema import Candidate

END_RX = re.compile(r"[.!?…]['\")\]]*$")


def _boundaries(words: list[Word]) -> tuple[list[float], list[float]]:
    starts, ends = [], []
    for i, w in enumerate(words):
        prev = words[i - 1] if i else None
        nxt = words[i + 1] if i + 1 < len(words) else None
        if prev is None or END_RX.search(prev.text) or w.start - prev.end > 0.6:
            starts.append(w.start)
        if nxt is None or END_RX.search(w.text) or nxt.start - w.end > 0.6:
            ends.append(w.end)
    return starts, ends


def _nearest(xs: list[float], x: float, lo: float, hi: float) -> float | None:
    best = None
    for v in xs:
        if lo <= v <= hi and (best is None or abs(v - x) < abs(best - x)):
            best = v
    return best


def snap(c: Candidate, t: Transcript, *, min_len: float, max_len: float, duration: float) -> Candidate | None:
    words = t.words
    if c.start >= duration - 1 or c.end <= 1:  # outside the video: model hallucinated timestamps
        return None
    s, e = max(0.0, c.start), min(duration, c.end)
    if e <= s:
        e = min(duration, s + (min_len + max_len) / 2)
    if not words:  # no speech (music/sports): just enforce the length
        e = min(duration, max(e, s + min_len), s + max_len)
        return (
            c.model_copy(update={"start": round(s, 2), "end": round(e, 2)})
            if e - s >= min_len * 0.9
            else None
        )
    starts, ends = _boundaries(words)
    word_starts = [w.start for w in words]
    word_ends = [w.end for w in words]
    s = _nearest(starts, s, s - 3, s + 2) or _nearest(word_starts, s, s - 2, s + 2) or s
    e = _nearest(ends, e, e - 3, e + 3) or _nearest(word_ends, e, e - 2, e + 2) or e

    if e - s < min_len:  # too short: extend to later sentence ends, then earlier starts
        later = [x for x in ends if s + min_len <= x <= s + max_len]
        if later:
            e = later[0]
        else:
            e = min(duration, s + min_len)
            if e - s < min_len:
                s = max(0.0, e - min_len)
    if e - s > max_len:  # too long: cut back to the last sentence end that fits
        fit = [x for x in ends if s + min_len <= x <= s + max_len]
        e = fit[-1] if fit else max([x for x in word_ends if x <= s + max_len] or [s + max_len])
    s = max(0.0, s - 0.12)
    e = min(duration, e + 0.25)
    if e - s < min_len * 0.9 or e - s > max_len + 0.5:
        return None
    return c.model_copy(update={"start": round(s, 2), "end": round(e, 2)})


def finalize(
    cands: list[Candidate],
    t: Transcript,
    *,
    n: int,
    min_len: float,
    max_len: float,
    duration: float,
    fallback: list[Candidate] | None = None,
) -> list[Candidate]:
    snapped = []
    for c in cands:
        sc = snap(c, t, min_len=min_len, max_len=max_len, duration=duration)
        if sc:
            sc.virality_score = int(max(1, min(100, sc.virality_score)))
            sc.title = sc.title.strip()[:60] or "Untitled clip"
            sc.hashtags = [
                h if h.startswith("#") else f"#{h}"
                for h in (h.strip().replace(" ", "") for h in sc.hashtags)
                if len(h) > 1
            ][:8]
            snapped.append(sc)
    chosen: list[Candidate] = []
    for c in sorted(snapped, key=lambda c: -c.virality_score):
        if all(c.end <= o.start + 0.5 or c.start >= o.end - 0.5 for o in chosen):
            chosen.append(c)
        if len(chosen) >= n:
            break
    if len(chosen) < n and fallback:  # top up with basic-mode picks that don't overlap
        for c in finalize(fallback, t, n=n * 3, min_len=min_len, max_len=max_len, duration=duration):
            if all(c.end <= o.start + 0.5 or c.start >= o.end - 0.5 for o in chosen):
                chosen.append(c)
            if len(chosen) >= n:
                break
    return sorted(chosen, key=lambda c: -c.virality_score)
