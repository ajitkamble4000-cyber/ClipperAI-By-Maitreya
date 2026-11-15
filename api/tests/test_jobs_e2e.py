"""Queue end to end: API creates a job, a real Celery worker runs it, progress lands in Postgres.
Also checks resume: a job that fails in step 2 is retried and step 1 is NOT run again."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from studio_shared import db, storage

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def worker():
    env = {**os.environ, "PYTHONPATH": str(ROOT / "worker")}
    p = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "celery",
            "-A",
            "worker.celery_app",
            "worker",
            "-Q",
            "media,ai,poll",
            "--concurrency",
            "2",
            "--loglevel",
            "WARNING",
            "--pool",
            "prefork",
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    time.sleep(4)
    yield p
    p.terminate()
    p.wait(10)


def wait_for(job_id: str, statuses: tuple[str, ...], timeout: float = 60) -> dict:
    deadline = time.time() + timeout
    seen = set()
    while time.time() < deadline:
        j = db.fetch_one("select * from jobs where id = %s", [job_id])
        seen.add((j["step"], j["percent"]))
        if j["status"] in statuses:
            j["_seen"] = seen
            return j
        time.sleep(0.2)
    raise AssertionError(f"job {job_id} stuck: {j['status']} {j['step']} {j['percent']}")


def test_dummy_job_runs_with_progress(client, make_member, worker):
    _, _, hdr = make_member()
    r = client.post("/jobs/dummy", json={"seconds_per_step": 1.5}, headers=hdr)
    assert r.status_code == 201
    job = wait_for(r.json()["id"], ("succeeded", "failed"))
    assert job["status"] == "succeeded", job["error"]
    assert job["percent"] == 100
    pcts = sorted(p for _, p in job["_seen"])
    assert len({p for p in pcts if 0 < p < 100}) >= 3, "expected several intermediate progress updates"
    assert storage.get_bytes(job["result"]["key"]).startswith(b"hello from job")
    steps = client.get(f"/jobs/{job['id']}", headers=hdr).json()["steps"]
    assert {s["name"]: s["status"] for s in steps} == {"prepare": "done", "process": "done", "write": "done"}


def test_failed_job_resumes_from_last_step(client, make_member, worker):
    _, _, hdr = make_member()
    r = client.post("/jobs/dummy", json={"seconds_per_step": 0.3, "fail_at": "process"}, headers=hdr)
    jid = r.json()["id"]
    job = wait_for(jid, ("succeeded", "failed"))
    assert job["status"] == "failed" and "Simulated failure" in job["error"]
    prepare_finished = db.fetch_one(
        "select finished_at from job_steps where job_id = %s and name = 'prepare'", [jid]
    )["finished_at"]

    # attempts reset to 0 by retry; the dummy only fails on attempt 1, so make it pass now.
    db.execute("update jobs set params = params - 'fail_at' where id = %s", [jid])
    assert client.post(f"/jobs/{jid}/retry", headers=hdr).status_code == 200
    job = wait_for(jid, ("succeeded", "failed"))
    assert job["status"] == "succeeded", job["error"]
    again = db.fetch_one("select finished_at from job_steps where job_id = %s and name = 'prepare'", [jid])
    assert again["finished_at"] == prepare_finished, "prepare step should not have re-run"


def test_cancel_stops_job(client, make_member, worker):
    _, _, hdr = make_member()
    jid = client.post("/jobs/dummy", json={"seconds_per_step": 5}, headers=hdr).json()["id"]
    wait_for(jid, ("running",), 20)
    assert client.post(f"/jobs/{jid}/cancel", headers=hdr).json() == {"canceled": True}
    time.sleep(2)
    assert db.fetch_one("select status from jobs where id = %s", [jid])["status"] == "canceled"


def test_rate_limit(client, make_member, monkeypatch, worker):
    from studio_shared.config import get_settings

    monkeypatch.setattr(get_settings(), "jobs_per_user_per_minute", 2)
    _, _, hdr = make_member()
    codes = [
        client.post("/jobs/dummy", json={"seconds_per_step": 0.1}, headers=hdr).status_code for _ in range(3)
    ]
    assert codes == [201, 201, 429]
