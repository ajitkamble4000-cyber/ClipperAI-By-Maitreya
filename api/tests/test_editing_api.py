"""Editing API: caption lines, saving fixed captions, exports, compilations, clip music options."""

from __future__ import annotations

import json

import pytest
from studio_shared import db, storage, tokens

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def no_queue(monkeypatch):
    sent = []
    monkeypatch.setattr("app.plans.enqueue", lambda job: sent.append(job))
    return sent


def _clip(
    uid: str, pid: str | None = None, *, aspect: str = "9:16", status: str = "ready"
) -> tuple[str, str]:
    if pid is None:
        pid = str(
            db.fetch_one(
                "insert into projects (type, title, created_by) values ('clip','P',%s) returning id", [uid]
            )["id"]
        )
    key = f"projects/{pid}/clips/{uid[:6]}-{aspect.replace(':', '')}/words.json"
    storage.put_bytes(
        key,
        json.dumps(
            [
                {"text": "Helo", "start": 0.0, "end": 0.5},
                {"text": "wrld.", "start": 0.5, "end": 1.0},
                {"text": "Second", "start": 2.0, "end": 2.5},
                {"text": "line", "start": 2.5, "end": 3.0},
            ]
        ).encode(),
    )
    cid = str(
        db.fetch_one(
            "insert into clips (project_id, idx, start_s, end_s, status, words_key, duration_s, aspect) "
            "values (%s,1,0,10,%s,%s,10,%s) returning id",
            [pid, status, key, aspect],
        )["id"]
    )
    return pid, cid


def test_cues_and_fixing_captions(client, make_member, no_queue):
    uid, _, hdr = make_member()
    _, cid = _clip(uid)
    cues = client.get(f"/clips/{cid}/cues", headers=hdr).json()
    assert [c["text"] for c in cues] == ["Helo wrld.", "Second line"]
    cues[0]["text"] = "Hello world."
    r = client.post(f"/clips/{cid}/captions", headers=hdr, json={"cues": cues})
    assert r.status_code == 201, r.text
    assert no_queue[-1]["kind"] == "clip_rerender" and no_queue[-1]["params"]["keep_words"] is True
    clip = db.fetch_one("select words_key, status from clips where id = %s", [cid])
    words = json.loads(storage.get_bytes(clip["words_key"]))
    assert [w["text"] for w in words][:2] == ["Hello", "world."] and clip["status"] == "queued"
    assert words[0]["start"] == 0.0 and words[1]["end"] <= 1.0 + 1e-6
    db.execute("update clips set status = 'ready' where id = %s", [cid])
    bad = client.post(
        f"/clips/{cid}/captions", headers=hdr, json={"cues": [{"start": 5, "end": 99, "text": "x"}]}
    )
    assert bad.status_code == 400
    _, _, other = make_member()
    assert client.get(f"/clips/{cid}/cues", headers=other).status_code == 404


def test_exports_are_free(client, make_member, no_queue):
    uid, _, hdr = make_member()
    _, cid = _clip(uid)
    r = client.post(f"/clips/{cid}/export", headers=hdr, json={"format": "mp3"})
    assert r.status_code == 201 and r.json()["tokens_charged"] == 0 and no_queue[-1]["kind"] == "clip_export"
    assert client.post(f"/clips/{cid}/export", headers=hdr, json={"format": "wav"}).status_code == 422


def test_compilation(client, make_member, no_queue):
    uid, _, hdr = make_member()
    pid, a = _clip(uid)
    _, b = _clip(uid, pid)
    r = client.post(
        f"/clipper/projects/{pid}/compilation", headers=hdr, json={"clip_ids": [a, b], "transition": "fade"}
    )
    assert r.status_code == 201 and r.json()["tokens_charged"] == tokens.price("compilation")
    _, c = _clip(uid, pid, aspect="1:1")
    r = client.post(f"/clipper/projects/{pid}/compilation", headers=hdr, json={"clip_ids": [a, c]})
    assert r.status_code == 400 and "same format" in r.json()["detail"]
    _, foreign = _clip(uid)  # another project
    assert (
        client.post(
            f"/clipper/projects/{pid}/compilation", headers=hdr, json={"clip_ids": [a, foreign]}
        ).status_code
        == 400
    )


def test_music_options(client, make_member, no_queue):
    uid, _, hdr = make_member(plan="pro")
    r = client.post(
        "/clipper/projects",
        headers=hdr,
        json={"url": "https://youtu.be/abc", "mode": "captions", "music_mood": "auto", "music_volume": 0.3},
    )
    assert r.status_code == 201
    assert no_queue[-1]["params"]["music"] == {"mood": "auto", "volume": 0.3}
    _, cid = _clip(uid)
    r = client.post(f"/clips/{cid}/rerender", headers=hdr, json={"music_mood": "calm"})
    assert r.status_code == 201 and no_queue[-1]["params"]["music"]["mood"] == "calm"
    assert (
        client.post(
            "/clipper/projects", headers=hdr, json={"url": "https://youtu.be/abc", "music_mood": "polka"}
        ).status_code
        == 422
    )
