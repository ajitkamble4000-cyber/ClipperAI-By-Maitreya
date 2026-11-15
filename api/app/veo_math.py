"""How many seconds of Veo video a scene needs (used for estimates and by the worker)."""

from __future__ import annotations

from typing import Any

VEO_LENGTHS = (4, 6, 8)


def scene_seconds(scene: dict[str, Any]) -> float:
    if scene.get("audio_start_s") is not None and scene.get("audio_end_s") is not None:
        return float(scene["audio_end_s"]) - float(scene["audio_start_s"])
    return float(scene.get("duration_estimate") or 4)


def veo_seconds(scene: dict[str, Any]) -> int:
    """Veo makes 4/6/8 s clips; pick the shortest that covers the scene (longer scenes are slowed/held)."""
    need = scene_seconds(scene)
    return next((n for n in VEO_LENGTHS if n >= need), VEO_LENGTHS[-1])
