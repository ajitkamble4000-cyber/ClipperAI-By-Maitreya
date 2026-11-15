"""Character reference images and scene images (parallel, cached, consistent characters)."""

from __future__ import annotations

import io
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from PIL import Image
from studio_shared import app_settings, db, storage
from studio_shared.config import get_settings
from studio_shared.gemini import CallContext, get_client

from ..pipeline import JobContext, Pipeline, Step, StepFailed
from . import assets, presets

log = logging.getLogger(__name__)
NO_TEXT = "Vertical 9:16 composition. No text, letters, captions, logos or watermarks anywhere in the image."


def _gem(ctx: JobContext):
    return get_client(CallContext(ctx.user_id, ctx.project_id, ctx.job_id))


def normalize_png(data: bytes, size: tuple[int, int] = (1080, 1920)) -> bytes:
    """Any image -> 1080x1920 PNG (cover-crop), so motion rendering always gets the same geometry."""
    im = Image.open(io.BytesIO(data)).convert("RGB")
    tw, th = size
    scale = max(tw / im.width, th / im.height)
    im = im.resize((round(im.width * scale), round(im.height * scale)), Image.Resampling.LANCZOS)
    left, top = (im.width - tw) // 2, (im.height - th) // 2
    im = im.crop((left, top, left + tw, top + th))
    out = io.BytesIO()
    im.save(out, "PNG", optimize=True)
    return out.getvalue()


def _story(pid: str) -> dict[str, Any]:
    row = db.fetch_one("select * from stories where project_id = %s", [pid])
    if not row:
        raise StepFailed("Story not found")
    return row


# ---------------------------------------------------------------- characters
def character_prompt(ch: dict[str, Any], style: str) -> str:
    return (
        f"Character reference portrait of {ch['name']}: {ch['description']}. Full body, front view, neutral pose, "
        f"plain neutral background, even lighting. Style: {style}. {NO_TEXT}"
    )


def generate_characters(ctx: JobContext) -> dict[str, Any]:
    st = _story(ctx.project_id)
    ids = ctx.params.get("character_ids")
    rows = db.fetch_all(
        "select * from characters where project_id = %s order by created_at", [ctx.project_id]
    )
    todo = [
        c
        for c in rows
        if (ids and str(c["id"]) in ids and not c["locked"])
        or (not ids and not c["ref_key"] and not c["locked"])
    ]
    if not todo:
        return {"generated": 0}
    gem = _gem(ctx)
    style = presets.visual_style_prompt(st["visual_style"])
    for i, ch in enumerate(todo):
        ctx.check_canceled()
        ctx.progress(i / len(todo), f"Drawing {ch['name']}")
        png = normalize_png(gem.generate_image(character_prompt(ch, style), aspect="9:16"))
        key = f"projects/{ctx.project_id}/characters/{ch['id']}/{ctx.job_id[:8]}.png"
        storage.put_bytes(key, png, "image/png")
        db.execute("update characters set ref_key = %s where id = %s", [key, ch["id"]])
    return {"generated": len(todo)}


