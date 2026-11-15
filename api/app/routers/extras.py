"""Creator extras: templates, AI thumbnails (covers) and title/hashtag ideas for clips and stories."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from studio_shared import db

from ..access import clip_for, project_for
from ..auth import CurrentMember
from ..plans import launch, require_feature

router = APIRouter(tags=["extras"])

MAX_TEMPLATES = 50


# ---------------------------------------------------------------- templates
@router.get("/templates")
def list_templates(m: CurrentMember, kind: Literal["clip", "story"] = "clip") -> list[dict]:
    """Built-in templates (for everyone) followed by your own."""
    return db.fetch_all(
        """select id, kind, name, settings, (user_id is null) as builtin, created_at from templates
            where kind = %s and (user_id is null or user_id = %s)
            order by (user_id is null) desc, created_at""",
        [kind, m.user_id],
    )


class TemplateIn(BaseModel):
    kind: Literal["clip", "story"]
    name: str = Field(min_length=1, max_length=60)
    settings: dict[str, Any]


@router.post("/templates", status_code=201)
def save_template(body: TemplateIn, m: CurrentMember) -> dict:
    require_feature(m, "templates")
    n = db.fetch_one("select count(*) as n from templates where user_id = %s", [m.user_id])["n"]
    if n >= MAX_TEMPLATES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"You can keep up to {MAX_TEMPLATES} templates. Delete one first."
        )
    settings = {
        k: v for k, v in body.settings.items() if k not in ("url", "upload_id", "title", "brand", "watermark")
    }
    if len(str(settings)) > 8000:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Template is too large")
    return db.fetch_one(
        "insert into templates (kind, name, settings, user_id, created_by) values (%s,%s,%s,%s,%s) "
        "returning id, kind, name, settings, false as builtin, created_at",
        [body.kind, body.name.strip(), db.jsonb(settings), m.user_id, m.user_id],
    )


@router.delete("/templates/{template_id}")
def delete_template(template_id: str, m: CurrentMember) -> dict:
    try:
        row = db.fetch_one(
            "delete from templates where id = %s and user_id = %s returning id", [template_id, m.user_id]
        )
    except Exception as e:  # noqa: BLE001 - bad uuid
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found") from e
    if not row:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Template not found (built-in templates can't be deleted)"
        )
    return {"ok": True}


# ---------------------------------------------------------------- thumbnails & title ideas
class ThumbIn(BaseModel):
    style: Literal["frame", "ai"] = "frame"
    text: str | None = Field(default=None, max_length=80)


def _busy(kind: str, key: str, value: str) -> None:
    if db.fetch_one(
        f"select 1 from jobs where kind = %s and status in ('queued','running') and params->>'{key}' = %s",
        [kind, value],
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "Already working on it")


@router.post("/clips/{clip_id}/thumbnail", status_code=201)
def clip_thumbnail(clip_id: str, body: ThumbIn, m: CurrentMember) -> dict:
    require_feature(m, "thumbnails")
    clip = clip_for(clip_id, m)
    if clip["status"] != "ready":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The clip isn't ready yet")
    _busy("thumbnail", "clip_id", clip_id)
    return launch(
        m, "thumbnail", str(clip["project_id"]), {"clip_id": clip_id, **body.model_dump()}, {"count": 1}
    )


@router.post("/story/{project_id}/thumbnail", status_code=201)
def story_thumbnail(project_id: str, body: ThumbIn, m: CurrentMember) -> dict:
    require_feature(m, "thumbnails")
    p = project_for(project_id, m)
    if p["type"] != "story":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Not a story")
    _busy("thumbnail", "story_id", project_id)
    return launch(m, "thumbnail", project_id, {"story_id": project_id, **body.model_dump()}, {"count": 1})


@router.post("/clips/{clip_id}/ideas", status_code=201)
def clip_ideas(clip_id: str, m: CurrentMember) -> dict:
    require_feature(m, "title_variants")
    clip = clip_for(clip_id, m)
    _busy("title_variants", "clip_id", clip_id)
    return launch(m, "title_variants", str(clip["project_id"]), {"clip_id": clip_id}, {"count": 1})


@router.post("/story/{project_id}/ideas", status_code=201)
def story_ideas(project_id: str, m: CurrentMember) -> dict:
    require_feature(m, "title_variants")
    p = project_for(project_id, m)
    if p["type"] != "story":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Not a story")
    _busy("title_variants", "story_id", project_id)
    return launch(m, "title_variants", project_id, {"story_id": project_id}, {"count": 1})
