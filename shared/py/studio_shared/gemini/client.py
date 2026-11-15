"""Gemini access for workers and the API, via the official google-genai SDK.

- The API key comes from Settings (encrypted) or GEMINI_API_KEY; it is never logged or returned.
- Model names come from Settings (filled from the models list API); nothing is hardcoded.
- 429/5xx are retried with exponential backoff.
- JSON output uses response_schema; invalid JSON is retried once, then repaired.
- Every call is logged to usage_events with an estimated cost.
- Image/TTS/video calls are "premium": blocked when the monthly budget is used up.
"""

from __future__ import annotations

import json
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from google import genai
from google.genai import errors as gerrors
from google.genai import types
from json_repair import repair_json
from pydantic import BaseModel, ValidationError

from .. import app_settings, usage
from ..errors import UserError

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)
RETRY_CODES = {408, 429, 500, 502, 503, 504}


class GeminiError(UserError):
    pass


class GeminiNotConfigured(GeminiError):
    pass


@dataclass
class CallContext:
    user_id: str | None = None
    project_id: str | None = None
    job_id: str | None = None


def _friendly(e: gerrors.APIError) -> GeminiError:
    msg = str(getattr(e, "message", "") or e)
    code = getattr(e, "code", 0) or 0
    low = msg.lower()
    if code in (400, 401, 403) and ("api key" in low or "api_key" in low or "permission" in low):
        return GeminiError(
            "The Gemini API key was rejected. An admin can check it in Settings → AI (Test key)."
        )
    if code == 429:
        return GeminiError(
            "Gemini rate limit or quota reached. Wait a minute, or check billing in Google AI Studio."
        )
    if code == 404:
        return GeminiError(
            f"The selected Gemini model is not available to this key ({msg[:160]}). Pick another in Settings → AI."
        )
    if "safety" in low or "blocked" in low:
        return GeminiError("Gemini refused this request for safety reasons. Try rewording the prompt.")
    return GeminiError(f"Gemini error ({code}): {msg[:300]}")


