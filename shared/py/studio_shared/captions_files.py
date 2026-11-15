"""Caption files (SRT, WebVTT, plain transcript) from timed words. Shared by the API (downloads) and worker."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

_END = re.compile(r"[.!?…]$")


def _ts(t: float, sep: str) -> str:
    ms = round(max(0.0, t) * 1000)
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def _get(w: Any, k: str) -> Any:
    return w[k] if isinstance(w, Mapping) else getattr(w, k)


def cues(words: Iterable[Any], per_line: int = 7, max_gap: float = 0.9) -> list[tuple[float, float, str]]:
    """Group words into readable cues: at most `per_line` words, split on sentence ends and pauses."""
    out: list[tuple[float, float, str]] = []
    cur: list[Any] = []

    def flush() -> None:
        if cur:
            out.append(
                (
                    float(_get(cur[0], "start")),
                    float(_get(cur[-1], "end")),
                    " ".join(str(_get(w, "text")).strip() for w in cur),
                )
            )

    for w in words:
        if cur and (
            len(cur) >= per_line
            or float(_get(w, "start")) - float(_get(cur[-1], "end")) > max_gap
            or _END.search(str(_get(cur[-1], "text")).strip())
        ):
            flush()
            cur = []
        cur.append(w)
    flush()
    return out


def to_srt(items: list[tuple[float, float, str]]) -> str:
    return "\n".join(f"{i}\n{_ts(a, ',')} --> {_ts(b, ',')}\n{t}\n" for i, (a, b, t) in enumerate(items, 1))


def to_vtt(items: list[tuple[float, float, str]]) -> str:
    return "WEBVTT\n\n" + "\n".join(f"{_ts(a, '.')} --> {_ts(b, '.')}\n{t}\n" for a, b, t in items)


def to_txt(items: list[tuple[float, float, str]]) -> str:
    paras, cur = [], []
    for _, _, t in items:
        cur.append(t)
        if _END.search(t.rstrip()):
            paras.append(" ".join(cur))
            cur = []
    if cur:
        paras.append(" ".join(cur))
    return "\n".join(paras) + "\n"


def render_file(words: Iterable[Any], fmt: str) -> str:
    items = cues(words)
    return {"srt": to_srt, "vtt": to_vtt, "txt": to_txt}[fmt](items)
