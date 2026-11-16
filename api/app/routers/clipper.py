"""Clipper: paste any link (or upload) and get captioned clips, a captioned whole video, or let auto mode decide.
Also: batch links, link inspection, per-clip re-render and caption files (SRT / VTT / TXT)."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator, model_validator
from studio_shared import db, jobs, platforms, storage
from studio_shared.languages import TRANSLATE_TO

from ..access import clip_for
from ..auth import CurrentMember, Member
from ..plans import has_feature, launch, limit, require_feature
from ..ratelimit import _r, check_job_rate
from ..validation import sanitize_url
from .uploads import take_completed_upload

router = APIRouter(tags=["clipper"])

Reframe = Literal["face", "action", "center", "blur", "split"]
ContentType = Literal["podcast", "sports", "gaming", "interview", "vlog", "education", "other"]
Aspect = Literal["9:16", "1:1", "4:5", "16:9"]
Mode = Literal["auto", "clips", "captions"]
MusicMood = Literal["none", "auto", "suspense", "horror", "upbeat", "epic", "funny", "calm", "emotional"]


class CaptionStyleIn(BaseModel):
    preset: Literal[
        "bold_pop", "karaoke", "minimal", "boxed", "horror", "neon", "typewriter", "bounce", "none"
    ] = "bold_pop"
    font: str | None = Field(default=None, max_length=60)
    size: int | None = Field(default=None, ge=36, le=160)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    highlight: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    outline_color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    outline: float | None = Field(default=None, ge=0, le=20)
    shadow: float | None = Field(default=None, ge=0, le=20)
    uppercase: bool | None = None
    words_per_line: int | None = Field(default=None, ge=1, le=8)
    position: Literal["top", "middle", "lower"] | None = None
    emoji: bool | None = None

    def clean(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class ClipOptions(BaseModel):
    """Everything you can set for a link or upload. Defaults give good vertical clips with captions."""

    mode: Mode = "clips"
    num_clips: int = Field(default=5, ge=1, le=20)
    min_len: int = Field(default=20, ge=15, le=180)
    max_len: int = Field(default=60, ge=15, le=180)
    content_type: ContentType = "podcast"
    reframe: Reframe = "face"
    aspect: Aspect = "9:16"
    caption_style: CaptionStyleIn = CaptionStyleIn()
    language: Literal["auto", "en", "hi", "hinglish"] = "auto"
    translate_to: str | None = Field(default=None, max_length=12)
    visual_analysis: bool = False
    hook_overlay: bool = True
    remove_silence: bool = False
    remove_fillers: bool = False
    keyword_emphasis: bool = False
    emphasis_words: list[str] = Field(default_factory=list, max_length=30)
    progress_bar: bool = False
    use_brand: bool = False
    auto_whole_max_s: int = Field(default=90, ge=15, le=180)
    music_mood: MusicMood = "none"
    music_volume: float = Field(default=0.2, ge=0.05, le=0.6)

    @field_validator("translate_to")
    @classmethod
    def known_language(cls, v: str | None) -> str | None:
        if v in (None, "", "none"):
            return None
        if v not in TRANSLATE_TO:
            raise ValueError("Unsupported caption language")
        return v

    @field_validator("emphasis_words")
    @classmethod
    def short_words(cls, v: list[str]) -> list[str]:
        return [w.strip()[:40] for w in v if w.strip()]

    @model_validator(mode="after")
    def ordered(self) -> ClipOptions:
        if self.min_len > self.max_len:
            self.min_len, self.max_len = self.max_len, self.min_len
        return self


class ClipJobIn(ClipOptions):
    upload_id: str | None = None
    url: str | None = Field(default=None, max_length=2048)
    title: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def one_source(self) -> ClipJobIn:
        if bool(self.upload_id) == bool(self.url):
            raise ValueError("Give either an uploaded file or a link")
        return self


def _brand_snapshot(m: Member) -> dict[str, Any] | None:
    row = db.fetch_one("select * from brand_kits where user_id = %s", [m.user_id])
    if not row:
        return None
    return {
        "logo_key": row["logo_key"],
        "logo_position": row["logo_position"],
        "logo_opacity": float(row["logo_opacity"]),
        "handle": row["handle"],
        "primary_color": row["primary_color"],
        "progress_bar": row["progress_bar"],
    }


def _check_entitlements(m: Member, o: ClipOptions) -> None:
    max_clips = int(limit(m, "max_clips_per_job", 5))
    if o.mode != "captions" and o.num_clips > max_clips:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Your plan makes up to {max_clips} clips per video. Lower the number or upgrade on Pricing.",
        )
    require_feature(m, "clipper")
    if o.mode in ("captions", "auto"):
        require_feature(m, "captions")
    if o.visual_analysis and o.mode != "captions":
        require_feature(m, "visual_analysis")
    if o.aspect != "9:16":
        require_feature(m, "output_formats")
    if o.translate_to:
        require_feature(m, "translation")
    if o.remove_silence or o.remove_fillers:
        require_feature(m, "filler_removal")
    if o.keyword_emphasis:
        require_feature(m, "keyword_emphasis")
    if o.use_brand:
        require_feature(m, "brand_kit")


def _params(m: Member, o: ClipOptions) -> dict[str, Any]:
    params: dict[str, Any] = o.model_dump(
        exclude={
            "caption_style",
            "title",
            "upload_id",
            "url",
            "emphasis_words",
            "use_brand",
            "music_mood",
            "music_volume",
        }
    )
    if o.music_mood != "none":
        params["music"] = {"mood": o.music_mood, "volume": o.music_volume}
    params["caption_style"] = o.caption_style.clean()
    params["language"] = None if o.language == "auto" else o.language
    if o.keyword_emphasis:
        params["emphasis_words"] = o.emphasis_words
    params["watermark"] = bool(limit(m, "watermark", True)) and not has_feature(m, "no_watermark")
    params["max_source_minutes"] = int(limit(m, "max_source_minutes", 60))
    if o.use_brand:
        brand = _brand_snapshot(m)
        if not brand:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Set up your brand kit first (Account → Brand kit)."
            )
        params["brand"] = brand
        params["progress_bar"] = o.progress_bar or bool(brand["progress_bar"])
    return params


def _create(
    m: Member,
    o: ClipOptions,
    *,
    url: str | None,
    upload_id: str | None,
    title: str | None,
    batch: bool = False,
) -> dict[str, Any]:
    params = _params(m, o)
    if upload_id:
        take_completed_upload(upload_id, m.user_id, "source")
        params["upload_id"] = upload_id
    else:
        params["url"] = sanitize_url(url or "")
        params["platform"] = platforms.detect(params["url"]).id
    if batch:
        params["batch"] = True
    default_title = {"captions": "Captioned video", "auto": "Quick video"}.get(o.mode, "Untitled")
    p = db.fetch_one(
        "insert into projects (type, title, created_by, status, meta) values ('clip', %s, %s, 'processing', %s) "
        "returning id",
        [title or default_title, m.user_id, {"options": params, "tool": o.mode}],
    )
    try:
        job = launch(m, "clip", str(p["id"]), params, rate_cost=0 if batch else 1, batch=batch)
    except HTTPException:
        db.execute("delete from projects where id = %s", [p["id"]])
        raise
    return {"project_id": p["id"], "job_id": job["id"], "tokens": job["tokens_charged"]}


@router.post("/clipper/projects", status_code=201)
def create_clip_project(body: ClipJobIn, m: CurrentMember) -> dict:
    _check_entitlements(m, body)
    return _create(m, body, url=body.url, upload_id=body.upload_id, title=body.title)


class BatchIn(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=50)
    options: ClipOptions = ClipOptions()


@router.post("/clipper/batch", status_code=201)
def create_batch(body: BatchIn, m: CurrentMember) -> dict:
    """Many links with the same settings. Each link becomes its own project; they queue and run in turn."""
    urls = list(dict.fromkeys(u.strip() for u in body.urls if u.strip()))
    if not urls:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Paste at least one link")
    cap = int(limit(m, "max_batch", 1))
    if len(urls) > 1:
        require_feature(m, "batch")
    if len(urls) > cap:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Your plan takes up to {cap} links at once. Remove some or upgrade on Pricing.",
        )
    for u in urls:
        sanitize_url(u)  # reject the whole batch up front if any link is invalid
    _check_entitlements(m, body.options)
    check_job_rate(m.user_id, 1)
    created: list[dict[str, Any]] = []
    error = None
    for u in urls:
        try:
            created.append(
                {"url": u, **_create(m, body.options, url=u, upload_id=None, title=None, batch=True)}
            )
        except HTTPException as e:  # e.g. ran out of tokens part-way: keep what was started
            error = {"url": u, "detail": e.detail, "status": e.status_code}
            break
    return {"created": created, "error": error, "requested": len(urls)}


@router.get("/clipper/options")
def clipper_options(m: CurrentMember) -> dict:
    """Choices for the settings panel, with what the user's plan allows."""
    return {
        "languages": [{"code": k, "name": v} for k, v in TRANSLATE_TO.items()],
        "aspects": [
            {"id": "9:16", "label": "Vertical 9:16", "hint": "TikTok, Reels, Shorts", "locked": False},
            *[
                {"id": a, "label": label, "hint": hint, "locked": not has_feature(m, "output_formats")}
                for a, label, hint in (
                    ("1:1", "Square 1:1", "Feed posts"),
                    ("4:5", "Portrait 4:5", "Instagram & Facebook feed"),
                    ("16:9", "Landscape 16:9", "YouTube, X, LinkedIn"),
                )
            ],
        ],
        "platforms": [{"id": p.id, "label": p.label} for _, p in platforms.PLATFORMS],
        "max_batch": int(limit(m, "max_batch", 1)),
        "max_clips": int(limit(m, "max_clips_per_job", 5)),
        "captions_max_minutes": 15,
    }


