"""The web app ships a copy of the caption presets for its live preview; it must match the worker's."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_web_caption_presets_match_shared():
    shared = json.loads((ROOT / "shared/presets/captions.json").read_text())
    web = json.loads((ROOT / "web/lib/presets/captions.json").read_text())
    assert shared == web, "run: cp shared/presets/captions.json web/lib/presets/captions.json"

