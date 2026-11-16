"""Content calendar: schedule, update, privacy, reminders and the private .ics feed."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from studio_shared import db
from studio_shared.calendar_reminders import send_due

pytestmark = pytest.mark.integration


def _clip(uid: str) -> tuple[str, str]:
    pid = str(
        db.fetch_one(
            "insert into projects (type, title, created_by) values ('clip','Cal',%s) returning id", [uid]
        )["id"]
    )
    cid = str(
        db.fetch_one(
            "insert into clips (project_id, idx, start_s, end_s, title, status) values (%s,1,0,9,'My clip','ready') returning id",
            [pid],
        )["id"]
    )
    return pid, cid


def test_schedule_and_update(client, make_member):
    uid, _, hdr = make_member()
    pid, cid = _clip(uid)
    when = (datetime.now(UTC) + timedelta(days=2)).replace(microsecond=0)
    r = client.post(
        "/calendar",
        headers=hdr,
        json={
            "clip_id": cid,
            "platform": "tiktok",
            "scheduled_at": when.isoformat(),
            "caption": "New clip! #shorts",
        },
    )
    assert r.status_code == 201, r.text
    item = r.json()
    assert item["project_id"] == pid and item["clip_title"] == "My clip" and item["status"] == "planned"
    rng = {"from": (when - timedelta(days=1)).isoformat(), "to": (when + timedelta(days=1)).isoformat()}
    assert [i["id"] for i in client.get("/calendar", headers=hdr, params=rng).json()] == [item["id"]]
    r = client.patch(
        f"/calendar/{item['id']}",
        headers=hdr,
        json={"status": "posted", "posted_url": "https://tiktok.com/@me/video/1"},
    )
    assert r.json()["status"] == "posted"
    assert (
        client.patch(
            f"/calendar/{item['id']}", headers=hdr, json={"posted_url": "javascript:alert(1)"}
        ).status_code
        == 400
    )
    _, _, other = make_member()
    assert client.get("/calendar", headers=other, params=rng).json() == []
    assert (
        client.patch(f"/calendar/{item['id']}", headers=other, json={"status": "skipped"}).status_code == 404
    )
    assert (
        client.post(
            "/calendar",
            headers=other,
            json={"clip_id": cid, "platform": "x", "scheduled_at": when.isoformat()},
        ).status_code
        == 404
    )
    assert client.delete(f"/calendar/{item['id']}", headers=hdr).status_code == 200
    too_long = {"from": rng["from"], "to": (when + timedelta(days=200)).isoformat()}
    assert client.get("/calendar", headers=hdr, params=too_long).status_code == 400


def test_reminders_once(client, make_member):
    uid, _, hdr = make_member()
    _, cid = _clip(uid)
    soon = datetime.now(UTC) + timedelta(minutes=10)
    client.post(
        "/calendar",
        headers=hdr,
        json={"clip_id": cid, "platform": "youtube", "scheduled_at": soon.isoformat(), "remind_minutes": 30},
    )
    later = datetime.now(UTC) + timedelta(days=3)
    client.post(
        "/calendar", headers=hdr, json={"clip_id": cid, "platform": "x", "scheduled_at": later.isoformat()}
    )
    assert send_due() >= 1
    titles = [n["title"] for n in db.fetch_all("select title from notifications where user_id = %s", [uid])]
    assert titles.count("Time to post on YouTube") == 1 and "Time to post on X" not in titles
    send_due()
    assert [
        n["title"] for n in db.fetch_all("select title from notifications where user_id = %s", [uid])
    ].count("Time to post on YouTube") == 1


def test_ics_feed(client, make_member):
    uid, _, hdr = make_member()
    _, cid = _clip(uid)
    when = datetime(2030, 5, 4, 15, 30, tzinfo=UTC)
    client.post(
        "/calendar",
        headers=hdr,
        json={
            "clip_id": cid,
            "platform": "instagram",
            "scheduled_at": when.isoformat(),
            "caption": "Hi, there; friends",
        },
    )
    feed = client.get("/calendar/feed", headers=hdr).json()
    token = feed["token"]
    assert feed["url"].endswith(f"/public/calendar/{token}.ics")
    ics = client.get(f"/public/calendar/{token}.ics")  # no sign-in: the token is the secret
    assert ics.status_code == 200 and ics.headers["content-type"].startswith("text/calendar")
    body = ics.text
    assert "BEGIN:VCALENDAR" in body and "DTSTART:20300504T153000Z" in body
    assert "SUMMARY:Post on Instagram: My clip" in body and "Hi\\, there\\; friends" in body
    new = client.post("/calendar/feed/reset", headers=hdr).json()["token"]
    assert client.get(f"/public/calendar/{token}.ics").status_code == 404 and new != token
