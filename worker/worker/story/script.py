"""Gemini script writing for Story Studio: full script, scene rewrites, stronger hook."""

from __future__ import annotations

from typing import Any

from studio_shared import db
from studio_shared.gemini import CallContext, get_client

from ..pipeline import JobContext, Pipeline, Step, StepFailed
from . import presets
from .schema import HookRewrite, SceneRewrite, StoryScript

SYSTEM = """You are a top YouTube Shorts scriptwriter and storyboard artist.
You write hook-first, tightly paced vertical videos that keep viewers watching to the end.
Rules:
- The first sentence is the hook: it must stop the scroll in under 3 seconds.
- Every scene is one image + one or two spoken sentences. No filler, no "in this video".
- Narration is spoken words only (no stage directions, no emojis, no hashtags).
- Image prompts describe a single striking vertical (9:16) frame, consistent in style across scenes, with no text,
  captions, logos or watermarks in the image. Name recurring characters exactly as in the character list.
- Pick camera motions that fit the beat: zoom-in for tension or reveals, zoom-out for scale, pans for travel or
  scanning, shake only for impacts and shocks, static for calm.
"""


def _story(project_id: str) -> dict[str, Any]:
    row = db.fetch_one("select * from stories where project_id = %s", [project_id])
    if not row:
        raise StepFailed("Story not found")
    return row


def build_script_prompt(st: dict[str, Any]) -> str:
    g = presets.genre(st["genre"])
    lo, hi = presets.target_scenes(st["length_s"])
    words = int(st["length_s"] * presets.catalog()["words_per_second"])
    style = presets.visual_style_prompt(st["visual_style"])
    parts = [
        f"Genre: {g['label']}. {g['prompt']}",
        f"Hook style: {g['hook']}",
        presets.language_instruction(st["language"]),
        f"Target length: about {st['length_s']} seconds of narration (about {words} words total), "
        f"split into {lo}-{hi} scenes.",
        f"Visual style for every image prompt (append the essence of it to each prompt): {style}",
        "Title, hook text, description and hashtags should be in the same language as the narration "
        "(hashtags may be English).",
    ]
    if st["input_mode"] == "script":
        parts.append(
            "The user wrote the script below. Keep their narration wording (you may fix obvious typos), split it "
            "into scenes, and write image prompts, camera motions, durations and SFX for each scene.\n\nSCRIPT:\n"
            + st["idea"]
        )
    else:
        parts.append(f"Story idea: {st['idea']}")
    return "\n\n".join(parts)


def _ctx(ctx: JobContext) -> CallContext:
    return CallContext(ctx.user_id, ctx.project_id, ctx.job_id)


