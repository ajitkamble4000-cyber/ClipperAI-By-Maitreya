"""Story Studio presets (genres, voices, speaking styles) from shared/presets/story.json."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from studio_shared import db
from studio_shared.config import REPO_ROOT


@lru_cache
def catalog() -> dict[str, Any]:
    return json.loads((REPO_ROOT / "shared" / "presets" / "story.json").read_text())


def genre(gid: str) -> dict[str, Any]:
    return catalog()["genres"].get(gid) or catalog()["genres"]["what_if"]


def visual_style_prompt(style_id: str) -> str:
    row = db.fetch_one("select prompt from visual_styles where id = %s", [style_id])
    return row["prompt"] if row else ""


def speaking_style_prompt(style: str) -> str:
    return (catalog()["speaking_styles"].get(style) or catalog()["speaking_styles"]["dramatic"])["prompt"]


def language_instruction(lang: str) -> str:
    return (catalog()["languages"].get(lang) or catalog()["languages"]["en"])["instruction"]


def target_scenes(length_s: int) -> tuple[int, int]:
    return {30: (6, 8), 45: (7, 10), 60: (8, 12), 90: (11, 15)}.get(length_s, (6, 15))
