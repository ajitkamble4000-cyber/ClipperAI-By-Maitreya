"""In-app notifications (the bell). Best effort: a failed notification never fails the action that sent it."""

from __future__ import annotations

import logging

from . import db

log = logging.getLogger(__name__)


def notify(user_id: str, title: str, body: str = "", *, kind: str = "info", link: str | None = None) -> None:
    try:
        db.execute(
            "insert into notifications (user_id, kind, title, body, link) values (%s, %s, %s, %s, %s)",
            [user_id, kind, title[:200], body[:1000], link],
        )
    except Exception:  # noqa: BLE001
        log.exception("notification failed")


def notify_admins(title: str, body: str = "", *, link: str | None = None) -> None:
    for r in db.fetch_all(
        "select user_id from members where role in ('owner', 'admin') and status = 'active'"
    ):
        notify(str(r["user_id"]), title, body, link=link)
