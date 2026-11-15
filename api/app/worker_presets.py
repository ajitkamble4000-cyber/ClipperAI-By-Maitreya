"""Read-only access to shared/presets/story.json for the API (no worker imports)."""

from __future__ import annotations

import json
from functools import lru_cache

from studio_shared.config import REPO_ROOT


@lru_cache
def _catalog() -> dict:
    return json.loads((REPO_ROOT / "shared" / "presets" / "story.json").read_text())


def speaking_style_prompt(style: str) -> str:
    styles = _catalog()["speaking_styles"]
    return (styles.get(style) or styles["dramatic"])["prompt"]
