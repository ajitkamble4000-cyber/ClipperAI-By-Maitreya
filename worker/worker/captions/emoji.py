"""Auto-emoji: pick an emoji for caption chunks by keyword and render it as a color PNG overlay.
(libass cannot draw color emoji, so emoji are composited with ffmpeg's overlay filter.)"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ..transcribe.base import Word
from .ass import CENTER_X, H, chunk_words

KEYWORDS: dict[str, str] = {
    "money": "💰",
    "cash": "💵",
    "rich": "🤑",
    "dollar": "💵",
    "million": "💸",
    "billion": "💸",
    "fire": "🔥",
    "hot": "🔥",
    "crazy": "🤪",
    "insane": "🤯",
    "mind": "🤯",
    "unbelievable": "🤯",
    "shocking": "😱",
    "scary": "😱",
    "afraid": "😨",
    "fear": "😨",
    "dead": "💀",
    "death": "💀",
    "die": "💀",
    "kill": "🔪",
    "blood": "🩸",
    "ghost": "👻",
    "night": "🌙",
    "dark": "🌑",
    "love": "❤️",
    "heart": "❤️",
    "happy": "😄",
    "funny": "😂",
    "laugh": "😂",
    "lol": "😂",
    "sad": "😢",
    "cry": "😭",
    "angry": "😡",
    "win": "🏆",
    "won": "🏆",
    "winner": "🏆",
    "goal": "⚽",
    "score": "🎯",
    "ball": "⚽",
    "game": "🎮",
    "play": "▶️",
    "music": "🎵",
    "song": "🎶",
    "time": "⏰",
    "fast": "⚡",
    "speed": "⚡",
    "power": "⚡",
    "energy": "⚡",
    "strong": "💪",
    "gym": "🏋️",
    "brain": "🧠",
    "think": "🤔",
    "idea": "💡",
    "secret": "🤫",
    "truth": "✅",
    "true": "✅",
    "wrong": "❌",
    "no": "🚫",
    "stop": "🛑",
    "warning": "⚠️",
    "danger": "⚠️",
    "space": "🚀",
    "rocket": "🚀",
    "planet": "🪐",
    "sun": "☀️",
    "moon": "🌙",
    "star": "⭐",
    "earth": "🌍",
    "world": "🌍",
    "water": "💧",
    "ocean": "🌊",
    "black hole": "🕳️",
    "hole": "🕳️",
    "eat": "🍽️",
    "food": "🍔",
    "honey": "🍯",
    "cat": "🐱",
    "dog": "🐶",
    "car": "🚗",
    "phone": "📱",
    "computer": "💻",
    "ai": "🤖",
    "robot": "🤖",
    "book": "📚",
    "school": "🎓",
    "history": "📜",
    "king": "👑",
    "queen": "👑",
    "eye": "👀",
    "look": "👀",
    "watch": "👀",
    "wow": "😮",
    "question": "❓",
    "why": "❓",
    "free": "🆓",
    "new": "🆕",
    "boom": "💥",
    "explode": "💥",
    "bus": "🚌",
}
_RX = re.compile(r"[^\w\s]")


def pick(text: str) -> str | None:
    low = " " + _RX.sub(" ", text.lower()) + " "
    for k, e in KEYWORDS.items():
        if f" {k} " in low:
            return e
    return None


@lru_cache
def emoji_font_path() -> str | None:
    try:
        p = subprocess.run(
            ["fc-match", "-f", "%{file}", "Noto Color Emoji"], capture_output=True, text=True, timeout=10
        ).stdout
        return p if p and "Emoji" in p else None
    except Exception:  # noqa: BLE001
        return None


def render_png(emoji: str, out: Path, size: int = 140) -> Path | None:
    font = emoji_font_path()
    if not font:
        return None
    f = ImageFont.truetype(font, 109)  # NotoColorEmoji only has a 109px bitmap strike
    img = Image.new("RGBA", (136, 128), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((0, 0), emoji, font=f, embedded_color=True)
    bbox = img.getbbox()
    if not bbox:
        return None
    img = img.crop(bbox).resize((size, size), Image.Resampling.LANCZOS)
    img.save(out)
    return out


@dataclass
class Overlay:
    png: Path
    start: float
    end: float
    x: int
    y: int


def emoji_overlays(
    words: list[Word],
    per_line: int,
    caption_y: int,
    workdir: Path,
    size: int = 140,
    *,
    center_x: int = CENTER_X,
    height: int = H,
) -> list[Overlay]:
    out: list[Overlay] = []
    cache: dict[str, Path | None] = {}
    for c in chunk_words(words, per_line):
        e = pick(" ".join(w.text for w in c.words))
        if not e:
            continue
        if e not in cache:
            cache[e] = render_png(e, workdir / f"emoji_{len(cache)}.png", size)
        png = cache[e]
        if png:
            top = max(40, int(height * 0.135))
            y = max(top, caption_y - 120 - size) if caption_y > height * 0.4 else caption_y + 120
            out.append(Overlay(png, c.start, c.end, center_x - size // 2, int(y)))
        if len(out) >= 40:
            break
    return out
