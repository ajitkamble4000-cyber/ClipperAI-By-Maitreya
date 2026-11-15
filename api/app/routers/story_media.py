"""Story Studio media steps: characters, images (+ estimate), voice (+ previews, uploaded voiceover), render."""

from __future__ import annotations

import io
import wave
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from studio_shared import app_settings, db, storage, usage
from studio_shared.gemini import CallContext, GeminiError, get_client

from ..auth import CurrentMember
from .story import busy, start, story_or_404
from .uploads import take_completed_upload

router = APIRouter(tags=["story"])
MEDIA_KINDS = (
    "story_characters",
    "story_images",
    "story_image_one",
    "story_voice",
    "story_render",
    "story_veo",
)


def _premium_ok() -> None:
    usage.assert_premium_allowed()


# ---------------------------------------------------------------- characters
class CharactersIn(BaseModel):
    character_ids: list[str] | None = None


@router.post("/story/{project_id}/characters", status_code=201)
def generate_characters(project_id: str, body: CharactersIn, m: CurrentMember) -> dict:
    story_or_404(project_id)
    _premium_ok()
    busy(project_id, ("story_characters",))
    return start("story_characters", project_id, {"character_ids": body.character_ids}, m.user_id)


class CharacterIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=600)


@router.post("/story/{project_id}/characters/add", status_code=201)
def add_character(project_id: str, body: CharacterIn, _: CurrentMember) -> dict:
    story_or_404(project_id)
    row = db.fetch_one(
        "insert into characters (project_id, name, description) values (%s,%s,%s) returning *",
        [project_id, body.name.strip(), body.description.strip()],
    )
    return row


# ---------------------------------------------------------------- images
class ImagesIn(BaseModel):
    only_missing: bool = True
    force: bool = False
    scene_ids: list[str] | None = None


def _image_count(project_id: str, body: ImagesIn) -> int:
    if body.scene_ids:
        return len(body.scene_ids)
    q = "select count(*) as n from scenes where project_id = %s" + (
        " and image_key is null" if body.only_missing else ""
    )
    return int(db.fetch_one(q, [project_id])["n"])


@router.get("/story/{project_id}/estimate")
def estimate(
    project_id: str,
    _: CurrentMember,
    what: str = Query(default="images", pattern="^(images|veo)$"),
    scene_ids: str | None = None,
) -> dict:
    story_or_404(project_id)
    if what == "images":
        n = int(
            db.fetch_one(
                "select count(*) as n from scenes where project_id = %s and image_key is null", [project_id]
            )["n"]
        )
        model = app_settings.model_for("image") or ""
        per = usage.price_for(model).per_image if model else 0
        chars = int(
            db.fetch_one(
                "select count(*) as n from characters where project_id = %s and ref_key is null and not locked",
                [project_id],
            )["n"]
        )
        return {
            "model": model,
            "images": n,
            "characters": chars,
            "per_image": per,
            "estimated_usd": round((n + chars) * per, 4),
            "budget": usage.budget_state(),
        }
    ids = [s for s in (scene_ids or "").split(",") if s]
    q = "select id, audio_start_s, audio_end_s, duration_estimate from scenes where project_id = %s"
    rows = [r for r in db.fetch_all(q, [project_id]) if not ids or str(r["id"]) in ids]
    model = app_settings.model_for("video") or ""
    per_s = usage.price_for(model).per_video_second if model else 0
    from ..veo_math import veo_seconds

    secs = sum(veo_seconds(r) for r in rows)
    return {
        "model": model,
        "scenes": len(rows),
        "seconds": secs,
        "per_second": per_s,
        "estimated_usd": round(secs * per_s, 2),
        "budget": usage.budget_state(),
    }


