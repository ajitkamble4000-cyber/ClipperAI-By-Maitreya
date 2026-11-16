"""Shared types for AI providers: the provider catalog, image parts, errors, the HTTP client, and the key vault."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx

from .. import crypto, db
from ..errors import UserError

ROLES = ("text", "image", "tts", "video", "transcribe")


class ProviderError(UserError):
    """A provider call failed. `retryable` errors trigger the fallback provider."""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class NotConfigured(ProviderError):
    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=True)


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    label: str
    roles: tuple[str, ...]
    env_key: str
    default_base_url: str | None = None
    needs_base_url: bool = False
    vision: bool = False  # text model can look at images (frame-based visual analysis)
    video_input: bool = False  # text model can watch whole videos (Gemini)
    docs: str = ""


PROVIDERS: dict[str, ProviderInfo] = {
    p.id: p
    for p in [
        ProviderInfo(
            "openai",
            "OpenAI",
            ("text", "image", "tts", "transcribe"),
            "OPENAI_API_KEY",
            "https://api.openai.com/v1",
            vision=True,
            docs="https://platform.openai.com/api-keys",
        ),
        ProviderInfo(
            "anthropic",
            "Anthropic (Claude)",
            ("text",),
            "ANTHROPIC_API_KEY",
            "https://api.anthropic.com/v1",
            vision=True,
            docs="https://console.anthropic.com/settings/keys",
        ),
        ProviderInfo(
            "openrouter",
            "OpenRouter (hundreds of models)",
            ("text",),
            "OPENROUTER_API_KEY",
            "https://openrouter.ai/api/v1",
            vision=True,
            docs="https://openrouter.ai/keys",
        ),
        ProviderInfo(
            "compat",
            "OpenAI-compatible (Groq, DeepSeek, Mistral, Together, Ollama…)",
            ("text", "transcribe"),
            "COMPAT_API_KEY",
            None,
            needs_base_url=True,
            vision=True,
        ),
        ProviderInfo(
            "elevenlabs",
            "ElevenLabs",
            ("tts",),
            "ELEVENLABS_API_KEY",
            "https://api.elevenlabs.io/v1",
            docs="https://elevenlabs.io/app/settings/api-keys",
        ),
        ProviderInfo(
            "replicate",
            "Replicate (Flux, Kling, Wan, MiniMax…)",
            ("image", "video"),
            "REPLICATE_API_TOKEN",
            "https://api.replicate.com/v1",
            docs="https://replicate.com/account/api-tokens",
        ),
        ProviderInfo(
            "stability",
            "Stability AI",
            ("image",),
            "STABILITY_API_KEY",
            "https://api.stability.ai",
            docs="https://platform.stability.ai/account/keys",
        ),
        ProviderInfo(
            "google",
            "Google Gemini",
            ("text", "image", "tts", "video"),
            "GEMINI_API_KEY",
            None,
            vision=True,
            video_input=True,
            docs="https://aistudio.google.com/apikey",
        ),
        ProviderInfo("local", "On the server (faster-whisper)", ("transcribe",), ""),
    ]
}


@dataclass
class ImagePart:
    data: bytes
    mime: str = "image/jpeg"
    label: str | None = None  # e.g. "frame at 12.0s"


@dataclass
class Credentials:
    provider: str
    key: str | None
    base_url: str | None
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------- HTTP
def http_client(timeout: float = 120.0) -> httpx.Client:
    """One place to build clients so tests can swap in a MockTransport."""
    return httpx.Client(timeout=httpx.Timeout(timeout, connect=20.0), follow_redirects=True)


def raise_for(resp: httpx.Response, provider: str) -> None:
    if resp.status_code < 400:
        return
    try:
        j = resp.json()
        msg = (
            (j.get("error") or {}).get("message")
            if isinstance(j.get("error"), dict)
            else j.get("error") or j.get("detail") or j.get("message")
        )
        msg = msg if isinstance(msg, str) else str(j)[:300]
    except ValueError:
        msg = resp.text[:300]
    label = PROVIDERS.get(provider, ProviderInfo(provider, provider, (), "")).label
    if resp.status_code in (401, 403):
        raise ProviderError(
            f"{label} rejected the API key ({msg}). The owner can check it in Settings → AI providers.",
            retryable=True,
        )
    if resp.status_code == 429:
        raise ProviderError(f"{label} rate limit or quota reached ({msg}).", retryable=True)
    if resp.status_code >= 500:
        raise ProviderError(f"{label} is having problems ({resp.status_code}).", retryable=True)
    raise ProviderError(
        f"{label} error {resp.status_code}: {msg}", retryable=resp.status_code in (404, 408, 409)
    )


# ---------------------------------------------------------------- vault
def credentials(provider: str) -> Credentials:
    info = PROVIDERS.get(provider)
    if not info:
        raise NotConfigured(f"Unknown AI provider '{provider}'.")
    env_val = os.environ.get(info.env_key, "").strip() if info.env_key else ""
    row = db.fetch_one("select * from ai_providers where id = %s", [provider]) or {}
    key = env_val or (crypto.decrypt(row["key_enc"]) if row.get("key_enc") else None)
    if provider == "google" and not key:
        from .. import app_settings  # legacy location of the Gemini key

        key = app_settings.gemini_key()
    base = (row.get("base_url") or info.default_base_url or "").rstrip("/") or None
    if row and row.get("enabled") is False:
        raise NotConfigured(
            f"{info.label} is turned off. The owner can enable it in Settings → AI providers."
        )
    return Credentials(provider, key, base, row.get("extra") or {})


def save_credentials(
    provider: str,
    *,
    key: str | None = None,
    base_url: str | None = None,
    enabled: bool | None = None,
    clear_key: bool = False,
) -> None:
    db.execute("insert into ai_providers (id) values (%s) on conflict do nothing", [provider])
    if clear_key:
        db.execute(
            "update ai_providers set key_enc = null, key_last4 = null, updated_at = now() where id = %s",
            [provider],
        )
    elif key:
        db.execute(
            "update ai_providers set key_enc = %s, key_last4 = %s, updated_at = now() where id = %s",
            [crypto.encrypt(key), key[-4:], provider],
        )
    if base_url is not None:
        db.execute(
            "update ai_providers set base_url = %s where id = %s", [base_url.rstrip("/") or None, provider]
        )
    if enabled is not None:
        db.execute("update ai_providers set enabled = %s where id = %s", [enabled, provider])


def provider_status() -> list[dict[str, Any]]:
    rows = {r["id"]: r for r in db.fetch_all("select * from ai_providers")}
    out = []
    for p in PROVIDERS.values():
        r = rows.get(p.id, {})
        env = bool(p.env_key and os.environ.get(p.env_key))
        last4 = (os.environ.get(p.env_key, "")[-4:] if env else None) or r.get("key_last4")
        if p.id == "google" and not last4:
            s = db.fetch_one("select gemini_key_last4 from settings where id = 1") or {}
            last4 = s.get("gemini_key_last4")
        out.append(
            {
                "id": p.id,
                "label": p.label,
                "roles": list(p.roles),
                "docs": p.docs,
                "needs_base_url": p.needs_base_url,
                "base_url": r.get("base_url") or p.default_base_url,
                "enabled": r.get("enabled", True),
                "configured": p.id == "local" or bool(last4),
                "key_masked": f"••••••••{last4}" if last4 else None,
                "source": "env" if env else ("vault" if last4 else "none"),
                "vision": p.vision,
                "video_input": p.video_input,
            }
        )
    return out


def parse_model_ref(ref: str | None) -> tuple[str, str] | None:
    """'openai:gpt-4.1-mini' -> ('openai', 'gpt-4.1-mini'). Legacy bare names mean Google."""
    if not ref:
        return None
    head, sep, rest = ref.partition(":")
    if sep and head in PROVIDERS:
        return head, rest
    return "google", ref.removeprefix("models/")
