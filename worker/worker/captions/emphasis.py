"""Keyword emphasis: pick the words worth highlighting (numbers, strong/long words, your own list)."""

from __future__ import annotations

import re

from ..transcribe.base import Word

_STOP_WORDS = """a an the and or but if then so of to in on at by for with from up down out over under again further once
    here there when where why how all any both each few more most other some such no nor not only own same than too
    very can will just should now i me my we our you your he him his she her it its they them their what which who
    whom this that these those am is are was were be been being have has had do does did doing would could about
    into through during before after above below between because while like really actually basically literally
    gonna wanna gotta yeah okay right well know think mean thing things going something anything everything"""
_STRONG_WORDS = """never always every best worst secret free money million billion insane crazy huge massive shocking
    truth mistake stop must biggest first last only fastest dangerous impossible incredible amazing"""
STOP = set(_STOP_WORDS.split())
STRONG = set(_STRONG_WORDS.split())
_ALNUM = re.compile(r"[^\w']+")


def _priority(text: str, extra: set[str]) -> int:
    """0 = not a keyword; higher = more important (your own words > numbers/money > strong words > long words)."""
    t = _ALNUM.sub("", text.lower())
    if not t:
        return 0
    if t in extra:
        return 4
    if any(ch.isdigit() for ch in t) or "$" in text or "%" in text:
        return 3
    if t in STOP:
        return 0
    if t in STRONG or text.rstrip().endswith("!"):
        return 2
    return 1 if len(t) >= 7 else 0


def is_keyword(text: str, extra: set[str] | None = None) -> bool:
    return _priority(text, extra or set()) > 0


def keyword_flags(
    words: list[Word], extra_words: list[str] | None = None, *, max_ratio: float = 0.25
) -> list[bool]:
    """One flag per word; at most ~25% of words (most important first), never two highlighted in a row."""
    extra = {_ALNUM.sub("", w.lower()) for w in (extra_words or []) if w.strip()}
    pr = [_priority(w.text, extra) for w in words]
    budget = max(1, int(len(words) * max_ratio))
    order = sorted((i for i, p in enumerate(pr) if p), key=lambda i: (-pr[i], -len(words[i].text), i))
    flags = [False] * len(words)
    for i in order:
        if sum(flags) >= budget:
            break
        if (i > 0 and flags[i - 1]) or (i + 1 < len(flags) and flags[i + 1]):
            continue
        flags[i] = True
    return flags