@router.post("/story/{project_id}/images", status_code=201)
def generate_images(project_id: str, body: ImagesIn, m: CurrentMember) -> dict:
    story_or_404(project_id)
    _premium_ok()
    if not _image_count(project_id, body):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Every scene already has an image.")
    busy(project_id, ("story_images",))
    return start("story_images", project_id, body.model_dump(), m.user_id)


class SceneImageIn(BaseModel):
    instruction: str | None = Field(default=None, max_length=500)


def _scene(scene_id: str) -> dict[str, Any]:
    sc = db.fetch_one("select * from scenes where id = %s", [scene_id])
    if not sc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scene not found")
    return sc


@router.post("/scenes/{scene_id}/image", status_code=201)
def scene_image(scene_id: str, body: SceneImageIn, m: CurrentMember) -> dict:
    sc = _scene(scene_id)
    _premium_ok()
    pending = db.fetch_one(
        "select 1 from jobs where kind = 'story_image_one' and status in ('queued','running') "
        "and params->>'scene_id' = %s",
        [scene_id],
    )
    if pending:
        raise HTTPException(status.HTTP_409_CONFLICT, "This scene's image is already being generated.")
    return start(
        "story_image_one",
        str(sc["project_id"]),
        {"scene_id": scene_id, "instruction": body.instruction},
        m.user_id,
    )


class UploadRef(BaseModel):
    upload_id: str | None = None


@router.post("/scenes/{scene_id}/image/upload")
def scene_image_upload(scene_id: str, body: UploadRef, m: CurrentMember) -> dict:
    _scene(scene_id)
    if not body.upload_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "upload_id is required")
    up = take_completed_upload(body.upload_id, m.user_id, "image")
    db.execute(
        "update scenes set image_key = %s, image_source = 'upload', image_hash = null, video_key = null, "
        "video_status = null where id = %s",
        [up["r2_key"], scene_id],
    )
    return {"image_key": up["r2_key"]}


# ---------------------------------------------------------------- voice
@router.post("/story/{project_id}/voice", status_code=201)
def generate_voice(project_id: str, m: CurrentMember) -> dict:
    st = story_or_404(project_id)
    if not st["voiceover_key"]:
        _premium_ok()
    busy(project_id, ("story_voice",))
    return start("story_voice", project_id, {}, m.user_id)


@router.put("/story/{project_id}/voiceover")
def set_voiceover(project_id: str, body: UploadRef, m: CurrentMember) -> dict:
    story_or_404(project_id)
    key = take_completed_upload(body.upload_id, m.user_id, "voiceover")["r2_key"] if body.upload_id else None
    db.execute("update stories set voiceover_key = %s where project_id = %s", [key, project_id])
    return {"voiceover_key": key}


@router.get("/story/voices/preview")
def voice_preview(
    m: CurrentMember,
    voice: str = Query(min_length=2, max_length=40, pattern=r"^[A-Za-z]+$"),
    style: str = Query(default="dramatic", pattern=r"^[a-z_]+$"),
) -> dict:
    """A short sample of a Gemini TTS voice, generated once and cached for everyone."""
    model = app_settings.model_for("tts")
    if not model:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No TTS model is selected (Settings → AI).")
    key = f"library/voice-previews/{model}-{voice}-{style}.wav"
    if not storage.exists(key):
        _premium_ok()
        from ..worker_presets import speaking_style_prompt

        try:
            pcm = get_client(CallContext(m.user_id)).tts(
                "Here is how I sound. What happens next will surprise you.",
                voice=voice,
                style=speaking_style_prompt(style),
            )
        except GeminiError as e:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(pcm)
        storage.put_bytes(key, buf.getvalue(), "audio/wav")
    return {"url": storage.presign_get(key, 900)}


# ---------------------------------------------------------------- render
@router.post("/story/{project_id}/render", status_code=201)
def render(project_id: str, m: CurrentMember) -> dict:
    story_or_404(project_id)
    busy(project_id, ("story_render", "story_voice", "story_images", "story_veo"))
    return start("story_render", project_id, {}, m.user_id)
