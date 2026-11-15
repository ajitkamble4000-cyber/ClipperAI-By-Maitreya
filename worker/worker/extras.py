"""Creator extras jobs: designed thumbnails (frame or AI background + bold title) and title/hashtag ideas."""

from __future__ import annotations

import io
import json
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field
from studio_shared import db, storage, usage
from studio_shared.config import get_settings
from studio_shared.gemini import AIError, CallContext, available, get_client

from .captions.emphasis import keyword_flags
from .pipeline import JobContext, Pipeline, Step, StepFailed
from .transcribe.base import Transcript, Word

SIZES = {"youtube": (1280, 720), "vertical": (1080, 1920)}
ACCENT = "#FFE500"


# ---------------------------------------------------------------- what are we working on
def _target(ctx: JobContext) -> dict[str, Any]:
    p = ctx.params
    if p.get("clip_id"):
        c = db.fetch_one("select * from clips where id = %s", [p["clip_id"]])
        if not c:
            raise StepFailed("Clip not found")
        text = ""
        meta = (db.fetch_one("select meta from projects where id = %s", [c["project_id"]]) or {}).get(
            "meta"
        ) or {}
        if meta.get("transcript_key"):
            try:
                t = Transcript.from_json(json.loads(storage.get_bytes(meta["transcript_key"])))
                text = " ".join(w.text for w in t.slice(float(c["start_s"]), float(c["end_s"])))
            except Exception:  # noqa: BLE001 - ideas still work from the title alone
                text = ""
        return {
            "table": "clips",
            "id": str(c["id"]),
            "title": c["title"],
            "description": c["description"],
            "hook": c["hook_text"],
            "image_key": c["thumb_key"],
            "text": text,
            "brand": (c.get("render_opts") or {}).get("brand"),
        }
    s = db.fetch_one(
        "select s.*, p.title as project_title from stories s join projects p on p.id = s.project_id "
        "where s.project_id = %s",
        [p["story_id"]],
    )
    if not s:
        raise StepFailed("Story not found")
    scenes = db.fetch_all(
        "select narration, image_key from scenes where project_id = %s order by idx", [p["story_id"]]
    )
    first_img = next((sc["image_key"] for sc in scenes if sc["image_key"]), None)
    return {
        "table": "stories",
        "id": str(s["project_id"]),
        "title": s.get("title") or s["project_title"],
        "description": s["description"] or "",
        "hook": s.get("hook_text") or "",
        "image_key": s["thumb_key"] or first_img,
        "text": " ".join(sc["narration"] or "" for sc in scenes),
        "brand": None,
    }


# ---------------------------------------------------------------- thumbnails
def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(get_settings().fonts_dir / "Montserrat-Black.ttf"), size)


