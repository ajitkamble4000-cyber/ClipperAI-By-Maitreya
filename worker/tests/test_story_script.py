"""Story script generation + AI scene edits with a fake Gemini, through the real pipeline and DB."""

from __future__ import annotations

import pytest
from fakes_story import FakeStoryGemini
from studio_shared import db, jobs
from studio_shared import gemini as gem_pkg
from worker.pipelines import get_pipeline
from worker.story.script import build_script_prompt

pytestmark = pytest.mark.integration


@pytest.fixture
def story():
    fake = FakeStoryGemini()
    old = gem_pkg.factory
    gem_pkg.factory = lambda ctx: fake
    pid = db.fetch_one("insert into projects (type, title) values ('story', 'x') returning id")["id"]
    db.execute(
        "insert into stories (project_id, idea, genre, language, length_s) values (%s, %s, 'what_if', 'hinglish', 30)",
        [pid, "What happens if you fall into a black hole"],
    )
    yield pid, fake
    gem_pkg.factory = old
    db.execute("delete from projects where id = %s", [pid])


def run(kind, pid, params):
    job = jobs.mark_running(jobs.create_job(kind, project_id=pid, params=params, user_id=None)["id"])
    return get_pipeline(kind, params).run(job)


def test_prompt_uses_genre_language_length_and_style(story):
    pid, _ = story
    st = db.fetch_one("select * from stories where project_id = %s", [pid])
    p = build_script_prompt(st)
    assert (
        "what happens if" in p.lower() and "Hinglish" in p and "about 30 seconds" in p and "6-8 scenes" in p
    )
    assert "Hyper-realistic 3D render" in p  # the visual style prompt from the DB


def test_script_writes_scenes_characters_and_metadata(story):
    pid, _ = story
    assert run("story_script", pid, {}) == {"scenes": 6, "characters": 1}
    scenes = db.fetch_all("select * from scenes where project_id = %s order by idx", [pid])
    assert [s["idx"] for s in scenes] == list(range(6))
    assert scenes[0]["camera_motion"] == "zoom-in" and scenes[0]["sfx_suggestion"] == "whoosh"
    st = db.fetch_one("select * from stories where project_id = %s", [pid])
    assert st["title"].startswith("What if") and st["hashtags"][0] == "#space"
    assert db.fetch_one("select title, status from projects where id = %s", [pid]) == {
        "title": "What if you fell into a black hole?",
        "status": "storyboard",
    }
    assert db.fetch_one("select name from characters where project_id = %s", [pid])["name"] == "Astronaut"


def test_regenerate_keeps_locked_characters(story):
    pid, _ = story
    run("story_script", pid, {})
    db.execute(
        "update characters set locked = true, description = 'my custom look' where project_id = %s", [pid]
    )
    run("story_script", pid, {})
    rows = db.fetch_all("select * from characters where project_id = %s", [pid])
    assert len(rows) == 1 and rows[0]["description"] == "my custom look"


def test_rewrite_scene_and_stronger_hook(story):
    pid, fake = story
    run("story_script", pid, {})
    sc = db.fetch_one("select id from scenes where project_id = %s and idx = 2", [pid])
    run("story_scene_ai", pid, {"op": "rewrite", "scene_id": str(sc["id"]), "instruction": "make it scarier"})
    row = db.fetch_one("select * from scenes where id = %s", [sc["id"]])
    assert row["narration"] == "A rewritten, more gripping line." and row["camera_motion"] == "shake"
    assert "make it scarier" in fake.prompts[-1]
    run("story_scene_ai", pid, {"op": "hook"})
    first = db.fetch_one("select narration from scenes where project_id = %s and idx = 0", [pid])
    assert first["narration"] == "Stronger hook."
    assert (
        db.fetch_one("select hook_text from stories where project_id = %s", [pid])["hook_text"]
        == "DON'T LOOK DOWN"
    )


def test_no_key_gives_clear_error(story, monkeypatch):
    pid, _ = story
    gem_pkg.factory = lambda ctx: gem_pkg.Gemini(ctx)
    monkeypatch.setattr("studio_shared.app_settings.gemini_key", lambda: None)
    with pytest.raises(gem_pkg.GeminiNotConfigured, match="Settings"):
        run("story_script", pid, {})