# ---------------------------------------------------------------- scene images
def present_characters(scene: dict[str, Any], chars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Characters tagged on the scene by the script, plus any named in its prompt or narration."""
    tagged = {n.lower() for n in (scene.get("characters") or [])}
    text = scene["image_prompt"] + " " + scene["narration"]
    return [
        c
        for c in chars
        if c["name"].lower() in tagged or re.search(rf"\b{re.escape(c['name'])}\b", text, re.I)
    ]


def scene_prompt(scene: dict[str, Any], style: str, chars: list[dict[str, Any]]) -> str:
    present = present_characters(scene, chars)
    parts = [scene["image_prompt"].strip(), f"Style: {style}."]
    if present:
        parts.append(
            "Keep these characters exactly consistent with their reference images: "
            + "; ".join(f"{c['name']} ({c['description']})" for c in present)
            + "."
        )
    parts.append(NO_TEXT)
    return " ".join(parts)


def _refs_for(scene: dict[str, Any], chars: list[dict[str, Any]]) -> list[tuple[str, bytes]]:
    present = [c for c in present_characters(scene, chars) if c["ref_key"]]
    return [(c["ref_key"], storage.get_bytes(c["ref_key"])) for c in present][:3]


def _one_scene(
    ctx: JobContext,
    scene: dict[str, Any],
    style: str,
    chars: list[dict[str, Any]],
    *,
    force: bool,
    instruction: str | None = None,
) -> str:
    gem = _gem(ctx)
    model = app_settings.model_for("image") or ""
    if instruction:  # edit the current image with a prompt
        if not scene["image_key"]:
            raise StepFailed("This scene has no image to edit yet.")
        src = storage.get_bytes(scene["image_key"])
        data = normalize_png(gem.edit_image(src, "image/png", instruction))
        h = assets.key_for(kind="edit", src=scene["image_key"], instruction=instruction, model=model)
    else:
        prompt = scene_prompt(scene, style, chars)
        refs = _refs_for(scene, chars)
        h = assets.key_for(kind="scene", prompt=prompt, model=model, refs=[k for k, _ in refs])
        cached = None if force else assets.get(h)
        if cached and storage.exists(cached):
            db.execute(
                "update scenes set image_key = %s, image_source = 'ai', image_hash = %s where id = %s",
                [cached, h, scene["id"]],
            )
            return cached
        data = normalize_png(
            gem.generate_image(prompt, refs=[(b, "image/png") for _, b in refs], aspect="9:16")
        )
    key = f"assets/{h}.png"
    storage.put_bytes(key, data, "image/png")
    assets.put(h, "image", key, {"scene_id": str(scene["id"])})
    db.execute(
        "update scenes set image_key = %s, image_source = 'ai', image_hash = %s, video_key = null, "
        "video_status = null where id = %s",
        [key, h, scene["id"]],
    )
    return key


def generate_images(ctx: JobContext) -> dict[str, Any]:
    st = _story(ctx.project_id)
    p = ctx.params
    scenes = db.fetch_all("select * from scenes where project_id = %s order by idx", [ctx.project_id])
    if p.get("scene_ids"):
        scenes = [s for s in scenes if str(s["id"]) in p["scene_ids"]]
    elif p.get("only_missing", True):
        scenes = [s for s in scenes if not s["image_key"]]
    if not scenes:
        return {"generated": 0}
    empty = [s["idx"] + 1 for s in scenes if not s["image_prompt"].strip()]
    if empty:
        raise StepFailed(f"Scene {', '.join(map(str, empty))} has no image prompt.")
    style = presets.visual_style_prompt(st["visual_style"])
    chars = db.fetch_all("select * from characters where project_id = %s", [ctx.project_id])
    done, errors = 0, []
    force = bool(p.get("force"))
    with ThreadPoolExecutor(max_workers=get_settings().image_concurrency) as pool:
        futs = {pool.submit(_one_scene, ctx, s, style, chars, force=force): s for s in scenes}
        for f in as_completed(futs):
            s = futs[f]
            try:
                f.result()
                done += 1
            except Exception as e:  # noqa: BLE001 - keep going; report per scene
                errors.append(f"scene {s['idx'] + 1}: {e}")
                log.warning("scene image failed: %s", e)
            ctx.progress(done / len(scenes), f"Images {done}/{len(scenes)}")
    if errors and not done:
        raise StepFailed("Image generation failed. " + "; ".join(errors[:3]))
    if errors:
        ctx.log("Some images failed: " + "; ".join(errors), "warn")
    first = db.fetch_one(
        "select image_key from scenes where project_id = %s and image_key is not null order by idx limit 1",
        [ctx.project_id],
    )
    if first:
        db.execute(
            "update projects set thumbnail_key = coalesce(thumbnail_key, %s) where id = %s",
            [first["image_key"], ctx.project_id],
        )
    return {"generated": done, "failed": len(errors)}


def image_one(ctx: JobContext) -> dict[str, Any]:
    st = _story(ctx.project_id)
    sc = db.fetch_one(
        "select * from scenes where id = %s and project_id = %s", [ctx.params["scene_id"], ctx.project_id]
    )
    if not sc:
        raise StepFailed("Scene not found")
    chars = db.fetch_all("select * from characters where project_id = %s", [ctx.project_id])
    key = _one_scene(
        ctx,
        sc,
        presets.visual_style_prompt(st["visual_style"]),
        chars,
        force=True,
        instruction=ctx.params.get("instruction"),
    )
    return {"image_key": key}


def build_characters(params: dict) -> Pipeline:
    return Pipeline(
        [Step("characters", generate_characters, label="Drawing characters")],
        finalize=lambda c: c.outputs["characters"],
    )


def build_images(params: dict) -> Pipeline:
    return Pipeline(
        [Step("images", generate_images, label="Generating images")], finalize=lambda c: c.outputs["images"]
    )


def build_image_one(params: dict) -> Pipeline:
    return Pipeline(
        [Step("image", image_one, label="Generating image")], finalize=lambda c: c.outputs["image"]
    )
