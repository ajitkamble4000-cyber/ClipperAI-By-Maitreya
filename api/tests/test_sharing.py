"""Project sharing: viewers watch, editors change; enforced by the API and by the database rules (RLS)."""

from __future__ import annotations

import httpx
import pytest
from authutil import ANON_KEY
from studio_shared import db
from studio_shared.config import get_settings

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def no_queue(monkeypatch):
    monkeypatch.setattr("app.plans.enqueue", lambda job: None)


def _project(uid: str) -> tuple[str, str]:
    pid = str(
        db.fetch_one(
            "insert into projects (type, title, created_by) values ('clip','Shared one',%s) returning id",
            [uid],
        )["id"]
    )
    cid = str(
        db.fetch_one(
            "insert into clips (project_id, idx, start_s, end_s, title, status) values (%s,1,0,9,'C','ready') returning id",
            [pid],
        )["id"]
    )
    return pid, cid


def _rest(token: str, method: str, path: str, body=None) -> httpx.Response:
    hdr = {"apikey": ANON_KEY, "Authorization": token, "Prefer": "return=representation"}
    return httpx.request(method, f"{get_settings().supabase_url}/rest/v1/{path}", headers=hdr, json=body)


def test_share_viewer_and_editor(client, make_member):
    owner, _, ohdr = make_member(plan="pro")
    viewer, vemail, vhdr = make_member()
    editor, eemail, ehdr = make_member()
    pid, cid = _project(owner)
    assert client.get(f"/projects/{pid}/members", headers=vhdr).status_code == 404  # not shared yet

    r = client.post(
        f"/projects/{pid}/members", headers=ohdr, json={"email": vemail.upper(), "role": "viewer"}
    )
    assert r.status_code == 201 and r.json()["role"] == "viewer"
    client.post(f"/projects/{pid}/members", headers=ohdr, json={"email": eemail, "role": "editor"})
    assert (
        client.post(
            f"/projects/{pid}/members", headers=ohdr, json={"email": "nobody-here@example.com"}
        ).status_code
        == 404
    )
    note = db.fetch_one(
        "select title, link from notifications where user_id = %s order by created_at desc limit 1", [viewer]
    )
    assert "shared “Shared one” with you" in note["title"] and note["link"] == f"/clipper/{pid}"

    # viewer: sees and downloads, can't change
    assert client.get(f"/projects/{pid}/members", headers=vhdr).json()["my_access"] == "viewer"
    assert [p["id"] for p in client.get("/shared-with-me", headers=vhdr).json()] == [pid]
    assert client.get(f"/files/sign?key=projects/{pid}/clips/x/v.mp4", headers=vhdr).status_code == 200
    r = client.post(f"/clips/{cid}/rerender", headers=vhdr, json={"music_mood": "calm"})
    assert r.status_code == 403 and "view this project but not change it" in r.json()["detail"]
    assert client.post(f"/projects/{pid}/repurpose", headers=vhdr).status_code == 403
    assert client.post(f"/projects/{pid}/members", headers=vhdr, json={"email": eemail}).status_code == 403
    # editor: can change (and pays for their own jobs)
    assert client.post(f"/clips/{cid}/rerender", headers=ehdr, json={"music_mood": "calm"}).status_code == 201

    # database rules match: both can read the clip, only the editor can rename it
    assert len(_rest(vhdr["Authorization"], "GET", f"clips?id=eq.{cid}&select=id").json()) == 1
    assert _rest(vhdr["Authorization"], "PATCH", f"clips?id=eq.{cid}", {"title": "hacked"}).json() == []
    assert (
        _rest(ehdr["Authorization"], "PATCH", f"clips?id=eq.{cid}", {"title": "Better title"}).json()[0][
            "title"
        ]
        == "Better title"
    )

    # role change, leave, owner removal
    assert (
        client.patch(f"/projects/{pid}/members/{viewer}", headers=ohdr, json={"role": "editor"}).json()[
            "role"
        ]
        == "editor"
    )
    assert client.delete(f"/projects/{pid}/members/{viewer}", headers=vhdr).status_code == 200  # leave
    assert client.get(f"/projects/{pid}/members", headers=vhdr).status_code == 404
    assert client.delete(f"/projects/{pid}/members/{editor}", headers=ohdr).status_code == 200
    assert client.post(f"/clips/{cid}/rerender", headers=ehdr, json={}).status_code == 404


def test_sharing_needs_pro(client, make_member):
    owner, _, ohdr = make_member(plan="free")
    _, email, _ = make_member()
    pid, _ = _project(owner)
    r = client.post(f"/projects/{pid}/members", headers=ohdr, json={"email": email})
    assert r.status_code == 403 and "Share projects with collaborators" in r.json()["detail"]


def test_story_share_database_rules(client, make_member):
    owner, _, ohdr = make_member(plan="pro")
    _, vemail, vhdr = make_member()
    _, eemail, ehdr = make_member()
    pid = str(
        db.fetch_one(
            "insert into projects (type, title, created_by) values ('story','Shared story',%s) returning id",
            [owner],
        )["id"]
    )
    db.execute("insert into stories (project_id, idea) values (%s, 'i')", [pid])
    sid = str(
        db.fetch_one(
            "insert into scenes (project_id, idx, narration, image_prompt) values (%s,1,'Hello','p') returning id",
            [pid],
        )["id"]
    )
    client.post(f"/projects/{pid}/members", headers=ohdr, json={"email": vemail, "role": "viewer"})
    client.post(f"/projects/{pid}/members", headers=ohdr, json={"email": eemail, "role": "editor"})
    v, e = vhdr["Authorization"], ehdr["Authorization"]
    assert len(_rest(v, "GET", f"scenes?project_id=eq.{pid}&select=id").json()) == 1
    assert _rest(v, "PATCH", f"scenes?id=eq.{sid}", {"narration": "nope"}).json() == []
    assert _rest(v, "PATCH", f"stories?project_id=eq.{pid}", {"title": "nope"}).json() == []
    r = _rest(v, "POST", "scenes", {"project_id": pid, "idx": 2, "narration": "x", "image_prompt": "p"})
    assert r.status_code in (401, 403)
    assert (
        _rest(e, "PATCH", f"scenes?id=eq.{sid}", {"narration": "Better"}).json()[0]["narration"] == "Better"
    )
    assert _rest(e, "PATCH", f"stories?project_id=eq.{pid}", {"title": "T"}).json()[0]["title"] == "T"
    assert client.post(f"/story/{pid}/script", headers=vhdr).status_code == 403
    # transcript search covers shared projects too
    db.execute(
        "insert into project_transcripts (project_id, text, segments) values (%s, 'the purple elephant dances', %s)",
        [pid, db.jsonb([{"start": 3.0, "end": 5.0, "text": "the purple elephant dances"}])],
    )
    hits = client.get("/search/transcripts", params={"q": "purple elephant"}, headers=vhdr).json()
    assert [h["project_id"] for h in hits] == [pid] and hits[0]["at"] == 3.0
