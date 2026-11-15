import pytest
from studio_shared import db

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def no_queue(monkeypatch):
    sent = []
    monkeypatch.setattr("app.routers.story.enqueue", lambda job: sent.append(job))
    return sent


def test_create_story_starts_script_job(client, make_member, no_queue):
    _, _, hdr = make_member()
    r = client.post(
        "/story/projects",
        headers=hdr,
        json={
            "idea": "Scary story: the last bus at midnight",
            "genre": "scary",
            "visual_style": "dark_horror",
            "length_s": 60,
        },
    )
    assert r.status_code == 201, r.text
    pid = r.json()["project_id"]
    assert no_queue[0]["kind"] == "story_script"
    st = db.fetch_one("select * from stories where project_id = %s", [pid])
    assert st["genre"] == "scary" and st["length_s"] == 60
    # One AI task at a time per story.
    assert client.post(f"/story/{pid}/hook", headers=hdr).status_code == 409
    db.execute("delete from projects where id = %s", [pid])


@pytest.mark.parametrize(
    "body",
    [
        {"idea": "x"},
        {"idea": "ok idea", "length_s": 50},
        {"idea": "ok idea", "visual_style": "nope"},
        {"idea": "ok idea", "language": "fr"},
    ],
)
def test_validation(client, make_member, body):
    _, _, hdr = make_member()
    assert client.post("/story/projects", headers=hdr, json=body).status_code in (400, 422)


def test_members_can_edit_storyboard_directly_via_rls(make_member):
    import httpx
    from authutil import ANON_KEY
    from studio_shared.config import get_settings

    uid, _, hdr = make_member()
    pid = db.fetch_one(
        "insert into projects (type, title, created_by) values ('story','s',%s) returning id", [uid]
    )["id"]
    db.execute("insert into stories (project_id, idea) values (%s, 'i')", [pid])
    base = f"{get_settings().supabase_url}/rest/v1"
    h = {**hdr, "apikey": ANON_KEY, "Prefer": "return=representation"}
    r = httpx.post(f"{base}/scenes", headers=h, json={"project_id": str(pid), "idx": 0, "narration": "hello"})
    assert r.status_code == 201, r.text
    sid = r.json()[0]["id"]
    assert (
        httpx.patch(f"{base}/scenes?id=eq.{sid}", headers=h, json={"narration": "edited"}).status_code == 200
    )
    assert httpx.patch(f"{base}/scenes?id=eq.{sid}", headers=h, json={"image_key": "x"}).status_code in (
        401,
        403,
    )
    assert httpx.delete(f"{base}/scenes?id=eq.{sid}", headers=h).status_code in (200, 204)
    db.execute("delete from projects where id = %s", [pid])
