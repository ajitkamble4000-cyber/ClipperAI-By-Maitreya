"""Clipper: create a clip project from an upload or a link; re-render a clip."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from studio_shared import db, jobs

from ..auth import CurrentMember
from ..queue import enqueue
from ..ratelimit import check_job_rate
from ..validation import sanitize_url
from .uploads import take_completed_upload

router = APIRouter(tags=["clipper"])

Reframe = Literal["face", "action", "center", "blur"]
ContentType = Literal["podcast", "sports", "gaming", "interview", "other"]


class CaptionStyleIn(BaseModel):
    preset: Literal["bold_pop", "karaoke", "minimal", "boxed", "horror", "none"] = "bold_pop"
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


class ClipJobIn(BaseModel):
    upload_id: str | None = None
    url: str | None = Field(default=None, max_length=2048)
    num_clips: int = Field(default=5, ge=1, le=20)
    min_len: int = Field(default=20, ge=15, le=180)
    max_len: int = Field(default=60, ge=15, le=180)
    content_type: ContentType = "podcast"
    reframe: Reframe = "face"
    caption_style: CaptionStyleIn = CaptionStyleIn()
    language: Literal["auto", "en", "hi", "hinglish"] = "auto"
    visual_analysis: bool = False
    hook_overlay: bool = True
    title: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def one_source(self) -> ClipJobIn:
        if bool(self.upload_id) == bool(self.url):
            raise ValueError("Give either an uploaded file or a link")
        if self.min_len > self.max_len:
            self.min_len, self.max_len = self.max_len, self.min_len
        return self


@router.post("/clipper/projects", status_code=201)
def create_clip_project(body: ClipJobIn, m: CurrentMember) -> dict:
    check_job_rate(m.user_id)
    params: dict[str, Any] = body.model_dump(exclude={"caption_style", "title", "upload_id", "url"})
    params["caption_style"] = body.caption_style.clean()
    params["language"] = None if body.language == "auto" else body.language
    if body.upload_id:
        take_completed_upload(body.upload_id, m.user_id, "source")
        params["upload_id"] = body.upload_id
    else:
        params["url"] = sanitize_url(body.url or "")
    p = db.fetch_one(
        "insert into projects (type, title, created_by, status, meta) values ('clip', %s, %s, 'processing', %s) "
        "returning id",
        [body.title or "Untitled", m.user_id, {"options": params}],
    )
    job = jobs.create_job("clip", project_id=p["id"], params=params, user_id=m.user_id)
    enqueue(job)
    return {"project_id": p["id"], "job_id": job["id"]}


class RerenderIn(BaseModel):
    start: float | None = Field(default=None, ge=0)
    end: float | None = Field(default=None, gt=0)
    caption_style: CaptionStyleIn | None = None
    reframe: Reframe | None = None


@router.post("/clips/{clip_id}/rerender", status_code=201)
def rerender_clip(clip_id: str, body: RerenderIn, m: CurrentMember) -> dict:
    clip = db.fetch_one("select id, project_id, start_s, end_s from clips where id = %s", [clip_id])
    if not clip:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Clip not found")
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
    if e - s < 3 or e - s > 300:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Clip length must be between 3 and 300 seconds")
    check_job_rate(m.user_id)
    params: dict[str, Any] = {"clip_id": clip_id}
    if body.start is not None or body.end is not None:
        params.update(start=s, end=e)
    if body.caption_style is not None:
        params["caption_style"] = body.caption_style.clean()
    if body.reframe:
        params["reframe"] = body.reframe
    db.execute("update clips set status = 'queued' where id = %s", [clip_id])
    job = jobs.create_job("clip_rerender", project_id=clip["project_id"], params=params, user_id=m.user_id)
    enqueue(job)
    return job
