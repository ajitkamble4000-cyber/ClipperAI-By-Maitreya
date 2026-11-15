"""Celery producer. The API never imports worker code; it sends tasks by name."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from celery import Celery
from studio_shared.config import get_settings
from studio_shared.queue import JOB_ROUTES


@lru_cache
def _celery() -> Celery:
    return Celery("shorts_studio_producer", broker=get_settings().redis_url)


def enqueue(job: dict[str, Any]) -> None:
    task, queue = JOB_ROUTES[job["kind"]]
    _celery().send_task(task, args=[str(job["id"])], queue=queue)
