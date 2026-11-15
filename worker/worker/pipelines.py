"""Registry: job kind -> pipeline factory. Imported lazily so heavy deps load only when needed."""

from __future__ import annotations

import importlib
from collections.abc import Callable

from .pipeline import Pipeline

_REGISTRY: dict[str, str] = {
    "dummy": "worker.dummy:build",
    "clip": "worker.clipper.pipeline:build",
    "clip_rerender": "worker.clipper.extra_jobs:build_rerender",
    "clip_zip": "worker.clipper.extra_jobs:build_zip",
    "story_script": "worker.story.script:build_script",
    "story_scene_ai": "worker.story.script:build_scene_ai",
    "story_characters": "worker.story.images:build_characters",
    "story_images": "worker.story.images:build_images",
    "story_image_one": "worker.story.images:build_image_one",
    "story_voice": "worker.story.voice:build_voice",
    "story_render": "worker.story.render:build_render",
}


def register(kind: str, target: str) -> None:
    _REGISTRY[kind] = target


def get_pipeline(kind: str, params: dict) -> Pipeline:
    target = _REGISTRY.get(kind)
    if not target:
        raise KeyError(f"Unknown job kind: {kind}")
    mod, fn = target.split(":")
    factory: Callable[[dict], Pipeline] = getattr(importlib.import_module(mod), fn)
    return factory(params)
