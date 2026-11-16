"""Content calendar: schedule clips/stories per platform, reminders, mark posted, private .ics feed."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from studio_shared import db
from studio_shared.config import get_settings

from ..access import clip_for, project_for
from ..auth import CurrentMember, SessionMember
from ..ratelimit import check_ip_rate

router = APIRouter(tags=["calendar"])

Platform = Literal["youtube", "tiktok", "instagram", "facebook", "x", "linkedin", "other"]
PLATFORM_LABEL = {
    "youtube": "YouTube",
    "tiktok": "TikTok",
    "instagram": "Instagram",
    "facebook": "Facebook",
    "x": "X",
    "linkedin": "LinkedIn",
    "other": "Other",
}
ITEM_SQL = """select s.*, p.title as project_title, p.type as project_type, c.title as clip_title,
                     coalesce(c.thumb_key, p.thumbnail_key) as thumb_key
                from schedule_items s join projects p on p.id = s.project_id left join clips c on c.id = s.clip_id"""


def _item(item_id: str, m) -> dict:
    try:
        row = db.fetch_one(ITEM_SQL + " where s.id = %s and s.user_id = %s", [item_id, m.user_id])
    except Exception as e:  # noqa: BLE001 - bad uuid
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from e
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return row


@router.get("/calendar")
def list_items(
    m: CurrentMember,
    start: Annotated[datetime, Query(alias="from")],
    end: Annotated[datetime, Query(alias="to")],
) -> list[dict]:
    if end - start > timedelta(days=100):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ask for at most 100 days at a time")
    return db.fetch_all(
        ITEM_SQL
        + " where s.user_id = %s and s.scheduled_at >= %s and s.scheduled_at < %s order by s.scheduled_at",
        [m.user_id, start, end],
    )


class ItemIn(BaseModel):
    project_id: str | None = None
    clip_id: str | None = None
    platform: Platform
    scheduled_at: datetime
    caption: str = Field(default="", max_length=2200)
    remind_minutes: int = Field(default=30, ge=0, le=10080)


@router.post("/calendar", status_code=201)
def create_item(body: ItemIn, m: CurrentMember) -> dict:
    if body.clip_id:
        clip = clip_for(body.clip_id, m)
        project_id, clip_id = str(clip["project_id"]), body.clip_id
    elif body.project_id:
        project_for(body.project_id, m)
        project_id, clip_id = body.project_id, None
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pick a clip or a project to schedule")
    when = body.scheduled_at if body.scheduled_at.tzinfo else body.scheduled_at.replace(tzinfo=UTC)
    row = db.fetch_one(
        "insert into schedule_items (user_id, project_id, clip_id, platform, scheduled_at, caption, remind_minutes) "
        "values (%s,%s,%s,%s,%s,%s,%s) returning id",
        [m.user_id, project_id, clip_id, body.platform, when, body.caption, body.remind_minutes],
    )
    return _item(str(row["id"]), m)


class ItemPatch(BaseModel):
    platform: Platform | None = None
    scheduled_at: datetime | None = None
    caption: str | None = Field(default=None, max_length=2200)
    status: Literal["planned", "posted", "skipped"] | None = None
    posted_url: str | None = Field(default=None, max_length=2048)
    remind_minutes: int | None = Field(default=None, ge=0, le=10080)


@router.patch("/calendar/{item_id}")
def update_item(item_id: str, body: ItemPatch, m: CurrentMember) -> dict:
    _item(item_id, m)
    vals = body.model_dump(exclude_none=True)
    if vals.get("posted_url") and not vals["posted_url"].startswith(("https://", "http://")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The post link should start with https://")
    if "scheduled_at" in vals:
        vals["reminded_at"] = None  # moved: remind again
    if vals:
        cols = ", ".join(f"{k} = %({k})s" for k in vals)
        db.execute(f"update schedule_items set {cols} where id = %(id)s", {**vals, "id": item_id})
    return _item(item_id, m)


@router.delete("/calendar/{item_id}")
def delete_item(item_id: str, m: CurrentMember) -> dict:
    _item(item_id, m)
    db.execute("delete from schedule_items where id = %s", [item_id])
    return {"ok": True}


# ---------------------------------------------------------------- private calendar feed
def _feed_url(token: str) -> str:
    base = (get_settings().public_api_url or "").rstrip("/")
    return f"{base}/public/calendar/{token}.ics"


@router.get("/calendar/feed")
def feed_url(m: SessionMember) -> dict:
    row = db.fetch_one("select calendar_token from members where user_id = %s", [m.user_id])
    token = row["calendar_token"] if row else None
    if not token:
        token = secrets.token_urlsafe(24)
        db.execute("update members set calendar_token = %s where user_id = %s", [token, m.user_id])
    return {"url": _feed_url(token), "token": token}


@router.post("/calendar/feed/reset")
def reset_feed(m: SessionMember) -> dict:
    token = secrets.token_urlsafe(24)
    db.execute("update members set calendar_token = %s where user_id = %s", [token, m.user_id])
    return {"url": _feed_url(token), "token": token}


def _ics_escape(s: str) -> str:
    return (
        s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r", "").replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """RFC 5545 line folding at 73 characters."""
    out, cur = [], line
    while len(cur) > 73:
        out.append(cur[:73])
        cur = " " + cur[73:]
    out.append(cur)
    return "\r\n".join(out)


@router.get("/public/calendar/{token}.ics")
def ics_feed(token: str, request: Request) -> Response:
    check_ip_rate(request.client.host if request.client else "?", "ics", limit=60)
    owner = (
        db.fetch_one("select user_id from members where calendar_token = %s", [token])
        if 16 <= len(token) <= 64
        else None
    )
    if not owner:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Calendar not found")
    rows = db.fetch_all(
        ITEM_SQL
        + " where s.user_id = %s and s.scheduled_at > now() - interval '60 days' order by s.scheduled_at",
        [owner["user_id"]],
    )
    origin = get_settings().origins[0] if get_settings().origins else ""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Shorts Studio//Content calendar//EN",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:Shorts Studio posts",
    ]
    for r in rows:
        start = r["scheduled_at"].astimezone(UTC)
        title = r["clip_title"] or r["project_title"] or "Post"
        summary = f"{'✓ ' if r['status'] == 'posted' else ''}Post on {PLATFORM_LABEL[r['platform']]}: {title}"
        path = "clipper" if r["project_type"] == "clip" else "story"
        lines += [
            "BEGIN:VEVENT",
            f"UID:{r['id']}@shorts-studio",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{start.strftime('%Y%m%dT%H%M%SZ')}",
            f"DTEND:{(start + timedelta(minutes=15)).strftime('%Y%m%dT%H%M%SZ')}",
            _fold(f"SUMMARY:{_ics_escape(summary)}"),
            _fold(f"DESCRIPTION:{_ics_escape(r['caption'] or '')}"),
            _fold(f"URL:{origin}/{path}/{r['project_id']}"),
            f"STATUS:{'CANCELLED' if r['status'] == 'skipped' else 'CONFIRMED'}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return Response(
        "\r\n".join(lines) + "\r\n",
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'inline; filename="shorts-studio.ics"'},
    )
