"""Repurpose job (with the offline fake AI) and the transcript index."""

from __future__ import annotations

import json
import uuid

import pytest
from studio_shared import db, jobs, storage
from tests_helpers import make_member
from worker.pipelines import get_pipeline
from worker.transcribe.base import Segment, Transcript, Word

pytestmark = pytest.mark.integration


def test_repurpose_writes_everything_and_indexes():
    from fakes_story import FakeStoryGemini
    from studio_shared import gemini as gem_pkg

    from worker import repurpose

    old_f, old_a = gem_pkg.factory, repurpose.available
    gem_pkg.factory = lambda ctx: FakeStoryGemini()
    repurpose.available = lambda: True
    try:
        uid = make_member()
        t = Transcript(
            language="en",
            duration=90.0,
            segments=[
                Segment(0.0, 10.0, "Start before you are ready", [Word("Start", 0.0, 0.5)]),
                Segment(
                    40.0, 50.0, "Momentum beats motivation every single time", [Word("Momentum", 40.0, 40.6)]
                ),
            ],
        )
        key = f"cache/test-transcripts/{uuid.uuid4().hex}.json"
        storage.put_bytes(key, json.dumps(t.to_json()).encode(), "application/json")
        pid = str(
            db.fetch_one(
                "insert into projects (type, title, created_by, meta) values ('clip','Talk',%s,%s) returning id",
                [uid, {"transcript_key": key}],
            )["id"]
        )
        job = jobs.mark_running(jobs.create_job("repurpose", project_id=pid, params={}, user_id=uid)["id"])
        get_pipeline("repurpose", {}).run(job)
        r = db.fetch_one("select repurpose from projects where id = %s", [pid])["repurpose"]
        assert r["chapters"][0]["time"] == 0.0 and r["chapters_text"].startswith("0:00 Intro")
        assert r["quotes"][0] == "Start before you are ready." and len(r["x_thread"]) == 3
        assert r["blog_post"].startswith("# Getting started") and r["keywords"][0] == "motivation"
        idx = db.fetch_one("select text, segments from project_transcripts where project_id = %s", [pid])
        assert "Momentum beats motivation" in idx["text"] and idx["segments"][1]["start"] == 40.0
    finally:
        gem_pkg.factory, repurpose.available = old_f, old_a