# ---------------------------------------------------------------- link inspection
class InspectIn(BaseModel):
    url: str = Field(max_length=2048)
    probe: bool = True  # False: platform only (instant); True: also title/length from the site


class _QuietLog:
    """yt-dlp prints errors even with quiet=True; a site refusing a metadata probe is normal here."""

    def debug(self, msg: str) -> None: ...
    def info(self, msg: str) -> None: ...
    def warning(self, msg: str) -> None: ...
    def error(self, msg: str) -> None: ...


def _probe_link(url: str) -> dict[str, Any]:
    """Title/duration/thumbnail via yt-dlp metadata only (no download). Best effort: errors are returned, not raised."""
    try:
        import yt_dlp
        from studio_shared import app_settings

        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": True,
            "socket_timeout": 8,
            "retries": 0,
            "extractor_retries": 0,
            "extract_flat": False,
            "logger": _QuietLog(),
        }
        if proxy := app_settings.proxy():
            opts["proxy"] = proxy
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False) or {}
        return {
            "title": (info.get("title") or "")[:200] or None,
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader") or info.get("channel"),
            "is_live": bool(info.get("is_live")),
        }
    except Exception as e:  # noqa: BLE001
        msg = str(e).strip().splitlines()[-1][:200] if str(e).strip() else "unknown error"
        return {"error": msg}