def write_script(ctx: JobContext) -> dict[str, Any]:
    st = _story(ctx.project_id)
    if not st["idea"].strip():
        raise StepFailed("Write an idea or paste a script first.")
    gem = get_client(_ctx(ctx))
    ctx.progress(0.1, "Writing the script")
    script = gem.generate_json(build_script_prompt(st), StoryScript, system=SYSTEM, temperature=0.9)
    if len(script.scenes) < 3:
        raise StepFailed("Gemini returned too few scenes. Try again or make the idea more specific.")
    scenes = script.scenes[:15]
    ctx.progress(0.8, "Saving storyboard")
    with db.transaction() as c:
        c.execute("delete from scenes where project_id = %s", [ctx.project_id])
        for i, s in enumerate(scenes):
            c.execute(
                """insert into scenes (project_id, idx, narration, image_prompt, camera_motion, duration_estimate,
                                       sfx_suggestion, on_screen_text, characters)
                   values (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                [
                    ctx.project_id,
                    i,
                    s.narration.strip(),
                    s.image_prompt.strip(),
                    s.camera_motion,
                    max(1.5, min(15.0, s.duration_estimate)),
                    s.sfx_suggestion.strip()[:80],
                    s.on_screen_text.strip()[:40],
                    [c.strip()[:60] for c in s.characters][:6],
                ],
            )
        locked = {
            r["name"].lower()
            for r in c.execute(
                "select name from characters where project_id = %s and locked", [ctx.project_id]
            ).fetchall()
        }
        c.execute("delete from characters where project_id = %s and not locked", [ctx.project_id])
        for ch in script.characters[:6]:
            if ch.name.lower() not in locked:
                c.execute(
                    "insert into characters (project_id, name, description) values (%s,%s,%s)",
                    [ctx.project_id, ch.name.strip()[:60], ch.description.strip()],
                )
        tags = [
            h if h.startswith("#") else f"#{h}"
            for h in (t.strip().replace(" ", "") for t in script.hashtags)
            if len(h) > 1
        ]
        c.execute(
            "update stories set title = %s, hook_text = %s, description = %s, hashtags = %s where project_id = %s",
            [
                script.title.strip()[:100],
                script.hook_text.strip()[:60],
                script.description.strip(),
                tags[:8],
                ctx.project_id,
            ],
        )
        c.execute(
            "update projects set title = %s, status = 'storyboard' where id = %s",
            [script.title.strip()[:120] or "Untitled story", ctx.project_id],
        )
    return {"scenes": len(scenes), "characters": len(script.characters)}


def _script_context(project_id: str) -> str:
    rows = db.fetch_all("select idx, narration from scenes where project_id = %s order by idx", [project_id])
    return "\n".join(f"Scene {r['idx'] + 1}: {r['narration']}" for r in rows)


def scene_ai(ctx: JobContext) -> dict[str, Any]:
    p = ctx.params
    st = _story(ctx.project_id)
    g = presets.genre(st["genre"])
    gem = get_client(_ctx(ctx))
    style = presets.visual_style_prompt(st["visual_style"])
    lang = presets.language_instruction(st["language"])
    if p["op"] == "rewrite":
        sc = db.fetch_one(
            "select * from scenes where id = %s and project_id = %s", [p["scene_id"], ctx.project_id]
        )
        if not sc:
            raise StepFailed("Scene not found")
        prompt = (
            f"Genre: {g['label']}. {g['prompt']}\n{lang}\nVisual style: {style}\n\n"
            f"Full script for context:\n{_script_context(ctx.project_id)}\n\n"
            f"Rewrite scene {sc['idx'] + 1} so it is more gripping and flows from the previous scene into the next. "
            f"Keep about the same length ({len(sc['narration'].split())} words).\n"
            f"Current narration: {sc['narration']}\nCurrent image prompt: {sc['image_prompt']}\n"
            + (f"Extra instruction from the editor: {p['instruction']}\n" if p.get("instruction") else "")
        )
        out = gem.generate_json(prompt, SceneRewrite, system=SYSTEM, temperature=0.9)
        db.execute(
            "update scenes set narration = %s, image_prompt = %s, camera_motion = %s, sfx_suggestion = %s, "
            "on_screen_text = %s where id = %s",
            [
                out.narration.strip(),
                out.image_prompt.strip(),
                out.camera_motion,
                out.sfx_suggestion[:80],
                out.on_screen_text[:40],
                sc["id"],
            ],
        )
        return {"scene_id": str(sc["id"])}
    if p["op"] == "hook":
        first = db.fetch_one(
            "select * from scenes where project_id = %s order by idx limit 1", [ctx.project_id]
        )
        if not first:
            raise StepFailed("The storyboard is empty.")
        prompt = (
            f"Genre: {g['label']}. Hook style: {g['hook']}\n{lang}\n\nFull script:\n{_script_context(ctx.project_id)}\n\n"
            "Make the opening much stronger: rewrite the FIRST scene's narration so the first sentence is an "
            "irresistible hook (under 3 seconds to say), rewrite its image prompt to be the most striking frame of "
            "the video, and write a better title and on-screen hook text."
        )
        out = gem.generate_json(prompt, HookRewrite, system=SYSTEM, temperature=1.0)
        db.execute(
            "update scenes set narration = %s, image_prompt = %s where id = %s",
            [out.first_scene_narration.strip(), out.first_scene_image_prompt.strip(), first["id"]],
        )
        db.execute(
            "update stories set title = %s, hook_text = %s where project_id = %s",
            [out.title.strip()[:100], out.hook_text.strip()[:60], ctx.project_id],
        )
        return {"scene_id": str(first["id"])}
    raise StepFailed(f"Unknown operation {p['op']}")


def build_script(params: dict) -> Pipeline:
    return Pipeline(
        [Step("script", write_script, label="Writing script")], finalize=lambda c: c.outputs["script"]
    )


def build_scene_ai(params: dict) -> Pipeline:
    return Pipeline([Step("ai", scene_ai, label="Rewriting")], finalize=lambda c: c.outputs["ai"])
