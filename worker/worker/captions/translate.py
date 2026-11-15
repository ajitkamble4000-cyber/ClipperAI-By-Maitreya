"""Translate caption words with the configured text AI, keeping the original timing.

Words are grouped into the same cues the captions use; each cue is translated as one line, then the
translated words are spread across the cue's time span in proportion to their length."""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, Field
from studio_shared.languages import name as lang_name

from ..transcribe.base import Word
from .ass import chunk_words

BATCH = 60


class CueTranslations(BaseModel):
    lines: list[str] = Field(description="One translated line per input line, same order and count")


SYSTEM = (
    "You translate short-video captions. Keep each line short, natural and spoken, like a native creator would "
    "say it. Keep names, numbers, brand names and @handles unchanged. Never merge or split lines."
)


def spread(text: str, start: float, end: float) -> list[Word]:
    toks = text.split()
    if not toks:
        return []
    total = sum(len(t) + 1 for t in toks)
    out, t = [], start
    for tok in toks:
        d = (end - start) * (len(tok) + 1) / total
        out.append(Word(tok, round(t, 3), round(t + d, 3), 1.0))
        t += d
    return out


def translate_words(
    words: list[Word],
    target: str,
    gem,
    *,
    source_language: str | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> list[Word]:
    if not words:
        return []
    cues = chunk_words(words, 6, max_gap=0.9)
    lines = [" ".join(w.text for w in c.words) for c in cues]
    out: list[str] = []
    for b in range(0, len(lines), BATCH):
        part = lines[b : b + BATCH]
        numbered = "\n".join(f"{i + 1}. {ln}" for i, ln in enumerate(part))
        prompt = (
            f"Translate these {len(part)} caption lines"
            f"{f' from {lang_name(source_language)}' if source_language else ''} into {lang_name(target)}. "
            f"Return exactly {len(part)} lines in the same order, without the numbers.\n\n{numbered}"
        )
        got: list[str] = []
        for _ in range(2):
            res = gem.generate_json(prompt, CueTranslations, system=SYSTEM, temperature=0.3)
            got = [ln.strip() for ln in res.lines]
            if len(got) == len(part):
                break
        if len(got) != len(part):  # still mismatched: pad/trim rather than fail the whole job
            got = (got + part[len(got) :])[: len(part)]
        out.extend(got)
        if on_progress:
            on_progress(min(1.0, (b + len(part)) / len(lines)))
    result: list[Word] = []
    for c, text in zip(cues, out, strict=True):
        result.extend(spread(text, c.words[0].start, c.words[-1].end))
    return result
