"""Insights: your personal stats; admin extras (refund a finished job, export users as CSV)."""

from __future__ import annotations

import csv
import io
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from studio_shared import db, jobs, tokens
from studio_shared.notify import notify

from ..auth import AdminMember, CurrentMember, audit

router = APIRouter(tags=["insights"])

# What each kind of job is called on the stats page (several kinds roll up into one feature).
FEATURE_OF: dict[str, str] = {
    "clip": "Clips",
    "clip_rerender": "Re-renders & edits",
    "clip_zip": "ZIP downloads",
    "clip_export": "MP3 & GIF exports",
    "clip_compile": "Compilations",
    "story_script": "Story scripts",
    "story_scene_ai": "Story scripts",
    "story_characters": "Characters",
    "story_images": "Story images",
    "story_image_one": "Story images",
    "story_voice": "Voiceover",
    "story_render": "Story renders",
    "story_veo": "Premium video",
    "thumbnail": "Thumbnails",
    "title_variants": "Title ideas",
    "repurpose": "Write-ups",
}


def _f(v: Any) -> float:
    return round(float(v or 0), 1) if isinstance(v, (Decimal, float, int)) else 0.0


@router.get("/me/stats")
def my_stats(m: CurrentMember, days: Annotated[int, Query(ge=7, le=90)] = 30) -> dict:
    """What you've made and what it cost, for the last `days` days, with a day-by-day series."""
    since = date.today() - timedelta(days=days - 1)
    args = {"uid": m.user_id, "since": since}
    made = db.fetch_one(
        """select
             (select count(*) from sources s join projects p on p.id = s.project_id
               where p.created_by = %(uid)s and s.created_at >= %(since)s) as videos_in,
             (select coalesce(sum(s.duration_s), 0) / 60 from sources s join projects p on p.id = s.project_id
               where p.created_by = %(uid)s and s.created_at >= %(since)s) as minutes_in,
             (select count(*) from clips c join projects p on p.id = c.project_id
               where p.created_by = %(uid)s and c.status = 'ready' and c.created_at >= %(since)s) as clips,
             (select coalesce(sum(c.duration_s), 0) / 60 from clips c join projects p on p.id = c.project_id
               where p.created_by = %(uid)s and c.status = 'ready' and c.created_at >= %(since)s) as minutes_out,
             (select round(avg(c.virality_score)) from clips c join projects p on p.id = c.project_id
               where p.created_by = %(uid)s and c.status = 'ready' and c.mode <> 'whole'
                 and c.created_at >= %(since)s) as avg_score,
             (select count(*) from stories st join projects p on p.id = st.project_id
               where p.created_by = %(uid)s and st.render_key is not null and p.updated_at >= %(since)s) as stories,
             (select count(*) from jobs where created_by = %(uid)s and status = 'succeeded'
               and kind <> 'dummy' and created_at >= %(since)s) as jobs_ok,
             (select count(*) from jobs where created_by = %(uid)s and status = 'failed'
               and kind <> 'dummy' and created_at >= %(since)s) as jobs_failed""",
        args,
    )
    # Net tokens per job kind: charges minus refunds/returns (refund rows carry the job, not the action).
    spend = db.fetch_all(
        """select coalesce(l.action, j.kind) as kind, -sum(l.delta)::int as tokens
             from token_ledger l left join jobs j on j.id = l.job_id
            where l.user_id = %(uid)s and l.ts >= %(since)s
              and (l.reason = 'charge' or (l.reason in ('refund', 'adjust') and l.job_id is not null))
            group by 1""",
        args,
    )
    by_feature: dict[str, int] = {}
    for r in spend:
        if r["kind"] == "dummy" or not r["tokens"]:
            continue
        label = FEATURE_OF.get(r["kind"] or "", "Other")
        by_feature[label] = by_feature.get(label, 0) + r["tokens"]
    features = sorted(
        ({"feature": k, "tokens": v} for k, v in by_feature.items() if v > 0),
        key=lambda x: -x["tokens"],
    )

    daily_rows = db.fetch_all(
        """select d::date as day,
                  coalesce((select -sum(l.delta) from token_ledger l
                             where l.user_id = %(uid)s and l.ts::date = d::date
                               and (l.reason = 'charge' or (l.reason in ('refund','adjust') and l.job_id is not null))), 0)::int
                    as tokens,
                  (select count(*) from clips c join projects p on p.id = c.project_id
                    where p.created_by = %(uid)s and c.status = 'ready' and c.created_at::date = d::date)::int as clips,
                  (select count(*) from jobs where created_by = %(uid)s and status = 'succeeded'
                    and kind <> 'dummy' and created_at::date = d::date)::int as jobs
             from generate_series(%(since)s::date, current_date, interval '1 day') d
            order by d""",
        args,
    )
    best = db.fetch_all(
        """select c.id, c.title, c.project_id, c.virality_score, c.thumb_key, c.duration_s
             from clips c join projects p on p.id = c.project_id
            where p.created_by = %(uid)s and c.status = 'ready' and c.mode <> 'whole' and c.created_at >= %(since)s
            order by c.virality_score desc, c.created_at desc limit 5""",
        args,
    )
    # Streak: consecutive days, ending today or yesterday, on which something finished.
    active = {
        r["d"]
        for r in db.fetch_all(
            """select distinct finished_at::date as d from jobs
                where created_by = %s and status = 'succeeded' and kind <> 'dummy'
                  and finished_at > now() - interval '400 days'""",
            [m.user_id],
        )
    }
    day = date.today() if date.today() in active else date.today() - timedelta(days=1)
    streak = 0
    while day in active:
        streak += 1
        day -= timedelta(days=1)

    return {
        "days": days,
        "since": since.isoformat(),
        "totals": {
            "videos_in": made["videos_in"],
            "minutes_in": _f(made["minutes_in"]),
            "clips": made["clips"],
            "minutes_out": _f(made["minutes_out"]),
            "avg_score": int(made["avg_score"]) if made["avg_score"] is not None else None,
            "stories": made["stories"],
            "jobs_ok": made["jobs_ok"],
            "jobs_failed": made["jobs_failed"],
            "tokens": sum(f["tokens"] for f in features),
        },
        "by_feature": features,
        "daily": [{**r, "day": r["day"].isoformat()} for r in daily_rows],
        "best_clips": [{**c, "duration_s": _f(c["duration_s"])} for c in best],
        "streak": streak,
    }


