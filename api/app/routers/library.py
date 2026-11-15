"""Shared libraries managed by admins: music tracks (by mood), SFX (by tag), custom visual styles."""

from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from studio_shared import db, storage

from ..auth import AdminMember
from .uploads import take_completed_upload

router = APIRouter(prefix="/library", tags=["library"])
Mood = Literal["suspense", "horror", "upbeat", "epic", "funny", "calm", "emotional"]


class MusicIn(BaseModel):
    upload_id: str
    name: str = Field(min_length=1, max_length=100)
    mood: Mood


@router.post("/music", status_code=201)
def add_music(body: MusicIn, admin: AdminMember) -> dict:
    up = take_completed_upload(body.upload_id, admin.user_id, "music")
    return db.fetch_one(
        "insert into music_tracks (name, mood, r2_key, created_by) values (%s,%s,%s,%s) returning *",
        [body.name, body.mood, up["r2_key"], admin.user_id],
    )


@router.delete("/music/{track_id}")
def delete_music(track_id: str, _: AdminMember) -> dict:
    row = db.fetch_one("delete from music_tracks where id = %s returning r2_key", [track_id])
    if row:
        db.execute("update stories set music_track_id = null where music_track_id = %s", [track_id])
        storage.delete(row["r2_key"])
    return {"ok": True}


class SfxIn(BaseModel):
    upload_id: str
    name: str = Field(min_length=1, max_length=100)
    tag: str = Field(min_length=2, max_length=30, pattern=r"^[a-z][a-z0-9-]*$")


@router.post("/sfx", status_code=201)
def add_sfx(body: SfxIn, admin: AdminMember) -> dict:
    up = take_completed_upload(body.upload_id, admin.user_id, "sfx")
    return db.fetch_one(
        "insert into sfx (name, tag, r2_key, created_by) values (%s,%s,%s,%s) returning *",
        [body.name, body.tag, up["r2_key"], admin.user_id],
    )


@router.delete("/sfx/{sfx_id}")
def delete_sfx(sfx_id: str, _: AdminMember) -> dict:
    row = db.fetch_one("delete from sfx where id = %s returning r2_key", [sfx_id])
    if row and not row["r2_key"].startswith("library/sfx/builtin-"):
        storage.delete(row["r2_key"])
    return {"ok": True}


class StyleIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    prompt: str = Field(min_length=10, max_length=1500)
    example_upload_id: str | None = None


@router.post("/styles", status_code=201)
def add_style(body: StyleIn, admin: AdminMember) -> dict:
    sid = re.sub(r"[^a-z0-9]+", "_", body.name.lower()).strip("_")[:40] or "style"
    if db.fetch_one("select 1 from visual_styles where id = %s", [sid]):
        raise HTTPException(status.HTTP_409_CONFLICT, "A style with this name already exists")
    example = (
        take_completed_upload(body.example_upload_id, admin.user_id, "image")["r2_key"]
        if body.example_upload_id
        else None
    )
    return db.fetch_one(
        "insert into visual_styles (id, name, prompt, example_key, builtin, created_by) values (%s,%s,%s,%s,false,%s) returning *",
        [sid, body.name, body.prompt, example, admin.user_id],
    )


@router.delete("/styles/{style_id}")
def delete_style(style_id: str, _: AdminMember) -> dict:
    row = db.fetch_one("select builtin from visual_styles where id = %s", [style_id])
    if row and row["builtin"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Built-in styles can't be deleted")
    db.execute("delete from visual_styles where id = %s", [style_id])
    return {"ok": True}
