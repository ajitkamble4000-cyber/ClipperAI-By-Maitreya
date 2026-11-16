"""Editing: fix caption words (then re-render), MP3/GIF exports, compilations of several clips."""

from __future__ import annotations

import json
import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from studio_shared import db, jobs, storage
from studio_shared.captions_files import cues, spread

from ..access import clip_for, project_for
from ..auth import CurrentMember
from ..plans import launch

router = APIRouter(tags=["editing"])


def _words(clip: dict) -> list[dict]:
    if not clip.get("words_key"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Captions are available once the clip has rendered")
    try:
        return json.loads(storage.get_bytes(clip["words_key"]))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Caption file not found") from e


@router.get("/clips/{clip_id}/cues")
def get_cues(clip_id: str, m: CurrentMember) -> list[dict]:
    """The captions as editable lines (start, end, text)."""
    clip = clip_for(clip_id, m)
    return [{"start": a, "end": b, "text": t} for a, b, t in cues(_words(clip), per_line=6)]


class Cue(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str = Field(max_length=200)


class CuesIn(BaseModel):
    cues: list[Cue] = Field(min_length=1, max_length=3000)


@router.post("/clips/{clip_id}/captions", status_code=201)
def save_cues(clip_id: str, body: CuesIn, m: CurrentMember) -> dict:
    """Save fixed caption text and re-render the captions (the cut stays the same)."""
    clip = clip_for(clip_id, m)
    if clip["status"] != "ready":
        raise HTTPException(status.HTTP_409_CONFLICT, "Wait until the clip has finished rendering")
    if jobs.active_job_for_project(clip["project_id"], ("clip",)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Clips are still being generated")
    limit = float(clip["duration_s"] or 0) + 1.0
    words: list[dict] = []
    last = 0.0
    for c in sorted(body.cues, key=lambda c: c.start):
        if c.end <= c.start or c.end > limit:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "A caption line has invalid timing")
        start = max(c.start, last)
        words.extend(spread(" ".join(c.text.split()), start, c.end))
        last = c.end
    key = f"projects/{clip['project_id']}/clips/{clip['id']}/edited-{uuid.uuid4().hex[:8]}.json"
    storage.put_bytes(key, json.dumps(words).encode(), "application/json")
    old = clip.get("words_key")
    db.execute("update clips set words_key = %s where id = %s", [key, clip_id])
    if old and old != key:
        storage.delete(old)
    job = launch(m, "clip_rerender", str(clip["project_id"]), {"clip_id": clip_id, "keep_words": True})
    db.execute("update clips set status = 'queued' where id = %s", [clip_id])
    return {"job_id": job["id"], "words": len(words)}


class ExportIn(BaseModel):
    format: Literal["mp3", "gif"]


@router.post("/clips/{clip_id}/export", status_code=201)
def export_clip(clip_id: str, body: ExportIn, m: CurrentMember) -> dict:
    clip = clip_for(clip_id, m)
    if clip["status"] != "ready":
        raise HTTPException(status.HTTP_409_CONFLICT, "The clip isn't ready yet")
    return launch(m, "clip_export", str(clip["project_id"]), {"clip_id": clip_id, "format": body.format}, {})


class CompilationIn(BaseModel):
    clip_ids: list[str] = Field(min_length=2, max_length=30)
    transition: Literal["cut", "fade"] = "cut"
    title: str = Field(default="", max_length=80)


@router.post("/clipper/projects/{project_id}/compilation", status_code=201)
def compilation(project_id: str, body: CompilationIn, m: CurrentMember) -> dict:
    p = project_for(project_id, m)
    if p["type"] != "clip":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Compilations are made from clips")
    try:
        rows = db.fetch_all(
            "select id, status, aspect from clips where project_id = %s and id = any(%s::uuid[])",
            [project_id, body.clip_ids],
        )
    except Exception as e:  # noqa: BLE001 - bad uuid
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown clip") from e
    if len(rows) != len(set(body.clip_ids)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pick clips from this project")
    if any(r["status"] != "ready" for r in rows):
        raise HTTPException(status.HTTP_409_CONFLICT, "All picked clips must be finished")
    if len({r["aspect"] for r in rows}) > 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "All picked clips need the same format")
    params = {"clip_ids": body.clip_ids, "transition": body.transition, "title": body.title or p["title"]}
    return launch(m, "clip_compile", project_id, params, {})
