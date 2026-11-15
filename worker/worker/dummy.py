"""Dummy job used to prove the queue + live progress + resume path end to end."""

from __future__ import annotations

import time

from studio_shared import storage

from .pipeline import JobContext, Pipeline, Step, StepFailed


def _work(name: str, seconds: float):
    def run(ctx: JobContext) -> dict:
        ticks = max(1, int(seconds * 4))
        for i in range(ticks):
            ctx.check_canceled()
            time.sleep(seconds / ticks)
            ctx.progress((i + 1) / ticks, f"{name}: {i + 1}/{ticks}")
        if ctx.params.get("fail_at") == name and ctx.job["attempts"] <= 1:
            raise StepFailed(f"Simulated failure in {name}")
        return {"finished": name}

    return run


def _write(ctx: JobContext) -> dict:
    key = ctx.job_key("hello.txt")
    storage.put_bytes(key, f"hello from job {ctx.job_id}".encode(), "text/plain")
    ctx.log(f"wrote {key}")
    return {"key": key}


def build(params: dict) -> Pipeline:
    secs = float(params.get("seconds_per_step", 1.5))
    return Pipeline(
        [
            Step("prepare", _work("prepare", secs), label="Preparing"),
            Step("process", _work("process", secs * 2), weight=2, label="Processing"),
            Step("write", _write, label="Saving result"),
        ],
        finalize=lambda ctx: {"key": ctx.outputs["write"]["key"]},
    )
