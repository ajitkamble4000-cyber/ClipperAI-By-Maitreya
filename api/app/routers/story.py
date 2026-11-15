"""Story Studio: create stories, generate scripts, AI scene edits. Storyboard text edits go straight to
Supabase from the browser (RLS column grants); anything that needs Gemini or the queue comes here."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from studio_shared import db, jobs

from ..access import project_for, scene_for
from ..auth import CurrentMember, Member
from ..queue import enqueue
from ..ratelimit import check_job_rate

router = APIRouter(tags=["story"])

Genre = Literal["what_if", "scary", "funny", "facts", "motivational", "history"]
Language = Literal["en", "hi", "hinglish"]
SpeakingStyle = Literal["dramatic", "calm", "excited", "creepy_whisper"]


class StoryIn(BaseModel):
    idea: str = Field(min_length=3, max_length=8000)
    input_mode: Literal["idea", "script"] = "idea"
    genre: Genre = "what_if"
    visual_style: str = Field(default="realistic_3d", max_length=60)
    length_s: Literal[30, 45, 60, 90] = 45
    language: Language = "en"
    voice: str | None = Field(default=None, max_length=40)
    speaking_style: SpeakingStyle = "dramatic"
    generate: bool = True


def story_or_404(project_id: str, m: Member) -> dict[str, Any]:
    project_for(project_id, m)
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


def start(kind: str, project_id: str, params: dict[str, Any], user_id: str) -> dict[str, Any]:
    check_job_rate(user_id)
    job = jobs.create_job(kind, project_id=project_id, params=params, user_id=user_id)
    enqueue(job)
    return job


@router.post("/story/projects", status_code=201)
def create_story(body: StoryIn, m: CurrentMember) -> dict:
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
    out: dict[str, Any] = {"project_id": p["id"]}
    if body.generate:
        out["job_id"] = start("story_script", str(p["id"]), {}, m.user_id)["id"]
    return out


AI_KINDS = ("story_script", "story_scene_ai")


@router.post("/story/{project_id}/script", status_code=201)
def regenerate_script(project_id: str, m: CurrentMember) -> dict:
    story_or_404(project_id, m)
    busy(project_id, AI_KINDS)
    return start("story_script", project_id, {}, m.user_id)


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
        m.user_id,
    )


@router.post("/story/{project_id}/hook", status_code=201)
def stronger_hook(project_id: str, m: CurrentMember) -> dict:
    story_or_404(project_id, m)
    busy(project_id, AI_KINDS)
    return start("story_scene_ai", project_id, {"op": "hook"}, m.user_id)


@router.get("/story/presets")
def story_presets(_: CurrentMember) -> dict:
    styles = db.fetch_all(
        "select id, name, example_key, builtin from visual_styles order by builtin desc, name"
    )
    return {"visual_styles": styles}
