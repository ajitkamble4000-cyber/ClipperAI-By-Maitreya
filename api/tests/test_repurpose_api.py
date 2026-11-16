"""Repurpose API and transcript search (only what you're allowed to see)."""

from __future__ import annotations

import pytest
from studio_shared import db, tokens

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def no_queue(monkeypatch):
    sent = []
    monkeypatch.setattr("app.plans.enqueue", lambda job: sent.append(job))
    return sent


def _project(uid: str, title: str, text: str, segments: list[dict]) -> str:
    pid = str(
        db.fetch_one(
            "insert into projects (type, title, created_by) values ('clip',%s,%s) returning id", [title, uid]
        )["id"]
    )
    db.execute(
        "insert into project_transcripts (project_id, language, text, segments) values (%s,'en',%s,%s)",
        [pid, text, db.jsonb(segments)],
    )
    return pid


def test_repurpose_launch_and_markdown(client, make_member, no_queue):
    uid, _, hdr = make_member()
    pid = _project(uid, "My talk", "hello", [])
    r = client.post(f"/projects/{pid}/repurpose", headers=hdr)
    assert (
        r.status_code == 201
        and r.json()["tokens_charged"] == tokens.price("repurpose")
        and no_queue[-1]["kind"] == "repurpose"
    )
    assert client.post(f"/projects/{pid}/repurpose", headers=hdr).status_code == 409  # one at a time
    assert client.get(f"/projects/{pid}/repurpose.md", headers=hdr).status_code == 404  # nothing yet
    db.execute(
        "update projects set repurpose = %s where id = %s",
        [
            db.jsonb(
                {
                    "summary": "Short.",
                    "chapters_text": "0:00 Intro",
                    "quotes": ["Q"],
                    "x_thread": ["one", "two"],
                    "linkedin_post": "L",
                    "newsletter": "N",
                    "keywords": ["k"],
                    "blog_post": "# Blog",
                }
            ),
            pid,
        ],
    )
    md = client.get(f"/projects/{pid}/repurpose.md", headers=hdr)
    assert md.status_code == 200 and "## Chapters" in md.text and "1. one" in md.text and "# Blog" in md.text
    assert 'filename="my-talk-writeup.md"' in md.headers["content-disposition"]
    _, _, other = make_member()
    assert client.get(f"/projects/{pid}/repurpose", headers=other).status_code == 404


def test_search_what_was_said(client, make_member):
    a, _, ha = make_member()
    b, _, hb = make_member()
    word = f"zebra{a[:6]}"
    pa = _project(
        a,
        "Safari",
        f"we saw a {word} near the river",
        [
            {"start": 0, "end": 5, "text": "intro"},
            {"start": 61.5, "end": 66, "text": f"we saw a {word} near the river"},
        ],
    )
    _project(
        b, "Private", f"my secret {word} story", [{"start": 0, "end": 3, "text": f"my secret {word} story"}]
    )
    res = client.get("/search/transcripts", headers=ha, params={"q": word}).json()
    assert [r["project_id"] for r in res] == [pa]  # never someone else's video
    assert res[0]["at"] == 61.5 and f"<<{word}>>" in res[0]["snippet"]
    assert client.get("/search/transcripts", headers=ha, params={"q": "x"}).status_code == 422
    _, _, admin = make_member("admin")
    assert len(client.get("/search/transcripts", headers=admin, params={"q": word}).json()) == 2


def test_downloads_expose_file_names_to_the_browser(client, make_member):
    from studio_shared.config import get_settings

    uid, _, hdr = make_member()
    pid = _project(uid, "Named", "x", [])
    db.execute("update projects set repurpose = %s where id = %s", [db.jsonb({"summary": "S"}), pid])
    origin = get_settings().origins[0]
    r = client.get(f"/projects/{pid}/repurpose.md", headers={**hdr, "Origin": origin})
    assert "content-disposition" in r.headers.get("access-control-expose-headers", "").lower()
