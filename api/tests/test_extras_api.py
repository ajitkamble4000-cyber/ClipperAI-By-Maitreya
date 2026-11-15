"""Creator extras API: templates, thumbnails, title ideas, batch story topics, new genres."""

from __future__ import annotations

import pytest
from studio_shared import db, tokens

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def no_queue(monkeypatch):
    sent = []
    monkeypatch.setattr("app.plans.enqueue", lambda job: sent.append(job))
    return sent


def test_templates(client, make_member):
    _, _, free = make_member(plan="free")
    builtin = client.get("/templates", headers=free, params={"kind": "clip"}).json()
    assert any(t["name"] == "Podcast highlights" and t["builtin"] for t in builtin)
    body = {
        "kind": "clip",
        "name": "My style",
        "settings": {"mode": "captions", "aspect": "1:1", "url": "x", "brand": {}},
    }
    r = client.post("/templates", headers=free, json=body)
    assert r.status_code == 403 and "Templates" in r.json()["detail"]
    _, _, pro = make_member(plan="pro")
    r = client.post("/templates", headers=pro, json=body)
    assert r.status_code == 201 and r.json()["settings"] == {
        "mode": "captions",
        "aspect": "1:1",
    }  # no source/brand kept
    tid = r.json()["id"]
    mine = client.get("/templates", headers=pro, params={"kind": "clip"}).json()
    assert mine[-1]["id"] == tid and not mine[-1]["builtin"]
    assert all(
        t["id"] != tid for t in client.get("/templates", headers=free, params={"kind": "clip"}).json()
    )  # private
    assert client.delete(f"/templates/{builtin[0]['id']}", headers=pro).status_code == 404  # built-ins stay
    assert client.delete(f"/templates/{tid}", headers=pro).status_code == 200


def _clip(uid: str, status: str = "ready") -> tuple[str, str]:
    pid = str(
        db.fetch_one(
            "insert into projects (type, title, created_by) values ('clip','P',%s) returning id", [uid]
        )["id"]
    )
    cid = str(
        db.fetch_one(
            "insert into clips (project_id, idx, start_s, end_s, title, status, thumb_key) values (%s,1,0,10,'T',%s,'x.jpg') returning id",
            [pid, status],
        )["id"]
    )
    return pid, cid


def test_thumbnail_and_ideas_jobs(client, make_member, no_queue):
    uid, _, free = make_member(plan="free")
    _, cid = _clip(uid)
    assert client.post(f"/clips/{cid}/thumbnail", headers=free, json={}).status_code == 403
    assert client.post(f"/clips/{cid}/ideas", headers=free).status_code == 403
    db.execute("update members set plan_id = 'pro' where user_id = %s", [uid])
    r = client.post(f"/clips/{cid}/thumbnail", headers=free, json={"style": "ai", "text": "Big words"})
    assert r.status_code == 201, r.text
    assert r.json()["tokens_charged"] == tokens.price("thumbnail") and no_queue[-1]["kind"] == "thumbnail"
    assert client.post(f"/clips/{cid}/thumbnail", headers=free, json={}).status_code == 409  # one at a time
    r = client.post(f"/clips/{cid}/ideas", headers=free)
    assert r.status_code == 201 and r.json()["tokens_charged"] == tokens.price("title_variants")
    _, other = make_member(plan="pro")[0], make_member(plan="pro")[2]
    assert client.post(f"/clips/{cid}/ideas", headers=other).status_code == 404  # not theirs


def test_story_batch_and_genres(client, make_member, no_queue):
    _, _, pro = make_member(plan="pro")
    assert (
        client.post(
            "/story/projects", headers=pro, json={"idea": "A cloud afraid of thunder", "genre": "bedtime"}
        ).status_code
        == 201
    )
    assert (
        client.post("/story/projects", headers=pro, json={"idea": "Nope", "genre": "made_up"}).status_code
        == 422
    )
    assert (
        client.post("/story/batch", headers=pro, json={"ideas": ["one topic", "two topic"]}).status_code
        == 403
    )  # Business
    _, _, biz = make_member(plan="business")
    r = client.post(
        "/story/batch",
        headers=biz,
        json={
            "ideas": ["Why cats purr", "Why cats purr", "How volcanoes form", "x"],
            "settings": {"genre": "facts", "length_s": 30},
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["requested"] == 2 and len(body["created"]) == 2 and body["error"] is None
    genres = {
        db.fetch_one("select genre from stories where project_id = %s", [c["project_id"]])["genre"]
        for c in body["created"]
    }
    assert genres == {"facts"} and all(j["kind"] == "story_script" for j in no_queue[-2:])
