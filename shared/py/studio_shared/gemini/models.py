"""Classify models from the Gemini models list into the roles Settings offers. No hardcoded names."""

from __future__ import annotations

from typing import Any


def classify(models: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    roles: dict[str, list[dict[str, Any]]] = {"text": [], "image": [], "tts": [], "video": []}
    for m in models:
        name = m["name"].lower()
        actions = set(m.get("actions") or [])
        entry = {"name": m["name"], "label": m.get("display_name") or m["name"]}
        if "embed" in name or "aqa" in name:
            continue
        if "predictLongRunning" in actions and ("veo" in name or "video" in name):
            roles["video"].append(entry)
        elif "tts" in name and "generateContent" in actions:
            roles["tts"].append(entry)
        elif ("image" in name and "generateContent" in actions) or (
            "predict" in actions and "imagen" in name
        ):
            roles["image"].append(entry)
        elif "generateContent" in actions and not any(
            x in name for x in ("audio", "live", "robotics", "computer-use")
        ):
            roles["text"].append(entry)
    for v in roles.values():
        v.sort(key=lambda e: e["name"], reverse=True)
    return roles
