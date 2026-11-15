"""AI client entry point (historically Gemini-only; now the multi-provider facade). Tests replace `factory`."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..ai.base import NotConfigured as ProviderNotConfigured
from ..ai.base import ProviderError
from .client import CallContext, Gemini, GeminiError, GeminiNotConfigured

# Errors any provider can raise; callers that fall back (e.g. clipper basic mode) catch both.
AIError = (GeminiError, ProviderError)


def _default_factory(ctx: CallContext) -> Any:
    from ..ai.client import AI

    return AI(ctx)


factory: Callable[[CallContext], Any] = _default_factory


def get_client(ctx: CallContext | None = None) -> Any:
    return factory(ctx or CallContext())


def available() -> bool:
    """True when a text model is chosen and its provider has credentials (does not call the API)."""
    from .. import app_settings
    from ..ai.base import credentials, parse_model_ref

    try:
        ref = parse_model_ref(app_settings.model_for("text"))
        if not ref:
            return False
        c = credentials(ref[0])
        return bool(c.key) or (ref[0] == "compat" and bool(c.base_url))
    except Exception:  # noqa: BLE001
        return False


__all__ = [
    "AIError",
    "CallContext",
    "Gemini",
    "GeminiError",
    "GeminiNotConfigured",
    "ProviderError",
    "ProviderNotConfigured",
    "available",
    "factory",
    "get_client",
]
