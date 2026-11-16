"""Celery application. Queues: media (CPU), ai (Gemini I/O), poll (Veo operations)."""

from __future__ import annotations

from pathlib import Path

from celery import Celery
from celery.schedules import crontab
from kombu import Queue
from studio_shared.config import get_settings
from studio_shared.logging_setup import setup as setup_logging
from studio_shared.queue import QUEUE_AI, QUEUE_MEDIA, QUEUE_POLL

setup_logging()
_s = get_settings()

app = Celery("shorts_studio", broker=_s.redis_url, backend=None, include=["worker.tasks"])
app.conf.update(
    task_queues=[Queue(QUEUE_MEDIA), Queue(QUEUE_AI), Queue(QUEUE_POLL)],
    task_default_queue=QUEUE_MEDIA,
    task_acks_late=True,  # redeliver if a worker dies mid-job
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # long tasks: take one at a time
    broker_transport_options={"visibility_timeout": 6 * 3600},
    broker_connection_retry_on_startup=True,
    task_ignore_result=True,
    timezone="UTC",
    beat_schedule={
        "recover-stuck-jobs": {"task": "worker.recover_stuck_jobs", "schedule": 120.0},
        "cleanup-sources": {"task": "worker.cleanup_sources", "schedule": crontab(minute=17, hour="*/6")},
        "expire-trials": {"task": "worker.expire_trials", "schedule": 900.0},
    },
)


def _install_test_fakes() -> None:
    """TEST ONLY: STUDIO_FAKE_GEMINI=1 swaps Gemini for an offline fake (Pillow images, espeak voice).
    Used by the browser end-to-end tests; never set this in production."""
    import logging
    import os
    import sys

    if os.environ.get("STUDIO_FAKE_GEMINI") != "1":
        return
    from studio_shared import gemini as gem_pkg

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
    from fakes_story import FakeVeoGemini

    import worker.story.veo as veo_mod

    veo_mod.POLL_EVERY = 0.5
    fake = FakeVeoGemini()
    gem_pkg.factory = lambda ctx: fake
    import worker.clipper.pipeline as cp
    import worker.extras as ex
    import worker.repurpose as rp

    cp.available = lambda: True
    ex.available = lambda: True
    rp.available = lambda: True
    logging.getLogger(__name__).warning("STUDIO_FAKE_GEMINI=1: using the offline fake Gemini (test mode)")


_install_test_fakes()