@router.post("/clipper/inspect")
def inspect_link(body: InspectIn, m: CurrentMember) -> dict:
    """Which platform a link is from (always), plus title/length when the site lets us look (cached 1 h)."""
    url = sanitize_url(body.url)
    p = platforms.detect(url)
    out: dict[str, Any] = {
        "url": url,
        "platform": p.id,
        "label": p.label,
        "short_form": p.short_form,
        "help": platforms.login_help(p).strip() or None,
    }
    key = "inspect:" + hashlib.sha256(url.encode()).hexdigest()[:32]
    try:
        cached = _r().get(key)
    except Exception:  # noqa: BLE001
        cached = None
    if cached:
        meta = json.loads(cached)
    elif not body.probe:
        return out
    else:
        meta = _probe_link(url)
        try:
            _r().setex(key, 3600 if "error" not in meta else 120, json.dumps(meta))
        except Exception:  # noqa: BLE001
            pass
    out.update(meta)
    dur = meta.get("duration")
    if isinstance(dur, (int, float)):
        out["suggested_mode"] = "captions" if dur <= 90 or p.short_form and dur <= 180 else "clips"
        out["too_long"] = dur > int(limit(m, "max_source_minutes", 60)) * 60
    return out


# ---------------------------------------------------------------- re-render
class RerenderIn(BaseModel):
    start: float | None = Field(default=None, ge=0)
    end: float | None = Field(default=None, gt=0)
    caption_style: CaptionStyleIn | None = None
    reframe: Reframe | None = None
    aspect: Aspect | None = None
    music_mood: MusicMood | None = None
    music_volume: float = Field(default=0.2, ge=0.05, le=0.6)


