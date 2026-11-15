"""Anthropic (text + vision), ElevenLabs (voices), Replicate (images + video), Stability (images)."""

from __future__ import annotations

import base64
import time
from typing import Any

from ..base import Credentials, ImagePart, NotConfigured, ProviderError, http_client, raise_for


def _need_key(c: Credentials, label: str) -> None:
    if not c.key:
        raise NotConfigured(f"No API key for {label}. The owner can add one in Settings → AI providers.")


class Anthropic:
    VERSION = "2023-06-01"

    def __init__(self, creds: Credentials) -> None:
        _need_key(creds, "Anthropic")
        self.c = creds

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.c.key or "",
            "anthropic-version": self.VERSION,
            "content-type": "application/json",
        }

    def generate(
        self,
        model: str,
        parts: list[Any],
        *,
        system: str | None,
        temperature: float,
        schema: dict[str, Any] | None,
    ) -> tuple[str, dict[str, int]]:
        content: list[dict[str, Any]] = []
        for p in parts:
            if isinstance(p, ImagePart):
                if p.label:
                    content.append({"type": "text", "text": p.label})
                content.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": p.mime,
                            "data": base64.b64encode(p.data).decode(),
                        },
                    }
                )
            elif isinstance(p, str):
                content.append({"type": "text", "text": p})
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": 8000,
            "temperature": min(1.0, temperature),
            "messages": [{"role": "user", "content": content}],
        }
        if system:
            body["system"] = system
        if schema is not None:  # structured output via a forced tool call
            body["tools"] = [{"name": "result", "description": "Return the result", "input_schema": schema}]
            body["tool_choice"] = {"type": "tool", "name": "result"}
        with http_client(300) as h:
            r = h.post(f"{self.c.base_url}/messages", headers=self._headers(), json=body)
        raise_for(r, "anthropic")
        j = r.json()
        u = j.get("usage") or {}
        usage = {
            "input_tokens": int(u.get("input_tokens", 0)),
            "output_tokens": int(u.get("output_tokens", 0)),
        }
        import json as _json

        for block in j.get("content") or []:
            if schema is not None and block.get("type") == "tool_use":
                return _json.dumps(block.get("input") or {}), usage
        text = "".join(b.get("text", "") for b in j.get("content") or [] if b.get("type") == "text")
        return text, usage

    def list_models(self) -> list[dict[str, Any]]:
        with http_client(60) as h:
            r = h.get(f"{self.c.base_url}/models", headers=self._headers(), params={"limit": 100})
        raise_for(r, "anthropic")
        return [
            {"name": m["id"], "label": m.get("display_name") or m["id"], "vision": True}
            for m in r.json().get("data", [])
        ]


class ElevenLabs:
    def __init__(self, creds: Credentials) -> None:
        _need_key(creds, "ElevenLabs")
        self.c = creds

    def _h(self) -> dict[str, str]:
        return {"xi-api-key": self.c.key or "", "content-type": "application/json"}

    def tts(self, model: str, text: str, *, voice: str, style: str | None) -> tuple[bytes, dict[str, int]]:
        settings = {"stability": 0.45, "similarity_boost": 0.8, "style": 0.35, "use_speaker_boost": True}
        if style and any(w in style.lower() for w in ("whisper", "calm", "measured")):
            settings.update(stability=0.65, style=0.2)
        if style and any(w in style.lower() for w in ("excite", "energy", "dramatic", "trailer")):
            settings.update(stability=0.3, style=0.6)
        with http_client(300) as h:
            r = h.post(
                f"{self.c.base_url}/text-to-speech/{voice}",
                headers=self._h(),
                params={"output_format": "pcm_24000"},
                json={"text": text, "model_id": model, "voice_settings": settings},
            )
        raise_for(r, "elevenlabs")
        return r.content, {"characters": len(text)}

    def voices(self) -> list[dict[str, Any]]:
        with http_client(60) as h:
            r = h.get(f"{self.c.base_url}/voices", headers=self._h())
        raise_for(r, "elevenlabs")
        out = []
        for v in r.json().get("voices", []):
            labels = v.get("labels") or {}
            desc = ", ".join(
                x for x in (labels.get("gender"), labels.get("accent"), labels.get("description")) if x
            )
            out.append(
                {
                    "name": v["voice_id"],
                    "label": v.get("name") or v["voice_id"],
                    "desc": desc,
                    "preview_url": v.get("preview_url"),
                }
            )
        return out

    def list_models(self) -> list[dict[str, Any]]:
        with http_client(60) as h:
            r = h.get(f"{self.c.base_url}/models", headers=self._h())
        raise_for(r, "elevenlabs")
        return [
            {"name": m["model_id"], "label": m.get("name") or m["model_id"]}
            for m in r.json()
            if m.get("can_do_text_to_speech", True)
        ]


