"""Job records in Postgres. Workers write progress here; Supabase Realtime pushes it to browsers."""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

from . import db

TERMINAL = ("succeeded", "failed", "canceled")


def create_job(
    kind: str, *, project_id: UUID | str | None, params: dict[str, Any], user_id: UUID | str | None
) -> dict[str, Any]:
    row = db.fetch_one(
        """insert into jobs (kind, project_id, params, created_by)
           values (%s, %s, %s, %s) returning *""",
        [kind, project_id, params, user_id],
    )
    assert row
    return row


def get_job(job_id: UUID | str) -> dict[str, Any] | None:
    return db.fetch_one("select * from jobs where id = %s", [job_id])


def active_job_for_project(project_id: UUID | str, kinds: tuple[str, ...]) -> dict[str, Any] | None:
    return db.fetch_one(
        "select * from jobs where project_id = %s and kind = any(%s) and status in ('queued','running') "
        "order by created_at desc limit 1",
        [project_id, list(kinds)],
    )


def mark_running(job_id: UUID | str) -> dict[str, Any] | None:
    return db.fetch_one(
        """update jobs set status = 'running', attempts = attempts + 1, heartbeat_at = now(),
                  started_at = coalesce(started_at, now()), error = null
           where id = %s and status in ('queued', 'running') returning *""",
        [job_id],
    )


def finish(
    job_id: UUID | str, status: str, *, result: dict[str, Any] | None = None, error: str | None = None
) -> None:
    db.execute(
        """update jobs set status = %s, finished_at = now(), heartbeat_at = now(),
                  percent = case when %s = 'succeeded' then 100 else percent end,
                  result = coalesce(%s, result), error = %s,
                  message = case when %s = 'succeeded' then 'Done' else message end
           where id = %s""",
        [status, status, result, error, status, job_id],
    )


def requeue(job_id: UUID | str) -> None:
    db.execute(
        "update jobs set status = 'queued', error = null, finished_at = null, message = 'Queued' where id = %s",
        [job_id],
    )


def cancel(job_id: UUID | str) -> bool:
    return (
        db.execute(
            "update jobs set status = 'canceled', finished_at = now(), message = 'Canceled' "
            "where id = %s and status in ('queued', 'running')",
            [job_id],
        )
        > 0
    )


def is_canceled(job_id: UUID | str) -> bool:
    row = db.fetch_one("select status from jobs where id = %s", [job_id])
    return bool(row and row["status"] == "canceled")


def log(job_id: UUID | str, message: str, level: str = "info") -> None:
    db.execute(
        "insert into job_logs (job_id, level, message) values (%s, %s, %s)", [job_id, level, message[:4000]]
    )


# ---------------------------------------------------------------- steps
def get_steps(job_id: UUID | str) -> dict[str, dict[str, Any]]:
    rows = db.fetch_all("select * from job_steps where job_id = %s", [job_id])
    return {r["name"]: r for r in rows}


def init_steps(job_id: UUID | str, names: list[str]) -> None:
    with db.conn() as c:
        for n in names:
            c.execute(
                "insert into job_steps (job_id, name) values (%s, %s) on conflict do nothing", [job_id, n]
            )


def step_running(job_id: UUID | str, name: str) -> None:
    db.execute(
        "update job_steps set status = 'running', started_at = now() where job_id = %s and name = %s",
        [job_id, name],
    )


def step_done(job_id: UUID | str, name: str, output: dict[str, Any]) -> None:
    db.execute(
        "update job_steps set status = 'done', output = %s, finished_at = now() where job_id = %s and name = %s",
        [output, job_id, name],
    )


def step_failed(job_id: UUID | str, name: str) -> None:
    db.execute(
        "update job_steps set status = 'failed', finished_at = now() where job_id = %s and name = %s",
        [job_id, name],
    )


def reset_steps(job_id: UUID | str, names: list[str]) -> None:
    db.execute(
        "update job_steps set status = 'pending', output = '{}'::jsonb where job_id = %s and name = any(%s)",
        [job_id, names],
    )


class ProgressReporter:
    """Writes step/percent/message to the job row, throttled so Realtime is not flooded."""

    def __init__(self, job_id: UUID | str, min_interval: float = 0.75) -> None:
        self.job_id = job_id
        self.min_interval = min_interval
        self._last = 0.0
        self._last_pct = -1

    def update(self, *, step: str, percent: float, message: str | None = None, force: bool = False) -> None:
        pct = max(0, min(100, int(percent)))
        now = time.monotonic()
        due = now - self._last >= self.min_interval or abs(pct - self._last_pct) >= 5
        if not (force or due):
            return
        self._last, self._last_pct = now, pct
        db.execute(
            "update jobs set step = %s, percent = greatest(percent, %s), message = coalesce(%s, message), "
            "heartbeat_at = now() where id = %s and status = 'running'",
            [step, pct, message, self.job_id],
        )
