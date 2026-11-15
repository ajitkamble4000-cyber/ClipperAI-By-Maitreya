"""Find clip candidates with Gemini (structured JSON), chunking long transcripts."""

from __future__ import annotations

import math
from collections.abc import Callable

from ...transcribe.base import Transcript
from .prompts import SYSTEM, build_prompt
from .schema import Candidate, ClipIdeas

CHUNK_SECONDS = 25 * 60
OVERLAP = 60


def transcript_lines(t: Transcript, start: float = 0, end: float = float("inf")) -> str:
    return "\n".join(
        f"[{s.start:.1f}-{s.end:.1f}] {s.text}" for s in t.segments if s.end > start and s.start < end
    )


def _windows(duration: float) -> list[tuple[float, float]]:
    if duration <= CHUNK_SECONDS * 1.2:
        return [(0.0, duration)]
    out = []
    s = 0.0
    while s < duration:
        out.append((max(0.0, s - OVERLAP), min(duration, s + CHUNK_SECONDS)))
        s += CHUNK_SECONDS
    return out


def find(
    gem,
    t: Transcript,
    *,
    n: int,
    min_len: int,
    max_len: int,
    content_type: str,
    language: str | None,
    peaks: list[tuple[float, float]],
    duration: float,
    video_part=None,
    on_progress: Callable[[float], None] | None = None,
) -> list[Candidate]:
    cands: list[Candidate] = []
    wins = _windows(duration)
    for i, (a, b) in enumerate(wins):
        k = n if len(wins) == 1 else max(2, math.ceil(n * (b - a) / duration) + 1)
        k = min(k + 2, 25)  # ask for a few extra; validation drops weak/overlapping ones
        win_peaks = [p for p in peaks if a <= p[0] <= b]
        contents: list = []
        if video_part is not None and len(wins) == 1:
            contents.extend(video_part if isinstance(video_part, list) else [video_part])
        contents.append(
            build_prompt(
                transcript_text=transcript_lines(t, a, b),
                n=k,
                min_len=min_len,
                max_len=max_len,
                content_type=content_type,
                language=language,
                peaks=win_peaks,
                window=(a, b) if len(wins) > 1 else None,
                visual=video_part is not None and len(wins) == 1,
            )
        )
        res = gem.generate_json(contents, ClipIdeas, system=SYSTEM, temperature=0.6)
        for c in res.clips:
            cands.append(Candidate(**c.model_dump(), mode="ai"))
        if on_progress:
            on_progress((i + 1) / len(wins))
    if video_part is not None and len(wins) > 1:
        # Long video: one extra pass over the whole video for visual-only moments.
        res = gem.generate_json(
            [
                *(video_part if isinstance(video_part, list) else [video_part]),
                build_prompt(
                    transcript_text="",
                    n=min(n, 10),
                    min_len=min_len,
                    max_len=max_len,
                    content_type=content_type,
                    language=language,
                    peaks=peaks,
                    visual=True,
                ),
            ],
            ClipIdeas,
            system=SYSTEM,
            temperature=0.6,
        )
        cands += [Candidate(**c.model_dump(), mode="ai") for c in res.clips]
    return cands