def _cover(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    w, h = size
    s = max(w / img.width, h / img.height)
    img = img.convert("RGB").resize(
        (max(w, round(img.width * s)), max(h, round(img.height * s))), Image.LANCZOS
    )
    x, y = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


def _wrap(words: list[str], font: ImageFont.FreeTypeFont, max_w: int) -> list[list[int]]:
    lines: list[list[int]] = [[]]
    for i in range(len(words)):
        trial = " ".join(words[j] for j in [*lines[-1], i])
        if lines[-1] and font.getlength(trial) > max_w:
            lines.append([i])
        else:
            lines[-1].append(i)
    return lines


def compose(
    bg: Image.Image,
    title: str,
    size: tuple[int, int],
    *,
    accent: str = ACCENT,
    logo: Image.Image | None = None,
) -> Image.Image:
    """Background cover-cropped, a dark gradient for contrast, a big outlined title with one highlighted word."""
    w, h = size
    img = _cover(bg, size)
    landscape = w > h
    # Darken towards where the text goes: the left side on landscape, the lower part on vertical.
    shade = Image.new("L", size, 0)
    d = ImageDraw.Draw(shade)
    if landscape:
        for x in range(w):
            d.line([(x, 0), (x, h)], fill=int(205 * max(0.0, 1 - x / (w * 0.75))))
    else:
        for y in range(h):
            d.line([(0, y), (w, y)], fill=int(190 * max(0.0, (y - h * 0.35) / (h * 0.65))))
    img = Image.composite(Image.new("RGB", size, (0, 0, 0)), img, shade)

    words = (title.strip() or "Watch this").upper().split()[:12]
    flags = keyword_flags([Word(t, i, i + 1) for i, t in enumerate(words)], max_ratio=0.2)
    max_w = int(w * (0.6 if landscape else 0.86))
    fs = int(h * (0.16 if landscape else 0.085))
    font = _font(fs)
    lines = _wrap(words, font, max_w)
    while (
        len(lines) > 3 or any(font.getlength(" ".join(words[i] for i in ln)) > max_w for ln in lines)
    ) and fs > 24:
        fs -= 4
        font = _font(fs)
        lines = _wrap(words, font, max_w)
    line_h = int(fs * 1.12)
    block_h = line_h * len(lines)
    y = (h - block_h - int(h * 0.08)) if landscape else int(h * 0.62 - block_h / 2)
    draw = ImageDraw.Draw(img)
    stroke = max(2, fs // 12)
    space = font.getlength(" ")
    for ln in lines:
        line_w = font.getlength(" ".join(words[i] for i in ln))
        x = int(w * 0.06) if landscape else int((w - line_w) / 2)
        for i in ln:
            draw.text(
                (x, y),
                words[i],
                font=font,
                fill=accent if flags[i] else "#FFFFFF",
                stroke_width=stroke,
                stroke_fill="#000000",
            )
            x += int(font.getlength(words[i]) + space)
        y += line_h
    if logo is not None:
        lw = int(min(w, h) * 0.16)
        lg = logo.convert("RGBA")
        lg = lg.resize((lw, max(1, int(lg.height * lw / lg.width))), Image.LANCZOS)
        img.paste(lg, (w - lw - int(w * 0.04), int(h * 0.04)), lg)
    return img


def step_thumbnail(ctx: JobContext) -> dict[str, Any]:
    t = _target(ctx)
    title = (ctx.params.get("text") or t["hook"] or t["title"] or "").strip()
    bg_bytes: bytes | None = None
    used = "frame"
    if ctx.params.get("style") == "ai":
        if available() and usage.premium_allowed():
            try:
                gem = get_client(CallContext(ctx.user_id, ctx.project_id, ctx.job_id))
                ctx.progress(0.2, "Generating background")
                bg_bytes = gem.generate_image(
                    f"Eye-catching thumbnail background for a video titled '{t['title']}'. {t['description'][:300]} "
                    "Bold composition, one clear subject, high contrast, dramatic lighting. No text, no letters, no logos.",
                    aspect="16:9",
                )
                used = "ai"
            except AIError as e:
                ctx.log(f"AI background unavailable, using a frame from the video: {e}", "warn")
        else:
            ctx.log(
                "AI images unavailable (no provider or budget reached), using a frame from the video", "warn"
            )
    if bg_bytes is None:
        if not t["image_key"]:
            raise StepFailed("There's no frame to use yet. Render the video first.")
        bg_bytes = storage.get_bytes(t["image_key"])
    bg = Image.open(io.BytesIO(bg_bytes))
    logo = None
    if t.get("brand") and t["brand"].get("logo_key"):
        try:
            logo = Image.open(io.BytesIO(storage.get_bytes(t["brand"]["logo_key"])))
        except Exception:  # noqa: BLE001
            logo = None
    accent = (t.get("brand") or {}).get("primary_color") or ACCENT
    covers: dict[str, str] = {}
    for i, (name, size) in enumerate(SIZES.items()):
        img = compose(bg, title, size, accent=accent, logo=logo)
        out = ctx.tmp / f"{name}.jpg"
        img.save(out, "JPEG", quality=90)
        key = f"projects/{ctx.project_id}/covers/{ctx.job_id[:8]}/{name}.jpg"
        storage.upload_file(out, key, "image/jpeg")
        covers[name] = key
        ctx.progress(0.5 + 0.5 * (i + 1) / len(SIZES), "Designing thumbnails")
    key_col = "id" if t["table"] == "clips" else "project_id"
    old = db.fetch_one(f"select covers from {t['table']} where {key_col} = %s", [t["id"]])
    db.execute(
        f"update {t['table']} set covers = %s where {key_col} = %s",
        [db.jsonb({**covers, "style": used}), t["id"]],
    )
    for k in ((old or {}).get("covers") or {}).values():
        if isinstance(k, str) and k.startswith("projects/") and k not in covers.values():
            try:
                storage.delete(k)
            except Exception:  # noqa: BLE001
                pass
    return {**covers, "style": used}


# ---------------------------------------------------------------- title ideas
class TitleIdeas(BaseModel):
    titles: list[str] = Field(description="5 different catchy titles, under 70 characters each")
    hashtags: list[str] = Field(description="8 relevant hashtags starting with #")
    description: str = Field(default="", description="A short, engaging description (1-2 sentences)")


IDEAS_SYSTEM = (
    "You write titles, hashtags and descriptions that get short videos clicked, without clickbait lies."
)


def step_ideas(ctx: JobContext) -> dict[str, Any]:
    t = _target(ctx)
    if not available():
        raise StepFailed(
            "No AI text provider is set up. Ask the owner to add one in Settings → AI providers."
        )
    gem = get_client(CallContext(ctx.user_id, ctx.project_id, ctx.job_id))
    prompt = (
        f"Current title: {t['title']}\nDescription: {t['description']}\n"
        f"What is said in the video:\n{t['text'][:3000] or '(no speech)'}\n\n"
        "Write 5 alternative titles in different styles (curiosity, bold claim, question, number/list, emotional), "
        "8 hashtags (mix of broad and niche) and a fresh description. Same language as the video."
    )
    try:
        res = gem.generate_json(prompt, TitleIdeas, system=IDEAS_SYSTEM, temperature=0.9)
    except AIError as e:
        raise StepFailed(f"The AI couldn't write ideas right now: {e}") from e
    ideas = {
        "titles": [x.strip()[:100] for x in res.titles if x.strip()][:5],
        "hashtags": [
            h if h.startswith("#") else f"#{h}"
            for h in (x.strip().replace(" ", "") for x in res.hashtags)
            if h
        ][:10],
        "description": res.description.strip()[:500],
    }
    key_col = "id" if t["table"] == "clips" else "project_id"
    db.execute(f"update {t['table']} set ideas = %s where {key_col} = %s", [db.jsonb(ideas), t["id"]])
    return ideas


def build_thumbnail(params: dict) -> Pipeline:
    return Pipeline(
        [Step("thumbnail", step_thumbnail, label="Designing thumbnails")],
        finalize=lambda ctx: ctx.outputs["thumbnail"],
    )


def build_ideas(params: dict) -> Pipeline:
    return Pipeline(
        [Step("ideas", step_ideas, label="Writing title ideas")], finalize=lambda ctx: ctx.outputs["ideas"]
    )