class Replicate:
    """Any Replicate model by name ('owner/model' or 'owner/model:version'). Images and image-to-video."""

    def __init__(self, creds: Credentials) -> None:
        _need_key(creds, "Replicate")
        self.c = creds

    def _h(self, wait: bool = False) -> dict[str, str]:
        h = {"Authorization": f"Bearer {self.c.key}", "Content-Type": "application/json"}
        if wait:
            h["Prefer"] = "wait=60"
        return h

    def _create(self, model: str, inp: dict[str, Any], wait: bool) -> dict[str, Any]:
        name, _, version = model.partition(":")
        with http_client(120) as h:
            if version:
                r = h.post(
                    f"{self.c.base_url}/predictions",
                    headers=self._h(wait),
                    json={"version": version, "input": inp},
                )
            else:
                r = h.post(
                    f"{self.c.base_url}/models/{name}/predictions", headers=self._h(wait), json={"input": inp}
                )
        raise_for(r, "replicate")
        return r.json()

    def _get(self, pid: str) -> dict[str, Any]:
        with http_client(60) as h:
            r = h.get(f"{self.c.base_url}/predictions/{pid}", headers=self._h())
        raise_for(r, "replicate")
        return r.json()

    @staticmethod
    def _output_url(pred: dict[str, Any]) -> str | None:
        out = pred.get("output")
        if isinstance(out, list):
            return out[0] if out else None
        if isinstance(out, dict):
            return out.get("video") or out.get("image") or next(iter(out.values()), None)
        return out

    def _download(self, url: str) -> bytes:
        with http_client(300) as h:
            r = h.get(url)
            r.raise_for_status()
            return r.content

    def generate_image(self, model: str, prompt: str, *, refs: list[tuple[bytes, str]], aspect: str) -> bytes:
        inp: dict[str, Any] = {
            "prompt": prompt,
            "aspect_ratio": aspect,
            "output_format": "png",
            "num_outputs": 1,
        }
        if refs and ("kontext" in model or "redux" in model or "ref" in model):
            b, mt = refs[0]
            inp["input_image"] = f"data:{mt};base64,{base64.b64encode(b).decode()}"
        pred = self._create(model, inp, wait=True)
        deadline = time.time() + 300
        while pred.get("status") not in ("succeeded", "failed", "canceled"):
            if time.time() > deadline:
                raise ProviderError("Replicate image generation timed out.")
            time.sleep(2)
            pred = self._get(pred["id"])
        if pred["status"] != "succeeded":
            raise ProviderError(f"Replicate: {pred.get('error') or pred['status']}")
        url = self._output_url(pred)
        if not url:
            raise ProviderError("Replicate returned no image.")
        return self._download(url)

    def edit_image(self, model: str, image: bytes, mime: str, instruction: str, *, aspect: str) -> bytes:
        return self.generate_image(model, instruction, refs=[(image, mime)], aspect=aspect)

    # Video models name their inputs differently; map the common ones.
    @staticmethod
    def video_input(model: str, prompt: str, image_uri: str, seconds: int) -> dict[str, Any]:
        m = model.lower()
        if "kling" in m:
            return {
                "prompt": prompt,
                "start_image": image_uri,
                "duration": 5 if seconds <= 5 else 10,
                "aspect_ratio": "9:16",
            }
        if "minimax" in m or "hailuo" in m:
            return {"prompt": prompt, "first_frame_image": image_uri}
        if "luma" in m or "ray" in m:
            return {"prompt": prompt, "start_image_url": image_uri, "aspect_ratio": "9:16"}
        if "seedance" in m:
            return {
                "prompt": prompt,
                "image": image_uri,
                "duration": min(10, max(5, seconds)),
                "aspect_ratio": "9:16",
            }
        return {"prompt": prompt, "image": image_uri}  # wan-video and most others

    def start_video(
        self, model: str, *, prompt: str, image: bytes, mime: str, seconds: int
    ) -> dict[str, Any]:
        uri = f"data:{mime};base64,{base64.b64encode(image).decode()}"
        pred = self._create(model, self.video_input(model, prompt, uri, seconds), wait=False)
        return {"name": f"replicate:{pred['id']}", "done": False, "error": None}

    def poll(self, name: str) -> dict[str, Any]:
        pred = self._get(name.removeprefix("replicate:"))
        st = pred.get("status")
        return {
            "name": name,
            "done": st in ("succeeded", "failed", "canceled"),
            "error": None if st in ("succeeded", "starting", "processing") else (pred.get("error") or st),
            "url": self._output_url(pred) if st == "succeeded" else None,
        }

    def download(self, op: dict[str, Any]) -> bytes:
        if not op.get("url"):
            raise ProviderError("The video model finished without a video.")
        return self._download(op["url"])

    def list_models(self) -> list[dict[str, Any]]:
        popular = [
            "black-forest-labs/flux-schnell",
            "black-forest-labs/flux-dev",
            "black-forest-labs/flux-1.1-pro",
            "black-forest-labs/flux-kontext-pro",
            "ideogram-ai/ideogram-v3-turbo",
            "kwaivgi/kling-v2.1",
            "minimax/video-01",
            "wan-video/wan-2.2-i2v-fast",
            "bytedance/seedance-1-lite",
            "luma/ray-flash-2-540p",
        ]
        return [{"name": n, "label": n} for n in popular]


