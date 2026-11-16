"""Repurpose a video into writing, and search what was said across everything you can see."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response, status
from studio_shared import db, jobs

from ..access import project_for
from ..auth import CurrentMember
from ..plans import launch

router = APIRouter(tags=["repurpose"])


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50] or "video"


@router.post("/projects/{project_id}/repurpose", status_code=201)
def start_repurpose(project_id: str, m: CurrentMember) -> dict:
    project_for(project_id, m, write=True)
    if jobs.active_job_for_project(project_id, ("repurpose",)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Already writing for this video")
    return launch(m, "repurpose", project_id, {}, {})


@router.get("/projects/{project_id}/repurpose")
def get_repurpose(project_id: str, m: CurrentMember) -> dict:
    return project_for(project_id, m).get("repurpose") or {}


def to_markdown(title: str, r: dict[str, Any]) -> str:
    parts = [f"# {title}", ""]
    if r.get("summary"):
        parts += ["## Summary", "", r["summary"], ""]
    if r.get("chapters_text"):
        parts += ["## Chapters (paste into the YouTube description)", "", r["chapters_text"], ""]
    if r.get("quotes"):
        parts += ["## Quotes", "", *[f"> {q}" for q in r["quotes"]], ""]
    if r.get("x_thread"):
        parts += ["## X / Twitter thread", "", *[f"{i}. {x}" for i, x in enumerate(r["x_thread"], 1)], ""]
    if r.get("linkedin_post"):
        parts += ["## LinkedIn post", "", r["linkedin_post"], ""]
    if r.get("newsletter"):
        parts += ["## Newsletter", "", r["newsletter"], ""]
    if r.get("keywords"):
        parts += ["## Keywords", "", ", ".join(r["keywords"]), ""]
    if r.get("blog_post"):
        parts += ["---", "", r["blog_post"], ""]
    return "\n".join(parts)


@router.get("/projects/{project_id}/repurpose.md")
def download_repurpose(project_id: str, m: CurrentMember) -> Response:
    p = project_for(project_id, m)
    r = p.get("repurpose") or {}
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nothing written yet")
    name = f"{slug(p['title'] or 'video')}-writeup.md"
    return Response(
        to_markdown(p["title"], r),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/search/transcripts")
def search_transcripts(m: CurrentMember, q: str = Query(min_length=2, max_length=100)) -> list[dict]:
    """Find the moment something was said, across every video you can see."""
    rows = db.fetch_all(
        """select pt.project_id, p.title, p.type, p.thumbnail_key, pt.segments,
                  ts_headline('simple', pt.text, query, 'MaxWords=20, MinWords=8, StartSel=<<, StopSel=>>') as snippet,
                  ts_rank(pt.tsv, query) as rank
             from project_transcripts pt
             join projects p on p.id = pt.project_id
             left join members cm on cm.user_id = p.created_by,
                  websearch_to_tsquery('simple', %(q)s) query
            where pt.tsv @@ query
              and (p.created_by = %(uid)s or %(admin)s or (%(team)s and cm.team is not null)
                   or exists (select 1 from project_members pm
                               where pm.project_id = p.id and pm.user_id = %(uid)s))
            order by rank desc, p.updated_at desc limit 20""",
        {"q": q, "uid": m.user_id, "admin": m.is_admin, "team": m.team is not None},
    )
    terms = [t for t in re.findall(r"\w+", q.lower()) if len(t) > 1]
    out = []
    for r in rows:
        at = next((s["start"] for s in r["segments"] if any(t in s["text"].lower() for t in terms)), None)
        out.append(
            {
                "project_id": r["project_id"],
                "title": r["title"],
                "type": r["type"],
                "thumbnail_key": r["thumbnail_key"],
                "snippet": r["snippet"],
                "at": at,
            }
        )
    return out
