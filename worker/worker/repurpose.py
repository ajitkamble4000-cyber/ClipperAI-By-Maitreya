"""Repurpose a video into writing (summary, chapters, quotes, blog post, X thread, LinkedIn post, newsletter), and
keep a searchable copy of every transcript ("search what was said")."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field
from studio_shared import db, storage
from studio_shared.gemini import AIError, CallContext, available, get_client

from .pipeline import JobContext, Pipeline, Step, StepFailed
from .transcribe.base import Transcript


# ---------------------------------------------------------------- transcript index
def index_transcript(project_id: str, t: Transcript) -> None:
    segs = [
        {"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()}
        for s in t.segments
        if s.text.strip()
    ]
    text = " ".join(s["text"] for s in segs)[:200_000]
    db.execute(
        """insert into project_transcripts (project_id, language, text, segments) values (%s,%s,%s,%s)
           on conflict (project_id) do update set language = excluded.language, text = excluded.text,
                  segments = excluded.segments, updated_at = now()""",
        [project_id, t.language, text, db.jsonb(segs)],
    )


# ---------------------------------------------------------------- repurpose
class Chapter(BaseModel):
    time: float = Field(description="Start time in seconds")
    title: str = Field(description="Short chapter title")


class Repurposed(BaseModel):
    summary: str = Field(description="3-5 sentence summary")
    chapters: list[Chapter] = Field(description="4-10 chapters covering the whole video, the first at 0")
    quotes: list[str] = Field(description="3-6 short quotable lines, word for word from the video")
    blog_post: str = Field(description="A 400-700 word blog post in Markdown with a title and subheadings")
    x_thread: list[str] = Field(description="5-8 posts for an X/Twitter thread, each under 270 characters")
    linkedin_post: str = Field(description="A LinkedIn post of 120-220 words with line breaks")
    newsletter: str = Field(
        description="A short newsletter section (120-200 words) with a subject line first"
    )
    keywords: list[str] = Field(description="6-10 keywords / tags")


SYSTEM = (
    "You turn video transcripts into ready-to-publish writing. Stay faithful to what was actually said, keep the "
    "speaker's voice, never invent facts or numbers, and write in the language of the transcript."
)


def _source(ctx: JobContext) -> tuple[str, Transcript | None, str]:
    p = db.fetch_one("select * from projects where id = %s", [ctx.project_id])
    if not p:
        raise StepFailed("Project not found")
    if p["type"] == "clip":
        key = (p["meta"] or {}).get("transcript_key")
        if not key:
            raise StepFailed("This video hasn't been transcribed yet.")
        t = Transcript.from_json(json.loads(storage.get_bytes(key)))
        lines = []
        for s in t.segments:
            mm, ss = divmod(int(s.start), 60)
            lines.append(f"[{mm}:{ss:02d}] {s.text.strip()}")
        return p["title"], t, "\n".join(lines)[:14000]
    scenes = db.fetch_all("select narration from scenes where project_id = %s order by idx", [ctx.project_id])
    text = "\n".join(s["narration"] or "" for s in scenes)
    if not text.strip():
        raise StepFailed("This story has no script yet.")
    return p["title"], None, text[:14000]


def _fmt_time(t: float) -> str:
    t = max(0, int(t))
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def step_repurpose(ctx: JobContext) -> dict[str, Any]:
    title, t, text = _source(ctx)
    if t is not None:
        index_transcript(ctx.project_id, t)
    if not available():
        raise StepFailed(
            "No AI text provider is set up. Ask the owner to add one in Settings → AI providers."
        )
    gem = get_client(CallContext(ctx.user_id, ctx.project_id, ctx.job_id))
    ctx.progress(0.2, "Reading the video")
    try:
        r = gem.generate_json(
            f"Title: {title}\n\nTranscript:\n{text}", Repurposed, system=SYSTEM, temperature=0.6
        )
    except AIError as e:
        raise StepFailed(f"The AI couldn't write this right now: {e}") from e
    duration = t.duration if t is not None else None
    chapters = sorted(
        (
            {"time": max(0.0, float(c.time)), "title": c.title.strip()[:80]}
            for c in r.chapters
            if c.title.strip()
        ),
        key=lambda c: c["time"],
    )
    if duration:
        chapters = [c for c in chapters if c["time"] < duration]
    if chapters:
        chapters[0]["time"] = 0.0  # YouTube needs the first chapter at 0:00
    out = {
        "summary": r.summary.strip(),
        "chapters": chapters,
        "chapters_text": "\n".join(f"{_fmt_time(c['time'])} {c['title']}" for c in chapters),
        "quotes": [q.strip().strip('"') for q in r.quotes if q.strip()][:6],
        "blog_post": r.blog_post.strip(),
        "x_thread": [x.strip()[:280] for x in r.x_thread if x.strip()][:8],
        "linkedin_post": r.linkedin_post.strip(),
        "newsletter": r.newsletter.strip(),
        "keywords": [k.strip().lstrip("#") for k in r.keywords if k.strip()][:10],
    }
    db.execute("update projects set repurpose = %s where id = %s", [db.jsonb(out), ctx.project_id])
    return {"sections": list(out)}


def build_repurpose(params: dict) -> Pipeline:
    return Pipeline(
        [Step("repurpose", step_repurpose, label="Writing")], finalize=lambda ctx: ctx.outputs["repurpose"]
    )
