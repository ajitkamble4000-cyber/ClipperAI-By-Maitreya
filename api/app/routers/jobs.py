"""Generic job endpoints: status, cancel, retry (resume), and the dummy test job."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from studio_shared import db, jobs, tokens

from ..access import job_for, project_for
from ..auth import CurrentMember
from ..plans import launch, recharge_for_retry
from ..queue import enqueue
from ..ratelimit import check_job_rate

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _get(job_id: str, m) -> dict:
    return job_for(job_id, m)


@router.get("/{job_id}")
def get_job(job_id: str, m: CurrentMember) -> dict:
    job = _get(job_id, m)
    job["steps"] = db.fetch_all(
        "select name, status, started_at, finished_at from job_steps where job_id = %s order by started_at nulls last",
        [job_id],
    )
    job["logs"] = db.fetch_all(
        "select ts, level, message from job_logs where job_id = %s order by id desc limit 50", [job_id]
    )
    return job


def _get_for_change(job_id: str, m) -> dict:
    """Cancel/retry: your own jobs, admins, or editors of the job's project."""
    job = job_for(job_id, m)
    if str(job["created_by"]) != m.user_id and not m.is_admin and job["project_id"]:
        project_for(str(job["project_id"]), m, write=True)
    return job


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str, m: CurrentMember) -> dict:
    _get_for_change(job_id, m)
    canceled = jobs.cancel(job_id)
    refunded = tokens.refund_job(job_id, "canceled") if canceled else 0
    return {"canceled": canceled, "refunded": refunded}


@router.post("/{job_id}/retry")
def retry_job(job_id: str, m: CurrentMember) -> dict:
    job = _get_for_change(job_id, m)
    if job["status"] not in ("failed", "canceled"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Only failed or canceled jobs can be retried")
    check_job_rate(m.user_id)
    recharge_for_retry(m, job)
    db.execute(
        "update jobs set status = 'queued', attempts = 0, error = null, finished_at = null, message = 'Queued' "
        "where id = %s",
        [job_id],
    )
    enqueue(_get(job_id, m))
    return {"ok": True}


class DummyIn(BaseModel):
    seconds_per_step: float = Field(default=1.5, ge=0.1, le=30)
    fail_at: str | None = None


@router.post("/dummy", status_code=201)
def dummy(body: DummyIn, m: CurrentMember) -> dict:
    job = launch(m, "dummy", None, body.model_dump())
    return job
