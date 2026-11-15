"""Registry: job kind -> pipeline factory. Imported lazily so heavy deps load only when needed."""

from __future__ import annotations

import importlib
from collections.abc import Callable

from .pipeline import Pipeline

_REGISTRY: dict[str, str] = {
    "dummy": "worker.dummy:build",
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
