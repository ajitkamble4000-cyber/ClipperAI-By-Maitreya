"""Export file naming: 01_<slug-of-title>.mp4"""

from __future__ import annotations

import re
import unicodedata


def slugify(text: str, max_len: int = 50) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return (t[:max_len].rstrip("-")) or "clip"


def clip_filename(idx: int, title: str, ext: str = "mp4") -> str:
    return f"{idx:02d}_{slugify(title)}.{ext}"
