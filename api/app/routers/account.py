"""User panel: dashboard data, getting-started checklist, plan upgrade requests, public share links."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from studio_shared import db, storage, tokens
from studio_shared.notify import notify, notify_admins

from ..access import clip_for, project_for
from ..auth import AdminMember, CurrentMember, Member, audit
from ..plans import has_feature, require_feature
from ..ratelimit import check_ip_rate

router = APIRouter(tags=["account"])


# ---------------------------------------------------------------- dashboard
def checklist(m: Member) -> list[dict[str, Any]]:
    row = db.fetch_one(
        """select
             exists(select 1 from projects where created_by = %(u)s and type = 'clip') as clip,
             exists(select 1 from projects where created_by = %(u)s and type = 'story') as story,
             exists(select 1 from clips c join projects p on p.id = c.project_id
                     where p.created_by = %(u)s and c.status = 'ready') as ready,
             exists(select 1 from brand_kits where user_id = %(u)s) as brand,
             exists(select 1 from share_links where created_by = %(u)s) as shared""",
        {"u": m.user_id},
    )
    items = [
        {
            "id": "first_clip",
            "label": "Paste a link and make your first Shorts",
            "done": row["clip"],
            "href": "/clipper/new",
        },
        {"id": "download", "label": "Download a finished video", "done": row["ready"], "href": "/clipper"},
        {
            "id": "first_story",
            "label": "Create an AI story video",
            "done": row["story"],
            "href": "/story/new",
        },
    ]
    if has_feature(m, "brand_kit"):
        items.append(
            {
                "id": "brand",
                "label": "Add your logo and @handle",
                "done": row["brand"],
                "href": "/account/brand",
            }
        )
    if has_feature(m, "share_links"):
        items.append(
            {"id": "share", "label": "Share a video with a link", "done": row["shared"], "href": "/clipper"}
        )
    return items


@router.get("/me/dashboard")
def dashboard(m: CurrentMember) -> dict:
    recent = db.fetch_all(
        """select p.id, p.type, p.title, p.status, p.thumbnail_key, p.updated_at, p.meta->>'tool' as tool,
                  (select count(*) from clips c where c.project_id = p.id and c.status = 'ready') as ready_clips
             from projects p where p.created_by = %s order by p.updated_at desc limit 8""",
        [m.user_id],
    )
    running = db.fetch_one(
        "select count(*) as n from jobs where created_by = %s and status in ('queued','running')", [m.user_id]
    )["n"]
    spent = db.fetch_one(
        "select coalesce(-sum(delta), 0) as n from token_ledger where user_id = %s and reason = 'charge' "
        "and ts > now() - interval '7 days'",
        [m.user_id],
    )["n"]
    pending = db.fetch_one(
        "select plan_id, created_at from upgrade_requests where user_id = %s and status = 'pending'",
        [m.user_id],
    )
    return {
        "wallet": tokens.get_wallet(m.user_id).to_json(),
        "recent": recent,
        "running_jobs": running,
        "spent_7d": int(spent),
        "checklist": checklist(m),
        "pending_upgrade": pending,
        "announcements": db.fetch_all(
            "select id, message, level, created_at from announcements "
            "where active and (expires_at is null or expires_at > now()) order by created_at desc limit 3"
        ),
    }


# ---------------------------------------------------------------- upgrade requests
class UpgradeIn(BaseModel):
    plan_id: str = Field(max_length=40)
    note: str = Field(default="", max_length=500)


@router.post("/billing/upgrade-request", status_code=201)
def request_upgrade(body: UpgradeIn, m: CurrentMember) -> dict:
    """Ask for a bigger plan. The owner/admins approve it (online payment can be connected later)."""
    plan = db.fetch_one("select id, name, public from plans where id = %s", [body.plan_id])
    if not plan or not plan["public"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown plan")
    if m.unlimited:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your account already has everything unlocked.")
    if plan["id"] == m.plan_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"You're already on {plan['name']}.")
    if db.fetch_one("select 1 from upgrade_requests where user_id = %s and status = 'pending'", [m.user_id]):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "You already have a request waiting. Cancel it to ask for another plan."
        )
    row = db.fetch_one(
        "insert into upgrade_requests (user_id, plan_id, note) values (%s, %s, %s) returning *",
        [m.user_id, plan["id"], body.note.strip()],
    )
    notify_admins(
        f"Upgrade request: {plan['name']}",
        f"{m.display_name or m.email} asked for {plan['name']}."
        + (f" Note: {body.note.strip()}" if body.note.strip() else ""),
        link="/admin/requests",
    )
    return row


@router.get("/billing/upgrade-request")
def my_requests(m: CurrentMember) -> list[dict]:
    return db.fetch_all(
        "select r.*, p.name as plan_name from upgrade_requests r join plans p on p.id = r.plan_id "
        "where r.user_id = %s order by r.created_at desc limit 10",
        [m.user_id],
    )


@router.delete("/billing/upgrade-request")
def cancel_request(m: CurrentMember) -> dict:
    db.execute(
        "update upgrade_requests set status = 'canceled' where user_id = %s and status = 'pending'",
        [m.user_id],
    )
    return {"ok": True}


@router.get("/admin/upgrade-requests")
def list_requests(_: AdminMember, state: str = "pending") -> list[dict]:
    return db.fetch_all(
        """select r.*, p.name as plan_name, m.email, m.display_name, m.plan_id as current_plan
             from upgrade_requests r join plans p on p.id = r.plan_id join members m on m.user_id = r.user_id
            where (%s = 'all' or r.status = %s) order by r.created_at desc limit 200""",
        [state, state],
    )


class DecisionIn(BaseModel):
    approve: bool
    reply: str = Field(default="", max_length=500)


@router.post("/admin/upgrade-requests/{request_id}")
def decide_request(request_id: str, body: DecisionIn, admin: AdminMember) -> dict:
    try:
        row = db.fetch_one(
            "update upgrade_requests set status = %s, decided_by = %s, decided_at = now(), reply = %s "
            "where id = %s and status = 'pending' returning *",
            ["approved" if body.approve else "declined", admin.user_id, body.reply.strip(), request_id],
        )
    except Exception as e:  # noqa: BLE001 - bad uuid
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found") from e
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found or already decided")
    plan = db.fetch_one("select name from plans where id = %s", [row["plan_id"]])
    uid = str(row["user_id"])
    if body.approve:
        db.execute("update members set plan_id = %s where user_id = %s", [row["plan_id"], uid])
        tokens.on_plan_change(uid, actor_id=admin.user_id)  # the bigger daily allowance applies today
        notify(
            uid,
            f"You're on {plan['name']} now",
            body.reply.strip() or "Your upgrade was approved. Enjoy!",
            kind="success",
            link="/account",
        )
    else:
        notify(
            uid, f"Your {plan['name']} request was declined", body.reply.strip(), kind="info", link="/pricing"
        )
    audit(
        admin, "upgrade.approve" if body.approve else "upgrade.decline", "member", uid, plan_id=row["plan_id"]
    )
    return row


# ---------------------------------------------------------------- share links
SHARE_DAYS = 30


class ShareIn(BaseModel):
    days: int | None = Field(default=SHARE_DAYS, ge=1, le=365)


@router.post("/clips/{clip_id}/share", status_code=201)
def share_clip(clip_id: str, body: ShareIn, m: CurrentMember) -> dict:
    require_feature(m, "share_links")
    clip = clip_for(clip_id, m)
    if clip["status"] != "ready" or not clip["video_key"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The clip isn't ready yet")
    return _make_link(m, str(clip["project_id"]), clip_id, body.days)


@router.post("/projects/{project_id}/share", status_code=201)
def share_story(project_id: str, body: ShareIn, m: CurrentMember) -> dict:
    require_feature(m, "share_links")
    p = project_for(project_id, m)
    if p["type"] != "story":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Share a clip from its card")
    st = db.fetch_one("select render_key from stories where project_id = %s", [project_id])
    if not st or not st["render_key"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Render the story first")
    return _make_link(m, project_id, None, body.days)


def _make_link(m: Member, project_id: str, clip_id: str | None, days: int | None) -> dict:
    token = secrets.token_urlsafe(18)
    expires = datetime.now(UTC) + timedelta(days=days) if days else None
    db.execute(
        "insert into share_links (token, project_id, clip_id, created_by, expires_at) values (%s,%s,%s,%s,%s)",
        [token, project_id, clip_id, m.user_id, expires],
    )
    return {"token": token, "path": f"/s/{token}", "expires_at": expires}


@router.get("/share-links")
def my_links(m: CurrentMember) -> list[dict]:
    return db.fetch_all(
        """select s.token, s.project_id, s.clip_id, s.views, s.expires_at, s.revoked_at, s.created_at,
                  coalesce(c.title, p.title) as title
             from share_links s join projects p on p.id = s.project_id left join clips c on c.id = s.clip_id
            where s.created_by = %s order by s.created_at desc limit 100""",
        [m.user_id],
    )


@router.delete("/share-links/{token}")
def revoke_link(token: str, m: CurrentMember) -> dict:
    row = db.fetch_one(
        "update share_links set revoked_at = now() where token = %s and (created_by = %s or %s) returning token",
        [token, m.user_id, m.is_admin],
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link not found")
    return {"ok": True}


@router.get("/public/share/{token}")
def view_share(token: str, request: Request) -> dict:
    """Public, no sign-in: what a share link shows. Short-lived signed URLs; counts views."""
    check_ip_rate(request.client.host if request.client else "?", "share", limit=60)
    if not (16 <= len(token) <= 64):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This link doesn't exist")
    s = db.fetch_one(
        """update share_links set views = views + 1
            where token = %s and revoked_at is null and (expires_at is null or expires_at > now()) returning *""",
        [token],
    )
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This link has expired or was turned off")
    owner = db.fetch_one("select display_name from members where user_id = %s", [s["created_by"]]) or {}
    if s["clip_id"]:
        c = db.fetch_one("select * from clips where id = %s", [s["clip_id"]])
        if not c or not c["video_key"]:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "This video is no longer available")
        return {
            "title": c["title"],
            "description": c["description"],
            "hashtags": c["hashtags"],
            "aspect": c.get("aspect") or "9:16",
            "duration": float(c["duration_s"] or 0),
            "video_url": storage.presign_get(c["video_key"], expires=3600),
            "poster_url": storage.presign_get(c["thumb_key"], expires=3600) if c["thumb_key"] else None,
            "download_url": storage.presign_get(c["video_key"], expires=3600, filename=c["filename"]),
            "by": owner.get("display_name"),
        }
    st = db.fetch_one(
        "select s.render_key, s.thumb_key, s.description, s.hashtags, p.title from stories s "
        "join projects p on p.id = s.project_id where s.project_id = %s",
        [s["project_id"]],
    )
    if not st or not st["render_key"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This video is no longer available")
    return {
        "title": st["title"],
        "description": st["description"] or "",
        "hashtags": st["hashtags"] or [],
        "aspect": "9:16",
        "duration": None,
        "video_url": storage.presign_get(st["render_key"], expires=3600),
        "poster_url": storage.presign_get(st["thumb_key"], expires=3600) if st.get("thumb_key") else None,
        "download_url": storage.presign_get(st["render_key"], expires=3600, filename="story.mp4"),
        "by": owner.get("display_name"),
    }
