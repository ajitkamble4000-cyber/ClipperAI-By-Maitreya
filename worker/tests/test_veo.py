"""Premium Veo mode: submit, poll, store, per-scene failure + retry, resume without re-paying, render uses clips."""

from __future__ import annotations

import pytest
from fakes_story import FakeVeoGemini
from studio_shared import db, jobs, storage
from studio_shared import gemini as gem_pkg
from worker.media import ffmpeg
from worker.pipelines import get_pipeline
from worker.story import veo as veo_mod

pytestmark = [pytest.mark.integration, pytest.mark.slow]


def run(kind, pid, params=None):
    params = params or {}
    job = jobs.mark_running(jobs.create_job(kind, project_id=pid, params=params, user_id=None)["id"])
    out = get_pipeline(kind, params).run(job)
    jobs.finish(job["id"], "succeeded", result=out)
    return out


@pytest.fixture(scope="module")
def story():
    fake = FakeVeoGemini()
    old = gem_pkg.factory
    gem_pkg.factory = lambda ctx: fake
    veo_mod.POLL_EVERY = 0.01
    import studio_shared.app_settings as aps

    old_model = aps.model_for
    aps.model_for = lambda role: {"video": "veo-3.1-fast-generate-preview"}.get(role) or old_model(role)
    db.execute("delete from assets where kind = 'video'")  # start with an empty Veo cache
    pid = db.fetch_one("insert into projects (type, title) values ('story', 'veo') returning id")["id"]
    db.execute(
        "insert into stories (project_id, idea, length_s, motion_mode) values (%s, 'black hole', 30, 'premium')",
        [pid],
    )
    for k in ("story_script", "story_images", "story_voice"):
        run(k, pid)
    yield pid, fake
    gem_pkg.factory = old
    aps.model_for = old_model
    db.execute("delete from projects where id = %s", [pid])


def test_veo_success_and_independent_failure(story):
    pid, fake = story
    scenes = db.fetch_all("select * from scenes where project_id = %s order by idx", [pid])
    db.execute("update scenes set image_prompt = image_prompt || ' FAILME' where id = %s", [scenes[1]["id"]])
    out = run("story_veo", pid, {"scene_ids": [str(scenes[0]["id"]), str(scenes[1]["id"])]})
    assert out == {"done": 1, "failed": 1}
    ok = db.fetch_one("select * from scenes where id = %s", [scenes[0]["id"]])
    bad = db.fetch_one("select * from scenes where id = %s", [scenes[1]["id"]])
    assert ok["video_status"] == "done" and storage.exists(ok["video_key"])
    assert bad["video_status"] == "failed" and "filtered" in bad["veo_error"]
    # usage logged per generated second
    row = db.fetch_one(
        "select seconds, cost_usd from usage_events where project_id = %s and kind = 'video'", [pid]
    )
    assert float(row["seconds"]) == 4 and float(row["cost_usd"]) == pytest.approx(0.6)

    # Retry just the failed scene after fixing its prompt.
    db.execute(
        "update scenes set image_prompt = replace(image_prompt, ' FAILME', '') where id = %s",
        [scenes[1]["id"]],
    )
    started = fake.started
    assert run("story_veo", pid, {"scene_ids": [str(scenes[1]["id"])]}) == {"done": 1, "failed": 0}
    assert fake.started == started + 1


def test_resume_polls_existing_operation_instead_of_resubmitting(story):
    pid, fake = story
    sc = db.fetch_one("select * from scenes where project_id = %s and idx = 2", [pid])
    op = fake.start_video(prompt="x", image=b"", mime="image/png", seconds=4)
    db.execute(
        "update scenes set video_status = 'running', veo_operation = %s where id = %s", [op.name, sc["id"]]
    )
    started = fake.started
    assert run("story_veo", pid, {"scene_ids": [str(sc["id"])]})["done"] == 1
    assert fake.started == started, "a resumed job must not submit a new (paid) generation"


def test_cached_clip_is_reused(story):
    pid, fake = story
    sc = db.fetch_one("select * from scenes where project_id = %s and idx = 0", [pid])
    started = fake.started
    run("story_veo", pid, {"scene_ids": [str(sc["id"])]})
    assert fake.started == started


def test_render_uses_veo_clips(story, tmp_path):
    pid, _ = story
    out = run("story_render", pid)
    pr = ffmpeg.probe(storage.download_file(out["render_key"], tmp_path / "v.mp4"))
    assert (pr.width, pr.height, pr.fps) == (1080, 1920, 30)
    seg = db.fetch_one("select count(*) as n from assets where kind = 'segment' and meta = '{}'::jsonb")
    assert seg["n"] >= 1
