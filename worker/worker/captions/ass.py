"""Build an ASS subtitle file from word timestamps for one of the caption presets.

The canvas (PlayRes) equals the output size, so sizes/positions are in output pixels. On 9:16 text is kept
inside the Shorts safe zone: never in the bottom ~25% (title, buttons) and away from the right rail. Other
formats (1:1, 4:5, 16:9) use symmetric margins and proportionally scaled text.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

from ..transcribe.base import Word
from .style import CaptionStyle, catalog, font_path, is_devanagari

W, H = 1080, 1920
SAFE_LEFT, SAFE_RIGHT = 70, 950  # right rail (like/comment buttons) starts ~950px
MAX_TEXT_W = SAFE_RIGHT - SAFE_LEFT - 40
CENTER_X = (SAFE_LEFT + SAFE_RIGHT) // 2  # 510: slightly left of center, clear of the rail
SAFE_TOP, SAFE_BOTTOM = 230, int(H * 0.76)

ASPECTS: dict[str, tuple[int, int]] = {
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
    "16:9": (1920, 1080),
}


@dataclass(frozen=True)
class Canvas:
    """Output frame and the area captions may use."""

    w: int = W
    h: int = H

    @property
    def vertical(self) -> bool:
        return self.w * 16 == self.h * 9

    @property
    def safe_left(self) -> int:
        return SAFE_LEFT if self.vertical else int(self.w * 0.07)

    @property
    def safe_right(self) -> int:
        return SAFE_RIGHT if self.vertical else int(self.w * 0.93)

    @property
    def safe_top(self) -> int:
        return SAFE_TOP if self.vertical else int(self.h * 0.08)

    @property
    def safe_bottom(self) -> int:
        return SAFE_BOTTOM if self.vertical else int(self.h * 0.9)

    @property
    def center_x(self) -> int:
        return (self.safe_left + self.safe_right) // 2

    @property
    def max_text_w(self) -> int:
        return self.safe_right - self.safe_left - 40

    @property
    def scale(self) -> float:
        """Text scale relative to the 1080x1920 design size."""
        return 1.0 if self.vertical else max(0.6, min(1.0, self.h / H * 1.35))


def canvas_for(aspect: str | None) -> Canvas:
    w, h = ASPECTS.get(aspect or "9:16", ASPECTS["9:16"])
    return Canvas(w, h)


def ass_color(hex_color: str, alpha: float = 0.0) -> str:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = h[0:2], h[2:4], h[4:6]
    a = max(0, min(255, round(alpha * 255)))
    return f"&H{a:02X}{b}{g}{r}".upper()


def ts(t: float) -> str:
    t = max(0.0, t)
    cs = round(t * 100)
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, c = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{c:02d}"


def clean(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ").strip()


@lru_cache(maxsize=64)
def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(font_path(name)), size)


def text_width(text: str, font: str, size: int) -> float:
    return float(_font(font, size).getlength(text))


@dataclass
class Chunk:
    words: list[Word]
    start: float
    end: float


def chunk_words(words: list[Word], per_line: int, *, max_gap: float = 0.7) -> list[Chunk]:
    """Group words into on-screen chunks: at most `per_line` words, break on sentence ends and pauses."""
    chunks: list[Chunk] = []
    cur: list[Word] = []
    for w in words:
        if cur and (
            len(cur) >= per_line or w.start - cur[-1].end > max_gap or re.search(r"[.!?…]$", cur[-1].text)
        ):
            chunks.append(Chunk(cur, cur[0].start, cur[-1].end))
            cur = []
        cur.append(w)
    if cur:
        chunks.append(Chunk(cur, cur[0].start, cur[-1].end))
    # Hold each chunk until the next one starts (no flicker), at least 0.35 s on screen.
    for i, c in enumerate(chunks):
        nxt = chunks[i + 1].start if i + 1 < len(chunks) else c.end + 0.4
        c.end = max(c.end, min(nxt, c.end + 0.6), c.start + 0.35)
        if i + 1 < len(chunks):
            c.end = min(c.end, nxt)
    return chunks


class AssBuilder:
    def __init__(
        self,
        style: CaptionStyle,
        *,
        seed: int = 7,
        canvas: Canvas | None = None,
        emphasis: bool = False,
        emphasis_words: list[str] | None = None,
    ) -> None:
        self.s = style
        self.c = canvas or Canvas()
        self.events: list[str] = []
        self.rng = random.Random(seed)
        self.size = max(28, round(style.size * self.c.scale))
        self.emphasis = emphasis
        self.emphasis_words = emphasis_words or []
        self._emph: set[int] = set()
        frac = catalog()["positions"][style.position]
        if not self.c.vertical and style.position == "lower":
            frac = 0.8  # no platform buttons to dodge outside 9:16: sit lower, like broadcast subtitles
        self.y = int(self.c.h * frac)
        margin = round(80 * self.c.scale)
        self.y = max(self.c.safe_top + margin, min(self.c.safe_bottom - margin, self.y))

    # ------------------------------------------------------------ helpers
    def _font_for(self, text: str) -> str:
        return catalog()["devanagari_font"] if is_devanagari(text) else self.s.font

    def _word(self, w: Word) -> str:
        t = clean(w.text)
        return t.upper() if self.s.uppercase and not is_devanagari(t) else t

    def _lines(self, tokens: list[str], font: str, size: int) -> list[list[int]]:
        """Split token indexes into 1–2 lines that fit the canvas text width."""
        idx = list(range(len(tokens)))
        if text_width(" ".join(tokens), font, size) <= self.c.max_text_w or len(tokens) < 2:
            return [idx]
        best, best_cost = 1, float("inf")
        for k in range(1, len(tokens)):
            a = text_width(" ".join(tokens[:k]), font, size)
            b = text_width(" ".join(tokens[k:]), font, size)
            cost = max(a, b)
            if cost < best_cost:
                best, best_cost = k, cost
        return [idx[:best], idx[best:]]

    def _fit_size(self, tokens: list[str], font: str) -> int:
        size = self.size
        floor = max(24, round(40 * self.c.scale))
        while size > floor:
            lines = self._lines(tokens, font, size)
            if all(
                text_width(" ".join(tokens[i] for i in ln), font, size) <= self.c.max_text_w for ln in lines
            ):
                return size
            size -= 4
        return size

    def _add(self, start: float, end: float, text: str, *, layer: int = 1, style: str = "Cap") -> None:
        if end - start < 0.02:
            return
        self.events.append(f"Dialogue: {layer},{ts(start)},{ts(end)},{style},,0,0,0,,{text}")

    def _join(self, tokens: list[str], lines: list[list[int]], render) -> str:
        return r"\N".join(" ".join(render(i, tokens[i]) for i in ln) for ln in lines)

    def _rounded_rect(self, cx: float, cy: float, w: float, h: float, r: float) -> str:
        x0, y0, x1, y1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
        r = min(r, h / 2, w / 2)
        k = r * 0.45
        f = lambda v: f"{v:.0f}"  # noqa: E731
        return (
            f"m {f(x0 + r)} {f(y0)} l {f(x1 - r)} {f(y0)} "
            f"b {f(x1 - k)} {f(y0)} {f(x1)} {f(y0 + k)} {f(x1)} {f(y0 + r)} "
            f"l {f(x1)} {f(y1 - r)} b {f(x1)} {f(y1 - k)} {f(x1 - k)} {f(y1)} {f(x1 - r)} {f(y1)} "
            f"l {f(x0 + r)} {f(y1)} b {f(x0 + k)} {f(y1)} {f(x0)} {f(y1 - k)} {f(x0)} {f(y1 - r)} "
            f"l {f(x0)} {f(y0 + r)} b {f(x0)} {f(y0 + k)} {f(x0 + k)} {f(y0)} {f(x0 + r)} {f(y0)}"
        )

    def _box(
        self, start: float, end: float, w: float, h: float, cy: float, color: str, alpha: float, layer=0
    ) -> None:
        path = self._rounded_rect(self.c.center_x, cy, w, h, 22 * self.c.scale)
        self._add(
            start,
            end,
            rf"{{\an7\pos(0,0)\p1\bord0\shad0\1c{ass_color(color)}\1a{ass_color('#000000', alpha)[:4]}&}}{path}",
            layer=layer,
        )

    # ------------------------------------------------------------ presets
    def add_words(self, words: list[Word]) -> None:
        if not self.s.enabled or not words:
            return
        if self.emphasis:
            from .emphasis import keyword_flags

            self._emph = {
                id(w) for w, f in zip(words, keyword_flags(words, self.emphasis_words), strict=True) if f
            }
        for c in chunk_words(words, self.s.words_per_line):
            tokens = [self._word(w) for w in c.words]
            font = self._font_for(" ".join(tokens))
            size = self._fit_size(tokens, font)
            lines = self._lines(tokens, font, size)
            pos = rf"\an5\pos({self.c.center_x},{self.y})\fn{font}\fs{size}"
            self._chunk = c
            getattr(self, f"_p_{self.s.preset}")(c, tokens, lines, pos, font, size)

    def _is_emph(self, i: int) -> bool:
        return bool(self._emph) and id(self._chunk.words[i]) in self._emph

    def _emph_tok(self, i: int, t: str) -> str:
        """Keyword emphasis for a token that isn't the active word: highlight colour, a touch bigger."""
        if not self._is_emph(i):
            return t
        hi, base = ass_color(self.s.highlight), ass_color(self.s.color)
        return rf"{{\1c{hi}\fscx108\fscy108}}{t}{{\1c{base}\fscx100\fscy100}}"

    def _word_spans(self, c: Chunk) -> list[tuple[float, float]]:
        spans = []
        for i, w in enumerate(c.words):
            a = c.start if i == 0 else w.start
            b = c.words[i + 1].start if i + 1 < len(c.words) else c.end
            spans.append((a, max(a + 0.05, b)))
        return spans

    def _p_bold_pop(self, c: Chunk, tokens, lines, pos, font, size) -> None:
        hi = ass_color(self.s.highlight)
        base = ass_color(self.s.color)
        for k, (a, b) in enumerate(self._word_spans(c)):

            def render(i: int, t: str, k=k) -> str:
                if i != k:
                    return self._emph_tok(i, t)
                return (
                    rf"{{\1c{hi}\fscx100\fscy100\t(0,90,\fscx114\fscy114)}}{t}{{\1c{base}\fscx100\fscy100}}"
                )

            self._add(a, b, "{" + pos + "}" + self._join(tokens, lines, render))

    def _p_karaoke(self, c: Chunk, tokens, lines, pos, font, size) -> None:
        # In ASS karaoke the PrimaryColour fills over the SecondaryColour as each \kf elapses.
        parts: list[str] = []
        t = c.start
        flat = [i for ln in lines for i in ln]
        for n, i in enumerate(flat):
            w = c.words[i]
            if w.start > t:
                parts.append(rf"{{\k{round((w.start - t) * 100)}}}")
            dur = max(1, round((w.end - max(w.start, t)) * 100))
            sep = r"\N" if n > 0 and any(ln[0] == i for ln in lines[1:]) else (" " if n > 0 else "")
            parts.append(f"{sep}{{\\kf{dur}}}{tokens[i]}")
            t = max(t, w.end)
        self._add(c.start, c.end, "{" + pos + "}" + "".join(parts))

    def _p_minimal(self, c: Chunk, tokens, lines, pos, font, size) -> None:
        self._add(c.start, c.end, "{" + pos + r"\blur0.6}" + self._join(tokens, lines, self._emph_tok))

    def _p_boxed(self, c: Chunk, tokens, lines, pos, font, size) -> None:
        widths = [text_width(" ".join(tokens[i] for i in ln), font, size) for ln in lines]
        box_w = max(widths) + 56 * self.c.scale
        box_h = len(lines) * size * 1.22 + 34 * self.c.scale
        self._box(c.start, c.end, box_w, box_h, self.y, self.s.box_color, 1 - self.s.box_opacity)
        hi, base = ass_color(self.s.highlight), ass_color(self.s.color)
        for k, (a, b) in enumerate(self._word_spans(c)):

            def render(i: int, t: str, k=k) -> str:
                return rf"{{\1c{hi}}}{t}{{\1c{base}}}" if i == k else self._emph_tok(i, t)

            self._add(a, b, "{" + pos + r"\bord0\shad0}" + self._join(tokens, lines, render))

    def _p_horror(self, c: Chunk, tokens, lines, pos, font, size) -> None:
        red, white = ass_color(self.s.highlight), ass_color(self.s.color)
        for k, (a, b) in enumerate(self._word_spans(c)):
            t = a
            while t < b - 0.01:
                e = min(b, t + 0.08)
                dx, dy = self.rng.uniform(-5, 5), self.rng.uniform(-4, 4)
                rot = self.rng.uniform(-1.8, 1.8)

                def render(i: int, tok: str, k=k) -> str:
                    return rf"{{\1c{red}}}{tok}{{\1c{white}}}" if i == k else self._emph_tok(i, tok)

                cx = self.c.center_x
                p = pos.replace(f"\\pos({cx},{self.y})", f"\\pos({cx + dx:.0f},{self.y + dy:.0f})")
                self._add(t, e, "{" + p + rf"\frz{rot:.1f}\blur0.8}}" + self._join(tokens, lines, render))
                t = e

    # ------------------------------------------------------------ hook text overlay
    def add_hook(self, text: str, duration: float = 3.0, *, start: float = 0.0, y_frac: float = 0.17) -> None:
        text = clean(text).upper()
        if not text:
            return
        font = catalog()["devanagari_font"] if is_devanagari(text) else "Montserrat Black"
        size = round(76 * self.c.scale)
        words = text.split()
        lines: list[str] = []
        cur = ""
        for w in words:
            cand = f"{cur} {w}".strip()
            if cur and text_width(cand, font, size) > self.c.max_text_w - 60:
                lines.append(cur)
                cur = w
            else:
                cur = cand
        lines.append(cur)
        lines = lines[:3]
        y = max(self.c.safe_top, int(self.c.h * y_frac)) if not self.c.vertical else int(self.c.h * y_frac)
        bw = max(text_width(ln, font, size) for ln in lines) + 64 * self.c.scale
        bh = len(lines) * size * 1.18 + 40 * self.c.scale
        cy = y + bh / 2
        path = self._rounded_rect(self.c.center_x, cy, bw, bh, 24 * self.c.scale)
        self._add(
            start,
            start + duration,
            rf"{{\an7\pos(0,0)\p1\bord0\shad3\4a&H80&\1c{ass_color('#FFE500')}\fad(120,220)}}{path}",
            layer=5,
            style="Hook",
        )
        self._add(
            start,
            start + duration,
            rf"{{\an5\pos({self.c.center_x},{cy:.0f})\fn{font}\fs{size}\fad(120,220)}}" + r"\N".join(lines),
            layer=6,
            style="Hook",
        )

    # ------------------------------------------------------------ output
    def render(self) -> str:
        s = self.s
        border_style = 1
        k = self.c.scale
        outline, shadow = round(s.outline * k, 1), round(s.shadow * k, 1)
        cap = (
            f"Style: Cap,{s.font},{self.size},{ass_color(s.color)},{ass_color(s.color)},{ass_color(s.outline_color)},"
            f"{ass_color('#000000', 0.45)},0,0,0,0,100,100,0,0,{border_style},{outline},{shadow},5,0,0,0,1"
        )
        if s.preset == "karaoke":
            cap = (
                f"Style: Cap,{s.font},{self.size},{ass_color(s.highlight)},{ass_color(s.color)},{ass_color(s.outline_color)},"
                f"{ass_color('#000000', 0.45)},0,0,0,0,100,100,0,0,1,{outline},{shadow},5,0,0,0,1"
            )
        hook = f"Style: Hook,Montserrat Black,{round(76 * k)},&H00000000,&H00000000,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1"
        return "\n".join(
            [
                "[Script Info]",
                "ScriptType: v4.00+",
                f"PlayResX: {self.c.w}",
                f"PlayResY: {self.c.h}",
                "WrapStyle: 2",
                "ScaledBorderAndShadow: yes",
                "YCbCr Matrix: TV.709",
                "",
                "[V4+ Styles]",
                "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
                "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
                "MarginL, MarginR, MarginV, Encoding",
                cap,
                hook,
                "",
                "[Events]",
                "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
                *self.events,
                "",
            ]
        )

    def write(self, path: Path) -> Path:
        path.write_text(self.render(), encoding="utf-8")
        return path


def build_ass(
    words: list[Word],
    style: CaptionStyle,
    path: Path,
    *,
    hook: str | None = None,
    hook_duration: float = 3.0,
    canvas: Canvas | None = None,
    emphasis: bool = False,
    emphasis_words: list[str] | None = None,
) -> Path:
    b = AssBuilder(style, canvas=canvas, emphasis=emphasis, emphasis_words=emphasis_words)
    b.add_words(words)
    if hook:
        b.add_hook(hook, hook_duration)
    return b.write(path)
