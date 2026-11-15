"""Multi-provider AI. `get_client()` returns the facade; tests replace `studio_shared.gemini.factory`."""

from .base import PROVIDERS, ImagePart, NotConfigured, ProviderError, parse_model_ref, provider_status
from .client import AI, VideoOp, role_chain

__all__ = [
    "AI",
    "ImagePart",
    "NotConfigured",
    "PROVIDERS",
    "ProviderError",
    "VideoOp",
    "parse_model_ref",
    "provider_status",
    "role_chain",
]
