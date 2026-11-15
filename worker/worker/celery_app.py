"""Celery application. Queues: media (CPU), ai (Gemini I/O), poll (Veo operations)."""

from __future__ import annotations

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
    },
)
