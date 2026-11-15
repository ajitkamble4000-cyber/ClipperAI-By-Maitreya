"""Admin panel: business overview, jobs monitor, system health."""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from studio_shared import db, jobs, storage, tokens, usage
from studio_shared.queue import QUEUE_AI, QUEUE_MEDIA, QUEUE_POLL

from ..auth import AdminMember, audit
from ..ratelimit import _r

router = APIRouter(prefix="/admin", tags=["admin"])


def _num(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: (float(v) if isinstance(v, Decimal) else v) for k, v in r.items()} for r in rows]


@router.get("/overview")
def overview(_: AdminMember) -> dict:
    users = db.fetch_one(
        """select count(*) as total,
                  count(*) filter (where created_at > now() - interval '7 days') as new_7d,
                  count(*) filter (where last_seen_at > now() - interval '1 day') as active_1d,
                  count(*) filter (where last_seen_at > now() - interval '7 days') as active_7d,
                  count(*) filter (where status = 'suspended') as suspended,
                  count(*) filter (where team is not null) as team
             from members"""
    )
    by_plan = db.fetch_all(
        """select p.id, p.name, p.price_usd_month,
                  count(m.user_id) filter (where m.team is null) as users,
                  count(m.user_id) filter (where m.team is null and m.role = 'user') as paying
             from plans p left join members m on m.plan_id = p.id group by p.id order by p.sort"""
    )
    team_row = next((p for p in by_plan if p["id"] == "team"), None)
    if team_row is not None:  # Staff/Creator members can sit on any plan; count them under Team
        team_row["users"] = int(users["team"])
    mrr = sum(
        float(p["price_usd_month"] or 0) * int(p["paying"]) for p in by_plan
    )  # owner/admins/team don't pay
    job_stats = db.fetch_one(
        """select count(*) filter (where created_at > now() - interval '1 day') as today,
                  count(*) filter (where status in ('queued','running')) as active,
                  count(*) filter (where status = 'failed' and created_at > now() - interval '1 day') as failed_1d,
                  count(*) filter (where status = 'succeeded' and created_at > now() - interval '1 day') as ok_1d
             from jobs where kind not in ('dummy')"""
    )
    spent = db.fetch_one(
        """select coalesce(-sum(delta) filter (where reason = 'charge' and ts > now() - interval '1 day'), 0) as d1,
                  coalesce(-sum(delta) filter (where reason = 'charge' and ts > now() - interval '7 days'), 0) as d7,
                  coalesce(-sum(delta) filter (where reason = 'charge' and ts > now() - interval '30 days'), 0) as d30,
                  coalesce(sum(delta) filter (where reason in ('refund','adjust') and ts > now() - interval '30 days'), 0)
                    as refunded_30d,
                  coalesce(sum((meta->>'tokens')::int) filter (where reason = 'waived' and ts > now() - interval '30 days'), 0)
                    as waived_30d
             from token_ledger"""
    )
    signups = db.fetch_all(
        """select d::date as day, count(m.user_id) as n
             from generate_series(current_date - 29, current_date, interval '1 day') d
             left join members m on m.created_at >= d and m.created_at < d + interval '1 day' group by d order by d"""
    )
    jobs_per_day = db.fetch_all(
        """select d::date as day, count(j.id) filter (where j.status = 'succeeded') as ok,
                  count(j.id) filter (where j.status = 'failed') as failed
             from generate_series(current_date - 13, current_date, interval '1 day') d
             left join jobs j on j.created_at >= d and j.created_at < d + interval '1 day' and j.kind <> 'dummy'
            group by d order by d"""
    )
    top = db.fetch_all(
        """select m.user_id, coalesce(m.display_name, m.email) as name, m.email, m.plan_id, m.team,
                  -sum(l.delta) as tokens
             from token_ledger l join members m on m.user_id = l.user_id
            where l.reason = 'charge' and l.ts > now() - interval '30 days'
            group by m.user_id order by tokens desc limit 8"""
    )
    kinds = db.fetch_all(
        "select kind, count(*) as n from jobs where created_at > now() - interval '30 days' and kind <> 'dummy' "
        "group by kind order by n desc"
    )
    pending_upgrades = db.fetch_one("select count(*) as n from upgrade_requests where status = 'pending'")[
        "n"
    ]
    done = int(job_stats["ok_1d"]) + int(job_stats["failed_1d"])
    return {
        "users": users,
        "by_plan": _num(by_plan),
        "mrr_usd": round(mrr, 2),
        "jobs": {**job_stats, "success_rate": round(int(job_stats["ok_1d"]) / done, 3) if done else None},
        "tokens": {k: int(v) for k, v in spent.items()},
        "ai": usage.budget_state(),
        "signups": signups,
        "jobs_per_day": jobs_per_day,
        "top_users": _num(top),
        "job_kinds": kinds,
        "pending_upgrades": pending_upgrades,
    }


