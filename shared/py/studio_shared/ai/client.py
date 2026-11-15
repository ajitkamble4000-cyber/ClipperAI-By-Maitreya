"""The AI facade every job uses. It routes each role (text, image, tts, video, transcribe) to the provider and
model chosen in Settings → AI providers, falls back to the next choice when a provider fails, validates/repairs
JSON, enforces the budget for premium media, and logs usage + estimated cost for every call."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from json_repair import repair_json
from pydantic import BaseModel, ValidationError

from .. import app_settings, usage
from ..gemini.client import CallContext, Gemini, GeminiError
from .adapters.openai_like import OPENAI_VOICES, OpenAILike
from .adapters.others import Anthropic, ElevenLabs, Replicate, Stability
from .base import PROVIDERS, ImagePart, NotConfigured, ProviderError, credentials, parse_model_ref

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


@dataclass
class VideoOp:
    name: str
    done: bool = False
    error: Any = None
    url: str | None = None
    raw: Any = None
    response: Any = None


def adapter(provider: str):
    c = credentials(provider)
    if provider in ("openai", "openrouter", "compat"):
        return OpenAILike(c)
    if provider == "anthropic":
        return Anthropic(c)
    if provider == "elevenlabs":
        return ElevenLabs(c)
    if provider == "replicate":
        return Replicate(c)
    if provider == "stability":
        return Stability(c)
    if provider == "google":
        if not c.key:
            raise NotConfigured("No Google Gemini key. The owner can add one in Settings → AI providers.")
        return Gemini(api_key=c.key)
    raise NotConfigured(f"Unknown provider {provider}")


def role_chain(role: str, override: str | None = None) -> list[tuple[str, str]]:
    """[(provider, model), ...] for a role: the choice first, then fallbacks."""
    models = app_settings.get_row()["models"] or {}
    refs = [override] if override else [models.get(role)]
    refs += list(models.get(f"{role}_fallback") or [])
    chain = [p for p in (parse_model_ref(r) for r in refs if r) if p]
    if not chain:
        raise NotConfigured(f"No {role} model is selected. The owner can choose one in Settings → AI providers.")
    return chain


def _schema_of(schema: type[BaseModel]) -> dict[str, Any]:
    s = schema.model_json_schema()

    def strip(node: Any) -> Any:  # some providers dislike 'title'/'default' noise
        if isinstance(node, dict):
            return {k: strip(v) for k, v in node.items() if k not in ("title", "default")}
        if isinstance(node, list):
            return [strip(x) for x in node]
        return node

    return strip(s)


class AI:
    def __init__(self, ctx: CallContext | None = None) -> None:
        self.ctx = ctx or CallContext()

    # ------------------------------------------------------------ helpers
    def _record(self, provider: str, model: str, kind: str, **kw: Any) -> None:
        try:
            name = f"stability:{model}" if provider == "stability" else model
            usage.record(
                model=name,
                kind=kind,
                user_id=self.ctx.user_id,
                project_id=self.ctx.project_id,
                job_id=self.ctx.job_id,
                meta={"provider": provider},
                **kw,
            )
        except Exception:  # noqa: BLE001
            log.exception("usage logging failed")

    def _run(self, role: str, fn, override: str | None = None):
        last: Exception | None = None
        for provider, model in role_chain(role, override):
            if role not in PROVIDERS[provider].roles:
                last = NotConfigured(f"{PROVIDERS[provider].label} can't do {role}.")
                continue
            try:
                return fn(provider, model)
            except GeminiError as e:
                last = e
            except ProviderError as e:
                last = e
                if not e.retryable:
                    break
            log.warning("%s via %s:%s failed (%s); trying the next choice", role, provider, model, last)
        assert last is not None
        raise last

    def text_provider(self) -> str:
        return role_chain("text")[0][0]

    def supports_video_input(self) -> bool:
        return PROVIDERS[self.text_provider()].video_input

    def supports_vision(self) -> bool:
        return PROVIDERS[self.text_provider()].vision

    # ------------------------------------------------------------ text
    def generate_json(
        self,
        contents: Any,
        schema: type[T],
        *,
        system: str | None = None,
        role: str = "text",
        model: str | None = None,
        temperature: float = 0.8,
        kind: str = "text",
    ) -> T:
        parts = contents if isinstance(contents, list) else [contents]

        def call(provider: str, m: str) -> T:
            if provider == "google":
                return adapter("google").generate_json(
                    parts, schema, system=system, model=m, temperature=temperature, kind=kind
                )
            a = adapter(provider)
            text = ""
            for attempt in range(2):
                text, u = a.generate(
                    m, parts, system=system, temperature=temperature, schema=_schema_of(schema)
                )
                self._record(provider, m, kind, **u)
                try:
                    return schema.model_validate_json(_strip_fences(text))
                except (ValidationError, ValueError):
                    log.warning("invalid JSON from %s:%s (attempt %d)", provider, m, attempt + 1)
            try:
                return schema.model_validate(json.loads(repair_json(_strip_fences(text))))
            except (ValidationError, ValueError) as e:
                raise ProviderError("The AI returned malformed data twice. Please try again.") from e

        return self._run(role, call, model)

    def generate_text(
        self, contents: Any, *, system: str | None = None, role: str = "text", temperature: float = 0.9
    ) -> str:
        parts = contents if isinstance(contents, list) else [contents]

        def call(provider: str, m: str) -> str:
            if provider == "google":
                return adapter("google").generate_text(parts, system=system, temperature=temperature)
            text, u = adapter(provider).generate(
                m, parts, system=system, temperature=temperature, schema=None
            )
            self._record(provider, m, "text", **u)
            return text.strip()

        return self._run(role, call)

    # Gemini-only: watch a whole video. Other providers get frames (see clipper visual analysis).
    def _gemini(self) -> Gemini:
        if self.text_provider() != "google":
            raise NotConfigured(
                "Whole-video analysis needs Google Gemini; other providers analyse frames instead."
            )
        g = adapter("google")
        g.ctx = self.ctx
        return g

    def upload_file(self, path: Path, mime_type: str = "video/mp4", timeout: float = 900):
        return self._gemini().upload_file(path, mime_type, timeout)

    def delete_file(self, f) -> None:
        try:
            self._gemini().delete_file(f)
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def video_part(file=None, youtube_url: str | None = None):
        return Gemini.video_part(file=file, youtube_url=youtube_url)

    # ------------------------------------------------------------ images
    def generate_image(
        self,
        prompt: str,
        *,
        refs: list[tuple[bytes, str]] | None = None,
        aspect: str = "9:16",
        model: str | None = None,
    ) -> bytes:
        usage.assert_premium_allowed()

        def call(provider: str, m: str) -> bytes:
            if provider == "google":
                return adapter("google").generate_image(prompt, refs=refs, aspect=aspect, model=m)
            data = adapter(provider).generate_image(m, prompt, refs=refs or [], aspect=aspect)
            self._record(provider, m, "image", images=1)
            return data

        return self._run("image", call, model)

    def edit_image(self, image: bytes, mime: str, instruction: str, *, aspect: str = "9:16") -> bytes:
        usage.assert_premium_allowed()

        def call(provider: str, m: str) -> bytes:
            if provider == "google":
                return adapter("google").edit_image(image, mime, instruction, aspect=aspect)
            data = adapter(provider).edit_image(m, image, mime, instruction, aspect=aspect)
            self._record(provider, m, "image", images=1)
            return data

        return self._run("image", call)

    # ------------------------------------------------------------ speech
    def tts_provider(self) -> str:
        return role_chain("tts")[0][0]

    def tts(self, text: str, *, voice: str, style: str | None = None, model: str | None = None) -> bytes:
        """Raw 24 kHz 16-bit mono PCM from whichever voice provider is chosen."""
        usage.assert_premium_allowed()

        def call(provider: str, m: str) -> bytes:
            if provider == "google":
                return adapter("google").tts(text, voice=voice, style=style, model=m)
            v = voice
            if provider == "openai" and voice not in OPENAI_VOICES:
                v = "onyx"
            pcm, u = adapter(provider).tts(m, text, voice=v, style=style)
            self._record(provider, m, "tts", **u)
            return pcm

        return self._run("tts", call, model)

    # ------------------------------------------------------------ video
    def video_provider(self) -> str:
        return role_chain("video")[0][0]

    def start_video(
        self,
        *,
        prompt: str,
        image: bytes,
        mime: str,
        seconds: int,
        model: str | None = None,
        aspect: str = "9:16",
    ) -> VideoOp:
        usage.assert_premium_allowed()
        provider, m = role_chain("video", model)[0]
        if provider == "google":
            op = adapter("google").start_video(
                prompt=prompt, image=image, mime=mime, seconds=seconds, model=m, aspect=aspect
            )
            return VideoOp(name=op.name, done=bool(op.done), error=getattr(op, "error", None), raw=op)
        d = adapter(provider).start_video(m, prompt=prompt, image=image, mime=mime, seconds=seconds)
        return VideoOp(name=d["name"])

    def operation_from_name(self, name: str) -> VideoOp:
        if name.startswith("replicate:"):
            return VideoOp(name=name)
        g = adapter("google")
        return VideoOp(name=name, raw=g.operation_from_name(name))

    def get_operation(self, op: VideoOp) -> VideoOp:
        if op.name.startswith("replicate:"):
            d = adapter("replicate").poll(op.name)
            return VideoOp(name=op.name, done=d["done"], error=d["error"], url=d.get("url"))
        g = adapter("google")
        raw = g.get_operation(op.raw if op.raw is not None else g.operation_from_name(op.name))
        return VideoOp(
            name=op.name,
            done=bool(raw.done),
            error=getattr(raw, "error", None),
            raw=raw,
            response=getattr(raw, "response", None),
        )

    def download_video(self, op: VideoOp, *, model: str, seconds: float) -> bytes:
        if op.name.startswith("replicate:"):
            return adapter("replicate").download({"url": op.url})
        return adapter("google").download_video(op.raw, model=model, seconds=seconds)

    # ------------------------------------------------------------ catalogue
    @staticmethod
    def list_models(provider: str) -> list[dict[str, Any]]:
        a = adapter(provider)
        if provider == "google":
            return [
                {"name": m["name"], "label": m.get("display_name") or m["name"], "actions": m.get("actions")}
                for m in a.list_models()
            ]
        return a.list_models()

    @staticmethod
    def voices(provider: str) -> list[dict[str, Any]]:
        if provider == "elevenlabs":
            return adapter("elevenlabs").voices()
        if provider == "openai":
            return [{"name": v, "label": v.title(), "desc": "OpenAI voice"} for v in OPENAI_VOICES]
        from ..config import REPO_ROOT

        cat = json.loads((REPO_ROOT / "shared" / "presets" / "story.json").read_text())
        return [{"name": v["name"], "label": v["name"], "desc": v["desc"]} for v in cat["voices"]]


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    return t.strip()


def ImageParts(frames: list[tuple[float, bytes]]) -> list[ImagePart]:  # noqa: N802 - reads like a constructor
    return [ImagePart(data=b, mime="image/jpeg", label=f"Frame at {t:.1f}s") for t, b in frames]
