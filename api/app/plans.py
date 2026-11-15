"""Plan entitlements (features, limits) and the one place jobs are launched: check limits, create the job,
charge tokens, enqueue. Failed or canceled jobs are refunded automatically."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from studio_shared import db, jobs, tokens

from .auth import Member
from .queue import enqueue
from .ratelimit import check_job_rate

FEATURE_LABELS = {
    "visual_analysis": "Visual analysis",
    "brand_kit": "Brand kit",
    "translation": "Caption translation",
    "filler_removal": "Filler & silence removal",
    "keyword_emphasis": "Keyword emphasis",
    "templates": "Templates",
    "premium_voices": "Premium voices",
    "thumbnails": "AI thumbnails",
    "title_variants": "Title ideas",
    "share_links": "Share links",
    "output_formats": "Square / 4:5 / 16:9 output",
    "premium_video": "Premium AI video",
    "batch": "Batch mode",
    "no_watermark": "No watermark",
    "priority": "Priority processing",
}
LIGHT_KINDS = ("clip_zip", "dummy")  # don't count toward the concurrent-job limit


def plan_for(m: Member) -> dict[str, Any]:
    pid = "team" if m.unlimited else m.plan_id
    return db.fetch_one("select * from plans where id = %s", [pid]) or {"features": [], "limits": {}}


def has_feature(m: Member, feature: str) -> bool:
    return m.unlimited or feature in (plan_for(m)["features"] or [])


def require_feature(m: Member, feature: str) -> None:
    if has_feature(m, feature):
        return
    row = db.fetch_one(
        "select name from plans where public and %s = any(features) order by sort limit 1", [feature]
    )
    label = FEATURE_LABELS.get(feature, feature.replace("_", " ").title())
    where = f" It's included in {row['name']} and above." if row else ""
    raise HTTPException(
        status.HTTP_403_FORBIDDEN, f"{label} isn't included in your plan.{where} See Pricing to upgrade."
    )


def limit(m: Member, key: str, default: int | bool = 0) -> Any:
    return (plan_for(m)["limits"] or {}).get(key, default)


def check_concurrency(m: Member) -> None:
    cap = int(limit(m, "concurrent_jobs", 1) or 1)
    running = db.fetch_one(
        "select count(*) as n from jobs where created_by = %s and status in ('queued','running') and kind <> all(%s)",
        [m.user_id, list(LIGHT_KINDS)],
    )["n"]
    if running >= cap:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Your plan runs {cap} job{'s' if cap > 1 else ''} at a time. Wait for the current one to finish, "
            "or upgrade for more.",
        )


def launch(
    m: Member,
    kind: str,
    project_id: str | None,
    params: dict[str, Any],
    quote_params: dict[str, Any] | None = None,
    *,
    rate_cost: int = 1,
    batch: bool = False,
) -> dict[str, Any]:
    """Create + charge + enqueue. Raises 402 with a clear message if the user lacks tokens.
    Batch launches (a plan feature with its own size limit) queue up instead of hitting the concurrency cap."""
    check_job_rate(m.user_id, rate_cost)
    if kind not in LIGHT_KINDS and not batch:
        check_concurrency(m)
    qp = quote_params if quote_params is not None else params
    cost, items = tokens.quote(kind, qp)
    params = {**params, "_tokens": {"kind": kind, "params": qp, "cost": cost, "items": items}}
    job = jobs.create_job(kind, project_id=project_id, params=params, user_id=m.user_id)
    try:
        tokens.charge(m.user_id, cost, kind, job_id=str(job["id"]), meta={"items": items})
    except tokens.InsufficientTokens as e:
        db.execute("delete from jobs where id = %s", [job["id"]])
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, str(e)) from e
    enqueue(job)
    job["tokens_charged"] = 0 if m.unlimited else cost
    return job


def recharge_for_retry(m: Member, job: dict[str, Any]) -> None:
    """A retried job was refunded when it failed; charge it again (same quote)."""
    t = (job.get("params") or {}).get("_tokens") or {}
    cost = int(t.get("cost") or 0)
    if not cost:
        return
    owner = str(job["created_by"]) if job.get("created_by") else m.user_id
    try:
        tokens.charge(
            owner, cost, job["kind"], job_id=str(job["id"]), meta={"items": t.get("items"), "retry": True}
        )
    except tokens.InsufficientTokens as e:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, str(e)) from e