@router.get("/jobs")
def list_jobs(
    _: AdminMember,
    state: str | None = Query(default=None, alias="status", max_length=20),
    kind: str | None = Query(default=None, max_length=40),
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict]:
    where, args = ["j.kind <> 'dummy'"], []
    if state == "active":
        where.append("j.status in ('queued','running')")
    elif state:
        where.append("j.status = %s")
        args.append(state)
    if kind:
        where.append("j.kind = %s")
        args.append(kind)
    if q:
        where.append("(m.email ilike %s or p.title ilike %s)")
        args += [f"%{q}%", f"%{q}%"]
    return db.fetch_all(
        f"""select j.id, j.kind, j.status, j.percent, j.message, j.error, j.attempts, j.tokens_charged, j.project_id,
                   j.created_at, j.started_at, j.finished_at, j.heartbeat_at,
                   extract(epoch from (coalesce(j.finished_at, now()) - coalesce(j.started_at, j.created_at))) as seconds,
                   m.email, coalesce(m.display_name, m.email) as user_name, p.title as project_title, p.type as project_type
              from jobs j left join members m on m.user_id = j.created_by left join projects p on p.id = j.project_id
             where {" and ".join(where)} order by j.created_at desc limit %s""",
        [*args, limit],
    )


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, admin: AdminMember) -> dict:
    try:
        job = jobs.get_job(job_id)
    except Exception as e:  # noqa: BLE001 - bad uuid
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found") from e
    if not job:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    if not jobs.cancel(job_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "The job isn't running")
    refunded = tokens.refund_job(job_id, "canceled by an admin")
    audit(admin, "job.cancel", "job", job_id, kind=job["kind"], refunded=refunded)
    return {"canceled": True, "refunded": refunded}


@router.get("/health")
def health(_: AdminMember) -> dict:
    checks: dict[str, Any] = {}
    t = time.monotonic()
    db.fetch_one("select 1 as ok")
    checks["database"] = {"ok": True, "ms": round((time.monotonic() - t) * 1000, 1)}
    try:
        t = time.monotonic()
        r = _r()
        r.ping()
        queues = {q: int(r.llen(q)) for q in (QUEUE_MEDIA, QUEUE_AI, QUEUE_POLL)}
        checks["redis"] = {"ok": True, "ms": round((time.monotonic() - t) * 1000, 1), "queues": queues}
    except Exception as e:  # noqa: BLE001
        checks["redis"] = {"ok": False, "error": str(e)[:200]}
    try:
        t = time.monotonic()
        storage.exists("health/check")
        checks["storage"] = {"ok": True, "ms": round((time.monotonic() - t) * 1000, 1)}
    except Exception as e:  # noqa: BLE001
        checks["storage"] = {"ok": False, "error": str(e)[:200]}
    w = db.fetch_one(
        """select count(*) filter (where status = 'running') as running,
                  count(*) filter (where status = 'running' and heartbeat_at < now() - interval '2 minutes') as stale,
                  max(heartbeat_at) as last_heartbeat,
                  count(*) filter (where status = 'queued' and created_at < now() - interval '10 minutes') as waiting_long
             from jobs"""
    )
    checks["workers"] = {
        "ok": int(w["stale"]) == 0 and int(w["waiting_long"]) == 0,
        "running": w["running"],
        "stale": w["stale"],
        "waiting_long": w["waiting_long"],
        "last_heartbeat": w["last_heartbeat"],
    }
    from studio_shared.ai.base import provider_status

    provs = provider_status()
    checks["ai"] = {
        "ok": any(p.get("configured") for p in provs),
        "configured": [p["id"] for p in provs if p.get("configured")],
        "budget": usage.budget_state(),
    }
    return {"ok": all(c.get("ok") for c in checks.values()), "checks": checks}