@router.post("/clips/{clip_id}/rerender", status_code=201)
def rerender_clip(clip_id: str, body: RerenderIn, m: CurrentMember) -> dict:
    clip = clip_for(clip_id, m)
    if jobs.active_job_for_project(clip["project_id"], ("clip",)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Clips are still being generated")
    busy = db.fetch_one(
        "select 1 from jobs where kind = 'clip_rerender' and status in ('queued','running') and params->>'clip_id' = %s",
        [clip_id],
    )
    if busy:
        raise HTTPException(status.HTTP_409_CONFLICT, "This clip is already re-rendering")
    s = body.start if body.start is not None else float(clip["start_s"])
    e = body.end if body.end is not None else float(clip["end_s"])
    max_len = 900 if clip["mode"] == "whole" else 300
    if e - s < 3 or e - s > max_len:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Clip length must be between 3 and {max_len} seconds"
        )
    params: dict[str, Any] = {"clip_id": clip_id}
    if body.start is not None or body.end is not None:
        params.update(start=s, end=e)
    if body.caption_style is not None:
        params["caption_style"] = body.caption_style.clean()
    if body.reframe:
        params["reframe"] = body.reframe
    if body.music_mood is not None:
        params["music"] = {"mood": body.music_mood, "volume": body.music_volume}
    if body.aspect and body.aspect != clip["aspect"]:
        if body.aspect != "9:16":
            require_feature(m, "output_formats")
        params["aspect"] = body.aspect
    job = launch(m, "clip_rerender", str(clip["project_id"]), params)
    db.execute("update clips set status = 'queued' where id = %s", [clip_id])
    return job


# ---------------------------------------------------------------- caption files
_MIME = {"srt": "application/x-subrip", "vtt": "text/vtt", "txt": "text/plain"}


@router.get("/clips/{clip_id}/captions.{fmt}")
def clip_captions(clip_id: str, fmt: Literal["srt", "vtt", "txt"], m: CurrentMember) -> Response:
    """The captions exactly as burned into the clip (translated / jump-cut timing included)."""
    from studio_shared.captions_files import render_file

    clip = clip_for(clip_id, m, write=False)
    if not clip.get("words_key"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Captions are available once the clip has rendered")
    try:
        words = json.loads(storage.get_bytes(clip["words_key"]))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Caption file not found") from e
    body = render_file(words, fmt)
    base = (clip.get("filename") or "clip.mp4").rsplit(".", 1)[0]
    suffix = f".{clip['language']}" if clip.get("language") else ""
    return Response(
        body,
        media_type=f"{_MIME[fmt]}; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{base}{suffix}.{fmt}"'},
    )
