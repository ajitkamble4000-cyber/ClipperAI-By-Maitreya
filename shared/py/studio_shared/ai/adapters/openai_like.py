"""OpenAI and everything that speaks its API: OpenRouter, Groq, DeepSeek, Mistral, Together, local Ollama…

Text (+ JSON schema, + images for vision), images (gpt-image-1), speech (PCM 24 kHz), transcription with word
timestamps (whisper-1 / Groq whisper-large-v3), and the models list."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from ..base import Credentials, ImagePart, NotConfigured, ProviderError, http_client, raise_for

OPENAI_VOICES = [
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "fable",
    "nova",
    "onyx",
    "sage",
    "shimmer",
    "verse",
]


class OpenAILike:
    def __init__(self, creds: Credentials) -> None:
        if not creds.base_url:
            raise NotConfigured(
                "Set the base URL for the OpenAI-compatible provider (e.g. https://api.groq.com/openai/v1)."
            )
        if not creds.key and creds.provider != "compat":
            raise NotConfigured(
                f"No API key for {creds.provider}. The owner can add one in Admin → AI providers."
            )
        self.c = creds

    def _headers(self, json_body: bool = True) -> dict[str, str]:
        h = {"Authorization": f"Bearer {self.c.key or 'none'}"}
        if json_body:
            h["Content-Type"] = "application/json"
        if self.c.provider == "openrouter":
            h["X-Title"] = "Shorts Studio"
        return h

    # ------------------------------------------------------------ text
    @staticmethod
    def _content(parts: list[Any]) -> str | list[dict[str, Any]]:
        if all(isinstance(p, str) for p in parts):
            return "\n\n".join(parts)
        out: list[dict[str, Any]] = []
        for p in parts:
            if isinstance(p, ImagePart):
                if p.label:
                    out.append({"type": "text", "text": p.label})
                b64 = base64.b64encode(p.data).decode()
                out.append({"type": "image_url", "image_url": {"url": f"data:{p.mime};base64,{b64}"}})
            elif isinstance(p, str):
                out.append({"type": "text", "text": p})
        return out

    def generate(
        self,
        model: str,
        parts: list[Any],
        *,
        system: str | None,
        temperature: float,
        schema: dict[str, Any] | None,
    ) -> tuple[str, dict[str, int]]:
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": self._content(parts)})
        body: dict[str, Any] = {"model": model, "messages": messages}
        if not model.startswith(("o1", "o3", "o4", "gpt-5")):
            body["temperature"] = temperature
        if schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "result", "schema": schema, "strict": False},
            }
        with http_client(300) as h:
            r = h.post(f"{self.c.base_url}/chat/completions", headers=self._headers(), json=body)
            if r.status_code == 400 and schema is not None and "response_format" in r.text:
                body["response_format"] = {"type": "json_object"}  # older / non-OpenAI models
                body["messages"][-1]["content"] = self._content(
                    [*parts, "Reply with JSON only, matching this JSON Schema:\n" + json.dumps(schema)]
                )
                r = h.post(f"{self.c.base_url}/chat/completions", headers=self._headers(), json=body)
        raise_for(r, self.c.provider)
        j = r.json()
        try:
            text = j["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as e:
            raise ProviderError(f"Unexpected response from {self.c.provider}: {str(j)[:200]}") from e
        u = j.get("usage") or {}
        return text, {
            "input_tokens": int(u.get("prompt_tokens", 0)),
            "output_tokens": int(u.get("completion_tokens", 0)),
        }

    # ------------------------------------------------------------ images
    def generate_image(self, model: str, prompt: str, *, refs: list[tuple[bytes, str]], aspect: str) -> bytes:
        size = {"9:16": "1024x1536", "16:9": "1536x1024", "1:1": "1024x1024"}.get(aspect, "1024x1536")
        with http_client(300) as h:
            if refs:  # use reference images (characters) through the edits endpoint
                files = [("image[]", (f"ref{i}.png", b, mt)) for i, (b, mt) in enumerate(refs)]
                r = h.post(
                    f"{self.c.base_url}/images/edits",
                    headers=self._headers(json_body=False),
                    data={"model": model, "prompt": prompt, "size": size, "n": "1"},
                    files=files,
                )
            else:
                r = h.post(
                    f"{self.c.base_url}/images/generations",
                    headers=self._headers(),
                    json={"model": model, "prompt": prompt, "size": size, "n": 1},
                )
        raise_for(r, self.c.provider)
        return self._image_bytes(r.json())

    def edit_image(self, model: str, image: bytes, mime: str, instruction: str, *, aspect: str) -> bytes:
        size = {"9:16": "1024x1536", "16:9": "1536x1024", "1:1": "1024x1024"}.get(aspect, "1024x1536")
        with http_client(300) as h:
            r = h.post(
                f"{self.c.base_url}/images/edits",
                headers=self._headers(json_body=False),
                data={"model": model, "prompt": instruction, "size": size, "n": "1"},
                files=[("image[]", ("image.png", image, mime))],
            )
        raise_for(r, self.c.provider)
        return self._image_bytes(r.json())

    def _image_bytes(self, j: dict[str, Any]) -> bytes:
        item = (j.get("data") or [{}])[0]
        if item.get("b64_json"):
            return base64.b64decode(item["b64_json"])
        if item.get("url"):
            with http_client(120) as h:
                r = h.get(item["url"])
                r.raise_for_status()
                return r.content
        raise ProviderError(
            "The image model returned no image (it may have been filtered). Try another prompt."
        )

    # ------------------------------------------------------------ speech
    def tts(self, model: str, text: str, *, voice: str, style: str | None) -> tuple[bytes, dict[str, int]]:
        body: dict[str, Any] = {
            "model": model,
            "input": text,
            "voice": voice if voice in OPENAI_VOICES else "onyx",
            "response_format": "pcm",
        }
        if style and "tts" in model and not model.startswith("tts-1"):
            body["instructions"] = style  # gpt-4o-mini-tts supports delivery instructions
        with http_client(300) as h:
            r = h.post(f"{self.c.base_url}/audio/speech", headers=self._headers(), json=body)
        raise_for(r, self.c.provider)
        return r.content, {"characters": len(text)}  # 24 kHz 16-bit mono PCM

    # ------------------------------------------------------------ transcription
    def transcribe(self, model: str, audio: Path, *, language: str | None) -> dict[str, Any]:
        data: dict[str, Any] = {
            "model": model,
            "response_format": "verbose_json",
            "timestamp_granularities[]": ["word", "segment"],
        }
        if language:
            data["language"] = language
        with http_client(600) as h, audio.open("rb") as f:
            r = h.post(
                f"{self.c.base_url}/audio/transcriptions",
                headers=self._headers(json_body=False),
                data=data,
                files={"file": (audio.name, f, "audio/mpeg")},
            )
        raise_for(r, self.c.provider)
        return r.json()

    # ------------------------------------------------------------ models
    def list_models(self) -> list[dict[str, Any]]:
        with http_client(60) as h:
            r = h.get(f"{self.c.base_url}/models", headers=self._headers())
        raise_for(r, self.c.provider)
        items = r.json().get("data") or []
        out = []
        for m in items:
            mid = m.get("id") or ""
            arch = m.get("architecture") or {}
            out.append(
                {
                    "name": mid,
                    "label": m.get("name") or mid,
                    "vision": "image" in (arch.get("input_modalities") or []) if arch else None,
                }
            )
        return sorted(out, key=lambda x: x["name"])
