"""Finished jobs queue webhook deliveries for the job owner's webhooks."""

from __future__ import annotations

import pytest
from studio_shared import crypto, db
from tests_helpers import make_member

from worker import hooks

pytestmark = pytest.mark.integration


def test_finished_jobs_queue_webhooks(monkeypatch):
    sent = []
    from celery import current_app

    monkeypatch.setattr(current_app, "send_task", lambda name, args, queue: sent.append((name, args, queue)))
    uid = make_member(plan="business")
    db.execute(
        "insert into webhooks (user_id, url, secret_enc, events) values (%s,'https://example.com/h',%s,%s)",
        [uid, crypto.encrypt("s"), ["job.failed"]],
    )
    job = db.fetch_one(
        "insert into jobs (kind, status, created_by, params) values ('story_render','failed',%s,'{}') returning *",
        [uid],
    )
    hooks._fire_webhooks(job, "failed", "boom")
    assert len(sent) == 1 and sent[0][0] == "worker.deliver_webhook" and sent[0][1][1] == "job.failed"
    assert sent[0][1][2]["job"]["error"] == "boom" and sent[0][2] == "ai"
    hooks._fire_webhooks(job, "succeeded", None)  # not subscribed to successes
    quiet = {**job, "kind": "story_scene_ai"}
    hooks._fire_webhooks(quiet, "failed", "x")  # internal jobs stay quiet
    assert len(sent) == 1
