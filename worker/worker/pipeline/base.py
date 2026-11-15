"""Resumable step pipeline.

A job is an ordered list of steps. Each finished step stores its output (small JSON,
usually R2 keys) in `job_steps`. If a worker crashes, the job is redelivered and the
runner skips every step already marked done, so work resumes from the last step.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from studio_shared import jobs, storage
from studio_shared.config import get_settings

log = logging.getLogger(__name__)


class StepFailed(RuntimeError):
    """A failure with a message that is safe and useful to show the user."""


class JobCanceled(RuntimeError):
    pass


@dataclass
class JobContext:
    job: dict[str, Any]
    tmp: Path
    outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    reporter: jobs.ProgressReporter | None = None
    _step: str = ""
    _step_range: tuple[float, float] = (0.0, 100.0)

    @property
    def job_id(self) -> str:
        return str(self.job["id"])

    @property
    def params(self) -> dict[str, Any]:
        return dict(self.job["params"] or {})

    @property
    def project_id(self) -> str | None:
        return str(self.job["project_id"]) if self.job.get("project_id") else None

    @property
    def user_id(self) -> str | None:
        return str(self.job["created_by"]) if self.job.get("created_by") else None

    def progress(self, fraction: float, message: str | None = None) -> None:
        """Report progress inside the current step (0..1)."""
        lo, hi = self._step_range
        pct = lo + (hi - lo) * max(0.0, min(1.0, fraction))
        if self.reporter:
            self.reporter.update(step=self._step, percent=pct, message=message)

    def log(self, message: str, level: str = "info") -> None:
        log.log(logging.WARNING if level == "warn" else logging.INFO, "[job %s] %s", self.job_id, message)
        jobs.log(self.job_id, message, level)

    def check_canceled(self) -> None:
        if jobs.is_canceled(self.job_id):
            raise JobCanceled()

    def fetch(self, key: str, name: str | None = None) -> Path:
        """Download an object into the job's temp dir (cached for the run)."""
        dest = self.tmp / "dl" / (name or key.replace("/", "_"))
        if not dest.exists():
            storage.download_file(key, dest)
        return dest

    def job_key(self, name: str) -> str:
        return f"jobs/{self.job_id}/{name}"


@dataclass
class Step:
    name: str
    run: Callable[[JobContext], dict[str, Any]]
    weight: float = 1.0
    label: str | None = None


class Pipeline:
    def __init__(
        self, steps: list[Step], finalize: Callable[[JobContext], dict[str, Any]] | None = None
    ) -> None:
        self.steps = steps
        self.finalize = finalize

    def run(self, job: dict[str, Any]) -> dict[str, Any]:
        job_id = str(job["id"])
        jobs.init_steps(job_id, [s.name for s in self.steps])
        done = jobs.get_steps(job_id)
        root = get_settings().tmp_dir
        root.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix=f"job-{job_id[:8]}-", dir=root))
        ctx = JobContext(job=job, tmp=tmp, reporter=jobs.ProgressReporter(job_id))
        total = sum(s.weight for s in self.steps) or 1.0
        acc = 0.0
        try:
            for step in self.steps:
                lo, hi = acc / total * 100, (acc + step.weight) / total * 100
                acc += step.weight
                prev = done.get(step.name)
                if prev and prev["status"] == "done":
                    ctx.outputs[step.name] = prev["output"] or {}
                    continue
                ctx.check_canceled()
                ctx._step, ctx._step_range = step.label or step.name, (lo, hi)
                jobs.step_running(job_id, step.name)
                assert ctx.reporter
                ctx.reporter.update(step=ctx._step, percent=lo, message=f"{ctx._step}…", force=True)
                try:
                    out = step.run(ctx) or {}
                except Exception:
                    jobs.step_failed(job_id, step.name)
                    raise
                ctx.outputs[step.name] = out
                jobs.step_done(job_id, step.name, out)
            return self.finalize(ctx) if self.finalize else {}
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