class Stability:
    def __init__(self, creds: Credentials) -> None:
        _need_key(creds, "Stability AI")
        self.c = creds

    def generate_image(self, model: str, prompt: str, *, refs: list[tuple[bytes, str]], aspect: str) -> bytes:
        endpoint = {"ultra": "ultra", "core": "core"}.get(model, "sd3")
        data = {"prompt": prompt, "aspect_ratio": aspect, "output_format": "png"}
        if endpoint == "sd3":
            data["model"] = model
        with http_client(180) as h:
            r = h.post(
                f"{self.c.base_url}/v2beta/stable-image/generate/{endpoint}",
                headers={"Authorization": f"Bearer {self.c.key}", "Accept": "image/*"},
                data=data,
                files={"none": ("", b"")},
            )
        raise_for(r, "stability")
        return r.content

    def edit_image(self, model: str, image: bytes, mime: str, instruction: str, *, aspect: str) -> bytes:
        return self.generate_image(model, instruction, refs=[(image, mime)], aspect=aspect)

    def list_models(self) -> list[dict[str, Any]]:
        return [
            {"name": n, "label": label}
            for n, label in (
                ("core", "Stable Image Core"),
                ("ultra", "Stable Image Ultra"),
                ("sd3.5-large", "SD 3.5 Large"),
                ("sd3.5-large-turbo", "SD 3.5 Large Turbo"),
                ("sd3.5-medium", "SD 3.5 Medium"),
            )
        ]
