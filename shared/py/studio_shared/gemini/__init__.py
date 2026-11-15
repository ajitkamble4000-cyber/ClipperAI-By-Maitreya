"""Gemini client. Tests replace `factory` with a fake."""

from __future__ import annotations

from collections.abc import Callable

from .client import CallContext, Gemini, GeminiError, GeminiNotConfigured

factory: Callable[[CallContext], Gemini] = lambda ctx: Gemini(ctx)  # noqa: E731


def get_client(ctx: CallContext | None = None) -> Gemini:
    return factory(ctx or CallContext())


def available() -> bool:
    """True when a key and a text model are configured (does not call the API)."""
    from .. import app_settings

    try:
        return bool(app_settings.gemini_key()) and bool(app_settings.model_for("text"))
    except Exception:  # noqa: BLE001
        return False


__all__ = [
    "CallContext",
    "Gemini",
    "GeminiError",
    "GeminiNotConfigured",
    "available",
    "get_client",
    "factory",
]