# ---------------------------------------------------------------- admin extras
class RefundIn(BaseModel):
    reason: str = Field(default="", max_length=200)


@router.post("/admin/jobs/{job_id}/refund")
def refund_finished_job(job_id: str, body: RefundIn, admin: AdminMember) -> dict:
    """Give back a finished job's tokens (e.g. the result was poor). Running jobs: cancel instead."""
    try:
        job = jobs.get_job(job_id)
    except Exception as e:  # noqa: BLE001 - bad uuid
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found") from e
    if not job:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    if job["status"] in ("queued", "running"):
        raise HTTPException(status.HTTP_409_CONFLICT, "The job is still running. Cancel it instead.")
    why = body.reason.strip() or "refunded by the team"
    amount = tokens.refund_job(job_id, why)
    if not amount:
        raise HTTPException(status.HTTP_409_CONFLICT, "Nothing left to refund for this job")
    payer = db.fetch_one(
        "select user_id from token_ledger where job_id = %s and reason = 'refund' order by id desc limit 1",
        [job_id],
    )
    if payer:
        notify(
            str(payer["user_id"]),
            f"{amount} tokens refunded",
            f"For your {FEATURE_OF.get(job['kind'], job['kind']).lower()} job. {why[:1].upper()}{why[1:]}.",
            kind="success",
            link="/account/tokens",
        )
    audit(admin, "job.refund", "job", job_id, kind=job["kind"], refunded=amount, reason=why)
    return {"refunded": amount}


CSV_FIELDS = [
    "email",
    "name",
    "role",
    "plan",
    "status",
    "team",
    "joined",
    "last_seen",
    "daily_tokens",
    "bonus_tokens",
    "lifetime_spent",
    "projects",
    "jobs_30d",
]


def _cell(v: Any) -> Any:
    """Stop spreadsheet apps from running text that starts like a formula (CSV injection)."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    return v


@router.get("/admin/users.csv")
def export_users(
    admin: AdminMember,
    q: Annotated[str | None, Query(max_length=100)] = None,
    plan: Annotated[str | None, Query(max_length=40)] = None,
) -> Response:
    where, args = ["true"], []
    if q:
        where.append("(m.email ilike %s or m.display_name ilike %s)")
        args += [f"%{q}%", f"%{q}%"]
    if plan:
        where.append("m.plan_id = %s")
        args.append(plan)
    rows = db.fetch_all(
        f"""select m.email, coalesce(m.display_name, '') as name, m.role, m.plan_id as plan, m.status,
                   coalesce(m.team, '') as team, m.created_at::date as joined, m.last_seen_at::date as last_seen,
                   coalesce(w.daily_balance, 0) as daily_tokens, coalesce(w.bonus_balance, 0) as bonus_tokens,
                   coalesce(w.lifetime_spent, 0) as lifetime_spent,
                   (select count(*) from projects p where p.created_by = m.user_id) as projects,
                   (select count(*) from jobs j where j.created_by = m.user_id and j.kind <> 'dummy'
                     and j.created_at > now() - interval '30 days') as jobs_30d
              from members m left join wallets w on w.user_id = m.user_id
             where {" and ".join(where)} order by m.created_at""",
        args,
    )
    buf = io.StringIO()
    out = csv.DictWriter(buf, fieldnames=CSV_FIELDS, extrasaction="ignore")
    out.writeheader()
    for r in rows:
        out.writerow({k: _cell("" if r.get(k) is None else r.get(k)) for k in CSV_FIELDS})
    audit(admin, "users.export", "members", None, rows=len(rows))
    return Response(
        buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="users-{date.today().isoformat()}.csv"'},
    )
