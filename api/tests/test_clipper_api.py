"""Clipper endpoints: validation, project + job creation, rerender guards."""

from __future__ import annotations

import pytest
from studio_shared import db

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def no_queue(monkeypatch):
    sent = []
    monkeypatch.setattr("app.plans.enqueue", lambda job: sent.append(job))
    monkeypatch.setattr("app.plans.enqueue", lambda job: sent.append(job))
    return sent


def test_create_from_url_creates_project_and_job(client, make_member, no_queue):
    _, _, hdr = make_member()
    r = client.post(
        "/clipper/projects",
        headers=hdr,
        json={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "num_clips": 4,
            "min_len": 60,
            "max_len": 30,
            "content_type": "sports",
            "reframe": "action",
            "caption_style": {"preset": "horror", "size": 90},
        },
    )
    assert r.status_code == 201, r.text
    job = db.fetch_one("select * from jobs where id = %s", [r.json()["job_id"]])
    assert job["kind"] == "clip" and job["params"]["min_len"] == 30 and job["params"]["max_len"] == 60
    assert job["params"]["caption_style"] == {"preset": "horror", "size": 90}
    assert len(no_queue) == 1
    db.execute("delete from projects where id = %s", [r.json()["project_id"]])


@pytest.mark.parametrize(
    "body,code",
    [
        ({"url": "http://localhost:8000/x"}, 400),
        ({"url": "http://169.254.169.254/latest"}, 400),
        ({"url": "file:///etc/passwd"}, 400),
        ({}, 422),
        ({"url": "https://youtu.be/x", "upload_id": "00000000-0000-0000-0000-000000000000"}, 422),
        ({"url": "https://youtu.be/x", "num_clips": 50}, 422),
        ({"url": "https://youtu.be/x", "caption_style": {"preset": "bold_pop", "color": "red;evil"}}, 422),
    ],
)
def test_validation(client, make_member, body, code):
    _, _, hdr = make_member()
    assert client.post("/clipper/projects", headers=hdr, json=body).status_code == code


def test_upload_must_belong_to_user(client, make_member):
    uid_a, _, _ = make_member()
    _, _, hdr_b = make_member()
    up = db.fetch_one(
        "insert into uploads (user_id, r2_key, filename, content_type, size_bytes, part_size, status) "
        "values (%s, 'k', 'a.mp4', 'video/mp4', 10, 10, 'complete') returning id",
        [uid_a],
    )
    r = client.post("/clipper/projects", headers=hdr_b, json={"upload_id": str(up["id"])})
    assert r.status_code == 404


def test_rerender_and_zip(client, make_member, no_queue):
    uid, _, hdr = make_member()
    pid = db.fetch_one(
        "insert into projects (type, title, created_by) values ('clip','t',%s) returning id", [uid]
    )["id"]
    cid = db.fetch_one(
        "insert into clips (project_id, idx, start_s, end_s, status) values (%s,1,10,40,'ready') "
        "returning id",
        [pid],
    )["id"]
    assert (
        client.post(f"/clips/{cid}/rerender", headers=hdr, json={"start": 10, "end": 11}).status_code == 400
    )
    r = client.post(
        f"/clips/{cid}/rerender", headers=hdr, json={"start": 12, "caption_style": {"preset": "karaoke"}}
    )
    assert r.status_code == 201
    params = {k: v for k, v in r.json()["params"].items() if k != "_tokens"}
    assert r.json()["params"]["_tokens"]["cost"] == 10
    assert params == {
        "clip_id": str(cid),
        "start": 12.0,
        "end": 40.0,
        "caption_style": {"preset": "karaoke"},
    }
    assert client.post(f"/clips/{cid}/rerender", headers=hdr, json={}).status_code == 409  # already queued
    assert client.post(f"/projects/{pid}/zip", headers=hdr).status_code == 201
    other_uid, _, other = make_member()
    assert client.delete(f"/projects/{pid}", headers=other).status_code == 404  # private: not even visible
    assert client.delete(f"/projects/{pid}", headers=hdr).status_code == 200
    assert db.fetch_one("select 1 from projects where id = %s", [pid]) is None
