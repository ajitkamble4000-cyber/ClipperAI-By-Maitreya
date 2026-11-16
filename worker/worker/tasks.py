"""Celery tasks. `run_job` executes any job kind through its resumable pipeline."""

from __future__ import annotations

import logging
import threading
import traceback

import redis
from celery import Task
from studio_shared import db, jobs, storage
from studio_shared.config import get_settings
from studio_shared.errors import UserError
from studio_shared.logging_setup import redact
from studio_shared.queue import JOB_ROUTES

from .celery_app import app
from .pipeline import JobCanceled
from .pipelines import get_pipeline

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 3
LOCK_TTL = 300


def _redis() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url)


def _heartbeat(job_id: str, lock: redis.lock.Lock, stop: threading.Event) -> None:
    while not stop.wait(60):
        try:
            db.execute("update jobs set heartbeat_at = now() where id = %s and status = 'running'", [job_id])
            lock.extend(LOCK_TTL, replace_ttl=True)
        except Exception:  # noqa: BLE001 - heartbeat must never kill the job
            log.exception("heartbeat failed for %s", job_id)


def user_message(exc: BaseException) -> str:
    if isinstance(exc, UserError):
        return str(exc)
    return redact(f"Unexpected error: {type(exc).__name__}: {exc}")[:1000]


@app.task(name="worker.run_job", bind=True)
def run_job(self: Task, job_id: str) -> None:
    # thread_local=False: the heartbeat thread extends the lock the task thread acquired.
    lock = _redis().lock(f"job-lock:{job_id}", timeout=LOCK_TTL, thread_local=False)
    if not lock.acquire(blocking=False):
        log.info("job %s already running elsewhere; skipping duplicate delivery", job_id)
        return
    stop = threading.Event()
    try:
        job = jobs.get_job(job_id)
        if not job or job["status"] in jobs.TERMINAL:
            return
        if job["attempts"] >= MAX_ATTEMPTS:
            jobs.finish(
                job_id, "failed", error="Job failed repeatedly (worker crashed or timed out). Try again."
            )
            _on_failure(job, RuntimeError("Job failed repeatedly"))
            return
        job = jobs.mark_running(job_id)
        if not job:
            return
        threading.Thread(target=_heartbeat, args=(job_id, lock, stop), daemon=True).start()
        from .hooks import on_job_started

        on_job_started(job)
        pipeline = get_pipeline(job["kind"], job["params"] or {})
        try:
            result = pipeline.run(job)
        except JobCanceled:
            jobs.log(job_id, "Canceled by user", "warn")
            return
        except Exception as exc:  # noqa: BLE001
            msg = user_message(exc)
            jobs.log(job_id, redact(traceback.format_exc())[-3500:], "error")
            if not jobs.is_canceled(job_id):
                jobs.finish(job_id, "failed", error=msg)
            _on_failure(job, exc)
            return
        if not jobs.is_canceled(job_id):
            jobs.finish(job_id, "succeeded", result=result)
            _on_success(job, result)
    finally:
        stop.set()
        try:
            lock.release()
        except Exception:  # noqa: BLE001
            pass


def _on_success(job: dict, result: dict) -> None:
    from .hooks import on_job_finished

    on_job_finished(job, "succeeded", result)


def _on_failure(job: dict, exc: BaseException) -> None:
    from .hooks import on_job_finished

    on_job_finished(job, "failed", {"error": user_message(exc)})


def enqueue(job: dict) -> None:
    task, queue = JOB_ROUTES[job["kind"]]
    app.send_task(task, args=[str(job["id"])], queue=queue)


@app.task(name="worker.recover_stuck_jobs")
def recover_stuck_jobs() -> int:
    """Requeue jobs whose worker died (no heartbeat for 5 minutes)."""
    rows = db.fetch_all(
        """update jobs set status = 'queued', message = 'Recovering after worker restart'
           where status = 'running' and heartbeat_at < now() - interval '5 minutes'
           returning *"""
    )
    for j in rows:
        jobs.log(j["id"], "Worker stopped responding; resuming from the last completed step", "warn")
        enqueue(j)
    return len(rows)


@app.task(name="worker.cleanup_sources")
def cleanup_sources() -> int:
    """Delete uploaded/downloaded source media older than the retention setting. Finished videos are kept."""
    rows = db.fetch_all(
        "select id, r2_key from sources where deleted_at is null and expires_at < now() and r2_key is not null"
    )
    for r in rows:
        try:
            storage.delete(r["r2_key"])
        except Exception:  # noqa: BLE001
            log.exception("could not delete %s", r["r2_key"])
            continue
        db.execute("update sources set deleted_at = now() where id = %s", [r["id"]])
    # Abandoned uploads (never attached to a project) older than 2 days.
    stale = db.fetch_all(
        "select id, r2_key, multipart_id, status from uploads where created_at < now() - interval '2 days' "
        "and status <> 'aborted' and r2_key not in (select r2_key from sources where r2_key is not null) "
        "and purpose = 'source'"
    )
    for u in stale:
        if u["status"] == "uploading" and u["multipart_id"]:
            storage.abort_multipart(u["r2_key"], u["multipart_id"])
        else:
            try:
                storage.delete(u["r2_key"])
            except Exception:  # noqa: BLE001
                pass
        db.execute("update uploads set status = 'aborted' where id = %s", [u["id"]])
    return len(rows)


@app.task(name="worker.expire_trials")
def expire_trials() -> int:
    """Plan trials from promo codes end on time even for people who don't sign in."""
    from studio_shared.growth import expire_trials as run

    return run()