class Gemini:
    def __init__(self, ctx: CallContext | None = None, *, api_key: str | None = None) -> None:
        key = api_key or app_settings.gemini_key()
        if not key:
            raise GeminiNotConfigured("No Gemini API key is set. An admin can add one in Settings → AI.")
        self.ctx = ctx or CallContext()
        self._client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=300_000))

    # ------------------------------------------------------------ plumbing
    def model(self, role: str, override: str | None = None) -> str:
        m = override or app_settings.model_for(role)
        if not m:
            raise GeminiNotConfigured(
                f"No {role} model is selected. An admin can choose one in Settings → AI."
            )
        return m.removeprefix("models/")

    def _retry(self, fn: Callable[[], Any], *, attempts: int = 5) -> Any:
        for i in range(attempts):
            try:
                return fn()
            except gerrors.APIError as e:
                code = getattr(e, "code", 0) or 0
                if code not in RETRY_CODES or i == attempts - 1:
                    raise _friendly(e) from e
                delay = min(60.0, 2.0 * 2**i) + random.uniform(0, 1)
                log.warning("Gemini %s, retrying in %.1fs (attempt %d)", code, delay, i + 1)
                time.sleep(delay)
            except (TimeoutError, ConnectionError) as e:
                if i == attempts - 1:
                    raise GeminiError(f"Could not reach Gemini: {e}") from e
                time.sleep(min(30.0, 2.0 * 2**i))
        raise AssertionError("unreachable")

    def _record(self, model: str, kind: str, resp: Any = None, **kw: Any) -> None:
        meta = getattr(resp, "usage_metadata", None)
        try:
            usage.record(
                model=model,
                kind=kind,
                user_id=self.ctx.user_id,
                project_id=self.ctx.project_id,
                job_id=self.ctx.job_id,
                input_tokens=int(getattr(meta, "prompt_token_count", 0) or 0)
                if meta
                else kw.pop("input_tokens", 0),
                output_tokens=(
                    int(getattr(meta, "candidates_token_count", 0) or 0)
                    + int(getattr(meta, "thoughts_token_count", 0) or 0)
                )
                if meta
                else kw.pop("output_tokens", 0),
                **kw,
            )
        except Exception:  # noqa: BLE001 - usage logging must never break generation
            log.exception("failed to record usage")

    @staticmethod
    def _premium() -> None:
        usage.assert_premium_allowed()

    # ------------------------------------------------------------ text / JSON
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
        m = self.model(role, model)
        cfg = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            response_mime_type="application/json",
            response_schema=schema,
        )
        last_text = ""
        for attempt in range(2):
            resp = self._retry(
                lambda: self._client.models.generate_content(model=m, contents=contents, config=cfg)
            )
            self._record(m, kind, resp)
            last_text = resp.text or ""
            try:
                return schema.model_validate_json(last_text)
            except (ValidationError, ValueError):
                log.warning("invalid JSON from %s (attempt %d)", m, attempt + 1)
        try:
            return schema.model_validate(json.loads(repair_json(last_text)))
        except (ValidationError, ValueError) as e:
            raise GeminiError("Gemini returned malformed data twice. Please try again.") from e

    def generate_text(
        self, contents: Any, *, system: str | None = None, role: str = "text", temperature: float = 0.9
    ) -> str:
        m = self.model(role)
        cfg = types.GenerateContentConfig(system_instruction=system, temperature=temperature)
        resp = self._retry(
            lambda: self._client.models.generate_content(model=m, contents=contents, config=cfg)
        )
        self._record(m, "text", resp)
        return (resp.text or "").strip()

    # ------------------------------------------------------------ files / video understanding
    def upload_file(self, path: Path, mime_type: str = "video/mp4", timeout: float = 900) -> types.File:
        f = self._retry(lambda: self._client.files.upload(file=str(path), config={"mime_type": mime_type}))
        deadline = time.time() + timeout
        while f.state and f.state.name == "PROCESSING":
            if time.time() > deadline:
                raise GeminiError("Gemini took too long to process the uploaded video.")
            time.sleep(5)
            f = self._client.files.get(name=f.name)
        if f.state and f.state.name == "FAILED":
            raise GeminiError("Gemini could not process the uploaded video.")
        return f

    def delete_file(self, f: types.File) -> None:
        try:
            self._client.files.delete(name=f.name)
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def video_part(file: types.File | None = None, youtube_url: str | None = None) -> types.Part:
        if youtube_url:
            return types.Part(file_data=types.FileData(file_uri=youtube_url))
        assert file is not None
        return types.Part(file_data=types.FileData(file_uri=file.uri, mime_type=file.mime_type))

    # ------------------------------------------------------------ images
    def generate_image(
        self,
        prompt: str,
        *,
        refs: list[tuple[bytes, str]] | None = None,
        aspect: str = "9:16",
        model: str | None = None,
    ) -> bytes:
        """Text (+ optional reference images) -> PNG/JPEG bytes."""
        self._premium()
        m = self.model("image", model)
        if m.startswith("imagen"):
            if refs:
                log.info("%s does not accept reference images; generating from text only", m)
            resp = self._retry(
                lambda: self._client.models.generate_images(
                    model=m,
                    prompt=prompt,
                    config=types.GenerateImagesConfig(number_of_images=1, aspect_ratio=aspect),
                )
            )
            imgs = resp.generated_images or []
            if not imgs or not imgs[0].image or not imgs[0].image.image_bytes:
                raise GeminiError(
                    "The image model returned no image (it may have been filtered). Try another prompt."
                )
            self._record(m, "image", None, images=1)
            return imgs[0].image.image_bytes
        parts: list[Any] = [types.Part.from_bytes(data=b, mime_type=mt) for b, mt in (refs or [])]
        parts.append(prompt)
        cfg = types.GenerateContentConfig(
            response_modalities=["IMAGE"], image_config=types.ImageConfig(aspect_ratio=aspect)
        )
        resp = self._retry(lambda: self._client.models.generate_content(model=m, contents=parts, config=cfg))
        self._record(m, "image", resp, images=1)
        return self._first_inline(resp, "image")

    def edit_image(self, image: bytes, mime: str, instruction: str, *, aspect: str = "9:16") -> bytes:
        return self.generate_image(
            f"Edit this image: {instruction}. Keep the same composition, style and subjects unless told otherwise.",
            refs=[(image, mime)],
            aspect=aspect,
        )

    @staticmethod
    def _first_inline(resp: Any, what: str) -> bytes:
        for cand in resp.candidates or []:
            for part in (cand.content.parts if cand.content else []) or []:
                if part.inline_data and part.inline_data.data:
                    return part.inline_data.data
        reason = ""
        if resp.candidates and resp.candidates[0].finish_reason:
            reason = f" (reason: {resp.candidates[0].finish_reason})"
        raise GeminiError(f"Gemini returned no {what}{reason}. Try rewording the prompt.")

    # ------------------------------------------------------------ speech
    def tts(self, text: str, *, voice: str, style: str | None = None, model: str | None = None) -> bytes:
        """Returns raw 24 kHz 16-bit mono PCM."""
        self._premium()
        m = self.model("tts", model)
        prompt = f"{style.strip()}:\n{text}" if style else text
        cfg = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                )
            ),
        )
        resp = self._retry(lambda: self._client.models.generate_content(model=m, contents=prompt, config=cfg))
        self._record(m, "tts", resp)
        return self._first_inline(resp, "audio")

    # ------------------------------------------------------------ video (Veo)
    def start_video(
        self,
        *,
        prompt: str,
        image: bytes,
        mime: str,
        seconds: int,
        model: str | None = None,
        aspect: str = "9:16",
    ) -> Any:
        self._premium()
        m = self.model("video", model)
        cfg = types.GenerateVideosConfig(aspect_ratio=aspect, number_of_videos=1, duration_seconds=seconds)
        return self._retry(
            lambda: self._client.models.generate_videos(
                model=m, prompt=prompt, image=types.Image(image_bytes=image, mime_type=mime), config=cfg
            )
        )

    def get_operation(self, op: Any) -> Any:
        return self._retry(lambda: self._client.operations.get(op))

    def operation_from_name(self, name: str) -> Any:
        return types.GenerateVideosOperation(name=name)

    def download_video(self, op: Any, *, model: str, seconds: float) -> bytes:
        vids = (op.response.generated_videos if op.response else None) or []
        if not vids or not vids[0].video:
            raise GeminiError("Veo finished without a video (it may have been filtered).")
        video = vids[0].video
        data = video.video_bytes or self._retry(lambda: self._client.files.download(file=video))
        # Usage is recorded by the caller (worker), which knows the user/project and the billed seconds.
        return bytes(data)

    # ------------------------------------------------------------ models
    def list_models(self) -> list[dict[str, Any]]:
        out = []
        for mdl in self._retry(lambda: list(self._client.models.list())):
            out.append(
                {
                    "name": (mdl.name or "").removeprefix("models/"),
                    "display_name": mdl.display_name,
                    "description": mdl.description,
                    "actions": list(mdl.supported_actions or []),
                }
            )
        return out
