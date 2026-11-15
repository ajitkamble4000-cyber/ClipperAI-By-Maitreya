import pytest
from studio_shared import db

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def no_queue(monkeypatch):
    sent = []
    monkeypatch.setattr("app.routers.story.enqueue", lambda job: sent.append(job))
    return sent


@pytest.fixture
def story(make_member):
    uid, _, hdr = make_member("admin")
    pid = db.fetch_one(
        "insert into projects (type, title, created_by) values ('story','s',%s) returning id", [uid]
    )["id"]
    db.execute("insert into stories (project_id, idea) values (%s, 'i')", [pid])
    for i in range(3):
        db.execute(
            "insert into scenes (project_id, idx, narration, image_prompt, audio_start_s, audio_end_s) "
            "values (%s,%s,'n','p',%s,%s)",
            [pid, i, i * 3.0, i * 3.0 + (3 if i < 2 else 9)],
        )
    yield uid, pid, hdr
    db.execute("delete from projects where id = %s", [pid])


def _upload(uid, purpose, name):
    return str(
        db.fetch_one(
            "insert into uploads (user_id, purpose, r2_key, filename, content_type, size_bytes, part_size, status) "
            "values (%s,%s,%s,%s,'application/octet-stream',10,10,'complete') returning id",
            [uid, purpose, f"uploads/{uid}/x/{name}", name],
        )["id"]
    )


def test_estimates_use_pricing_table(client, story, monkeypatch):
    uid, pid, hdr = story
    monkeypatch.setattr(
        "studio_shared.app_settings.model_for",
        lambda role: {"image": "gemini-2.5-flash-image", "video": "veo-3.1-fast-generate-preview"}.get(role),
    )
    r = client.get(f"/story/{pid}/estimate", params={"what": "images"}, headers=hdr).json()
    assert (
        r["images"] == 3
        and r["per_image"] == pytest.approx(0.039)
        and r["estimated_usd"] == pytest.approx(0.117)
    )
    v = client.get(f"/story/{pid}/estimate", params={"what": "veo"}, headers=hdr).json()
    assert v["seconds"] == 4 + 4 + 8 and v["estimated_usd"] == pytest.approx(16 * 0.15)


def test_uploaded_scene_image_and_voiceover(client, story):
    uid, pid, hdr = story
    sc = db.fetch_one("select id from scenes where project_id = %s and idx = 0", [pid])["id"]
    up = _upload(uid, "image", "my.png")
    r = client.post(f"/scenes/{sc}/image/upload", json={"upload_id": up}, headers=hdr)
    assert r.status_code == 200
    assert db.fetch_one("select image_source from scenes where id = %s", [sc])["image_source"] == "upload"
    # wrong purpose is rejected
    assert (
        client.post(
            f"/scenes/{sc}/image/upload", json={"upload_id": _upload(uid, "music", "a.mp3")}, headers=hdr
        ).status_code
        == 400
    )
    vo = _upload(uid, "voiceover", "me.m4a")
    assert (
        client.put(f"/story/{pid}/voiceover", json={"upload_id": vo}, headers=hdr)
        .json()["voiceover_key"]
        .endswith("me.m4a")
    )
    assert (
        client.put(f"/story/{pid}/voiceover", json={"upload_id": None}, headers=hdr).json()["voiceover_key"]
        is None
    )


def test_budget_blocks_premium(client, story):
    uid, pid, hdr = story
    db.execute("update settings set monthly_budget_usd = 0.01 where id = 1")
    db.execute("insert into usage_events (model, kind, cost_usd) values ('x', 'image', 5)")
    try:
        r = client.post(f"/story/{pid}/images", json={}, headers=hdr)
        assert r.status_code == 402 and "budget" in r.json()["detail"].lower()
    finally:
        db.execute("update settings set monthly_budget_usd = null where id = 1")
        db.execute("delete from usage_events where model = 'x'")


def test_render_and_conflicts(client, story, no_queue):
    uid, pid, hdr = story
    assert client.post(f"/story/{pid}/render", headers=hdr).status_code == 201
    assert client.post(f"/story/{pid}/render", headers=hdr).status_code == 409


def test_library_admin_only(client, make_member):
    uid, _, admin = make_member("admin")
    _, _, member = make_member("member")
    up = _upload(uid, "music", "song.mp3")
    assert (
        client.post(
            "/library/music", json={"upload_id": up, "name": "Song", "mood": "epic"}, headers=member
        ).status_code
        == 403
    )
    r = client.post("/library/music", json={"upload_id": up, "name": "Song", "mood": "epic"}, headers=admin)
    assert r.status_code == 201
    db.execute("delete from music_tracks where id = %s", [r.json()["id"]])
    s = client.post(
        "/library/styles",
        json={"name": "Retro VHS", "prompt": "grainy 1990s VHS footage look, scanlines"},
        headers=admin,
    )
    assert s.status_code == 201 and s.json()["id"] == "retro_vhs"
    assert client.delete("/library/styles/realistic_3d", headers=admin).status_code == 400
    client.delete("/library/styles/retro_vhs", headers=admin)
