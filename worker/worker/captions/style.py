"""Caption styles: presets from shared/presets/captions.json merged with user overrides."""

from __future__ import annotations

import json
from dataclasses import dataclass, fields
from functools import lru_cache
from pathlib import Path
from typing import Any

from studio_shared.config import REPO_ROOT, get_settings

PRESETS_FILE = REPO_ROOT / "shared" / "presets" / "captions.json"


@lru_cache
def catalog() -> dict[str, Any]:
    return json.loads(PRESETS_FILE.read_text())


@dataclass
class CaptionStyle:
    preset: str = "bold_pop"
    font: str = "Montserrat Black"
    size: int = 86
    color: str = "#FFFFFF"
    highlight: str = "#FFE500"
    outline_color: str = "#000000"
    outline: float = 7
    shadow: float = 3
    uppercase: bool = True
    words_per_line: int = 3
    position: str = "lower"
    emoji: bool = False
    box_color: str = "#000000"
    box_opacity: float = 0.72
    enabled: bool = True

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> CaptionStyle:
        d = dict(d or {})
        preset = d.get("preset") or "bold_pop"
        if preset == "none":
            return cls(enabled=False)
        base = dict(catalog()["presets"].get(preset) or catalog()["presets"]["bold_pop"])
        base.update({k: v for k, v in d.items() if v is not None})
        names = {f.name for f in fields(cls)}
        s = cls(**{k: v for k, v in base.items() if k in names})
        s.preset = preset if preset in catalog()["presets"] else "bold_pop"
        s.size = int(max(36, min(160, s.size)))
        s.words_per_line = int(max(1, min(8, s.words_per_line)))
        if s.position not in catalog()["positions"]:
            s.position = "lower"
        if s.font not in catalog()["fonts"]:
            s.font = base.get("font", "Montserrat Black")
        return s


def font_path(name: str) -> Path:
    info = catalog()["fonts"].get(name) or catalog()["fonts"]["Montserrat Black"]
    return get_settings().fonts_dir / info["file"]


def fonts_dir() -> Path:
    return get_settings().fonts_dir


def is_devanagari(text: str) -> bool:
    return any("ऀ" <= ch <= "ॿ" for ch in text)
