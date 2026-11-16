"""Story Studio: create stories, generate scripts, AI scene edits. Storyboard text edits go straight to
Supabase from the browser (RLS column grants); anything that needs Gemini or the queue comes here."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from studio_shared import db, jobs
from studio_shared.config import REPO_ROOT

from ..access import project_for, scene_for
from ..auth import CurrentMember, Member
from ..plans import launch

router = APIRouter(tags=["story"])


@lru_cache
def genre_ids() -> frozenset[str]:
    return frozenset(json.loads((REPO_ROOT / "shared" / "presets" / "story.json").read_text())["genres"])


Language = Literal["en", "hi", "hinglish"]
SpeakingStyle = Literal["dramatic", "calm", "excited", "creepy_whisper"]


class StorySettings(BaseModel):
    """How a story looks and sounds (shared by single and batch creation)."""

    genre: str = Field(default="what_if", max_length=40)
    visual_style: str = Field(default="realistic_3d", max_length=60)
    length_s: Literal[30, 45, 60, 90] = 45
    language: Language = "en"
    voice: str | None = Field(default=None, max_length=40)
    speaking_style: SpeakingStyle = "dramatic"

    @field_validator("genre")
    @classmethod
    def known_genre(cls, v: str) -> str:
        if v not in genre_ids():
            raise ValueError("Unknown genre")
        return v


class StoryIn(StorySettings):
    idea: str = Field(min_length=3, max_length=8000)
    input_mode: Literal["idea", "script"] = "idea"
    generate: bool = True


def story_or_404(project_id: str, m: Member, write: bool = True) -> dict[str, Any]:
    project_for(project_id, m, write=write)
    row = db.fetch_one(
        "select s.*, p.created_by from stories s join projects p on p.id = s.project_id where s.project_id = %s",
        [project_id],
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Story not found")
    return row


def busy(project_id: str, kinds: tuple[str, ...]) -> None:
    if jobs.active_job_for_project(project_id, kinds):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Another AI task is already running on this story. Wait for it to finish.",
        )


def start(
    kind: str, project_id: str, params: dict[str, Any], m: Member, quote_params: dict[str, Any] | None = None
) -> dict[str, Any]:
    job = launch(m, kind, project_id, params, quote_params)
    return job


def _insert_story(body: StoryIn, m: Member) -> str:
    if not db.fetch_one("select 1 from visual_styles where id = %s", [body.visual_style]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown visual style")
    title = body.idea.strip().splitlines()[0][:80] if body.input_mode == "idea" else "Untitled story"
    with db.transaction() as c:
        p = c.execute(
            "insert into projects (type, title, created_by, status) values ('story', %s, %s, 'draft') returning id",
            [title, m.user_id],
        ).fetchone()
        c.execute(
            """insert into stories (project_id, idea, input_mode, genre, visual_style, length_s, language, voice,
                                    speaking_style, updated_by)
               values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            [
                p["id"],
                body.idea.strip(),
                body.input_mode,
                body.genre,
                body.visual_style,
                body.length_s,
                body.language,
                body.voice,
                body.speaking_style,
                m.user_id,
            ],
        )
    return str(p["id"])


@router.post("/story/projects", status_code=201)
def create_story(body: StoryIn, m: CurrentMember) -> dict:
    pid = _insert_story(body, m)
    out: dict[str, Any] = {"project_id": pid}
    if body.generate:
        out["job_id"] = start("story_script", pid, {}, m)["id"]
    return out


class StoryBatchIn(BaseModel):
    ideas: list[str] = Field(min_length=1, max_length=50)
    settings: StorySettings = StorySettings()


@router.post("/story/batch", status_code=201)
def create_story_batch(body: StoryBatchIn, m: CurrentMember) -> dict:
    """Many topics at once (Business): each becomes a story and its script is written in the background."""
    from ..plans import limit, require_feature
    from ..ratelimit import check_job_rate

    ideas = list(dict.fromkeys(i.strip() for i in body.ideas if len(i.strip()) >= 3))
    if not ideas:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Write at least one topic")
    if len(ideas) > 1:
        require_feature(m, "batch")
    cap = int(limit(m, "max_batch", 1))
    if len(ideas) > cap:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Your plan takes up to {cap} topics at once.")
    check_job_rate(m.user_id, 1)
    created: list[dict[str, Any]] = []
    error = None
    for idea in ideas:
        story = StoryIn(**body.settings.model_dump(), idea=idea[:8000], input_mode="idea")
        pid = _insert_story(story, m)
        try:
            job = launch(m, "story_script", pid, {}, rate_cost=0, batch=True)
        except HTTPException as e:  # out of tokens part-way: keep the story as a draft, stop here
            error = {"idea": idea, "detail": e.detail, "status": e.status_code}
            created.append({"idea": idea, "project_id": pid, "job_id": None})
            break
        created.append({"idea": idea, "project_id": pid, "job_id": job["id"]})
    return {"created": created, "error": error, "requested": len(ideas)}


AI_KINDS = ("story_script", "story_scene_ai")


@router.post("/story/{project_id}/script", status_code=201)
def regenerate_script(project_id: str, m: CurrentMember) -> dict:
    story_or_404(project_id, m)
    busy(project_id, AI_KINDS)
    return start("story_script", project_id, {}, m)


class RewriteIn(BaseModel):
    instruction: str | None = Field(default=None, max_length=500)


@router.post("/scenes/{scene_id}/rewrite", status_code=201)
def rewrite_scene(scene_id: str, body: RewriteIn, m: CurrentMember) -> dict:
    sc = scene_for(scene_id, m)
    if not sc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scene not found")
    busy(str(sc["project_id"]), AI_KINDS)
    return start(
        "story_scene_ai",
        str(sc["project_id"]),
        {"op": "rewrite", "scene_id": scene_id, "instruction": body.instruction},
        m,
    )


@router.post("/story/{project_id}/hook", status_code=201)
def stronger_hook(project_id: str, m: CurrentMember) -> dict:
    story_or_404(project_id, m)
    busy(project_id, AI_KINDS)
    return start("story_scene_ai", project_id, {"op": "hook"}, m)


@router.get("/story/presets")
def story_presets(_: CurrentMember) -> dict:
    styles = db.fetch_all(
        "select id, name, example_key, builtin from visual_styles order by builtin desc, name"
    )
    return {"visual_styles": styles}
