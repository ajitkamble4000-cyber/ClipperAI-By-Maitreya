"""Content-calendar reminders: a notification shortly before each planned post."""

from __future__ import annotations

from . import db
from .notify import notify

LABEL = {
    "youtube": "YouTube",
    "tiktok": "TikTok",
    "instagram": "Instagram",
    "facebook": "Facebook",
    "x": "X",
    "linkedin": "LinkedIn",
    "other": "your channel",
}


def send_due() -> int:
    rows = db.fetch_all(
        """update schedule_items s set reminded_at = now()
             from projects p
            where p.id = s.project_id and s.status = 'planned' and s.reminded_at is null and s.remind_minutes > 0
              and s.scheduled_at - make_interval(mins => s.remind_minutes) <= now()
              and s.scheduled_at > now() - interval '1 day'
        returning s.user_id, s.platform, s.scheduled_at, s.project_id,
                  coalesce((select title from clips where id = s.clip_id), p.title) as title"""
    )
    for r in rows:
        notify(
            str(r["user_id"]),
            f"Time to post on {LABEL.get(r['platform'], r['platform'])}",
            r["title"] or "",
            link="/calendar",
            kind="info",
        )
    return len(rows)
