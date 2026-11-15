"""Basic mode (no Gemini key or budget reached): speech density + loudness peaks."""

from __future__ import annotations

import re

import numpy as np

from ...transcribe.base import Transcript
from .schema import Candidate

STOP = set(
    [
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "so",
        "to",
        "of",
        "in",
        "on",
        "at",
        "for",
        "is",
        "are",
        "was",
        "were",
        "be",
        "it",
        "this",
        "that",
        "i",
        "you",
        "he",
        "she",
        "we",
        "they",
        "my",
        "your",
        "our",
        "their",
        "with",
        "as",
        "from",
        "by",
        "not",
        "do",
        "does",
        "did",
        "have",
        "has",
        "had",
        "just",
        "like",
        "yeah",
        "um",
        "uh",
        "okay",
    ]
)


def _title(text: str) -> str:
    words = text.strip().split()
    title = " ".join(words[:9])
    return (title[:57] + "…") if len(title) > 58 else title


def _hashtags(text: str) -> list[str]:
    words = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z']{3,}", text)]
    freq: dict[str, int] = {}
    for w in words:
        if w not in STOP:
            freq[w] = freq.get(w, 0) + 1
    top = sorted(freq, key=lambda w: -freq[w])[:5]
    return ["#shorts", *[f"#{w.replace(chr(39), '')}" for w in top]][:8]


def find(
    t: Transcript,
    *,
    n: int,
    min_len: int,
    max_len: int,
    duration: float,
    loudness: np.ndarray | None,
    hop: float = 0.5,
    content_type: str = "other",
) -> list[Candidate]:
    target = min(max_len, max(min_len, (min_len + max_len) / 2))
    words = t.words
    if duration <= 0:
        return []
    step = max(2.0, target / 4)
    starts = [s.start for s in t.segments] or list(np.arange(0, max(0.1, duration - target), step))
    loud_z = None
    if loudness is not None and len(loudness):
        loud_z = (loudness - np.median(loudness)) / (np.std(loudness) + 1e-6)
    cands = []
    for s in starts:
        e = min(duration, s + target)
        if e - s < min_len * 0.8:
            continue
        ws = [w for w in words if s <= w.start < e]
        density = len(ws) / max(1.0, e - s)  # words per second
        text = " ".join(w.text for w in ws)
        punch = text.count("!") + text.count("?") * 0.5
        loud = 0.0
        if loud_z is not None:
            seg = loud_z[int(s / hop) : int(e / hop) + 1]
            loud = float(np.max(seg)) if len(seg) else 0.0
        weight_loud = 1.6 if content_type == "sports" else 0.6
        score = density * 1.0 + punch * 0.3 + loud * weight_loud
        cands.append((score, s, e, text))
    cands.sort(key=lambda c: -c[0])
    if not cands:
        return []
    hi, lo = cands[0][0], cands[-1][0]
    out = []
    for score, s, e, text in cands[:200]:
        v = int(30 + 50 * ((score - lo) / (hi - lo + 1e-6)))
        out.append(
            Candidate(
                start=s,
                end=e,
                title=_title(text) or "Highlight",
                hook_text=" ".join(text.split()[:5]).upper(),
                description=text[:200],
                hashtags=_hashtags(text),
                virality_score=v,
                reason="Basic mode: high speech density / loudness",
                mode="basic",
            )
        )
    return out
