"""Any-link quick mode & captions tool: plan gating, token quotes, batch links, link inspection, caption files,
brand kit."""

from __future__ import annotations

import json
import uuid

import pytest
from studio_shared import db, storage, tokens

pytestmark = pytest.mark.integration

URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


@pytest.fixture(autouse=True)
def no_queue(monkeypatch):
    sent = []
    monkeypatch.setattr("app.plans.enqueue", lambda job: sent.append(job))
    return sent


def _job(job_id):
    return db.fetch_one("select * from jobs where id = %s", [job_id])


@pytest.mark.parametrize(
    ("extra", "feature"),
    [
        ({"aspect": "16:9"}, "Square / 4:5 / 16:9"),
        ({"translate_to": "es"}, "Caption translation"),
        ({"remove_silence": True}, "Filler & silence removal"),
        ({"keyword_emphasis": True}, "Keyword emphasis"),
        ({"use_brand": True}, "Brand kit"),
    ],
)
def test_free_plan_gets_upgrade_message_for_pro_options(client, make_member, extra, feature):
    _, _, hdr = make_member(plan="free")
    r = client.post("/clipper/projects", headers=hdr, json={"url": URL, **extra})
    assert r.status_code == 403 and feature in r.json()["detail"] and "Pro" in r.json()["detail"]


def test_captions_mode_quote_and_params(client, make_member, no_queue):
    _, _, hdr = make_member(plan="pro")
    r = client.post(
        "/clipper/projects",
        headers=hdr,
        json={
            "url": "https://www.tiktok.com/@a/video/1",
            "mode": "captions",
            "aspect": "4:5",
            "translate_to": "es",
            "remove_fillers": True,
            "keyword_emphasis": True,
            "emphasis_words": ["money", " "],
            "progress_bar": True,
        },
    )
    assert r.status_code == 201, r.text
    job = _job(r.json()["job_id"])
    p = job["params"]
    assert p["mode"] == "captions" and p["aspect"] == "4:5" and p["platform"] == "tiktok"
    assert p["emphasis_words"] == ["money"] and p["watermark"] is False and p["progress_bar"] is True
    want = tokens.price("captions_job") + tokens.price("translation") + tokens.price("jump_cuts")
    assert job["tokens_charged"] == want == p["_tokens"]["cost"]
    proj = db.fetch_one("select title, meta from projects where id = %s", [r.json()["project_id"]])
    assert proj["title"] == "Captioned video" and proj["meta"]["tool"] == "captions"


def test_free_plan_watermark_and_unknown_language(client, make_member):
    _, _, hdr = make_member(plan="free")
    r = client.post("/clipper/projects", headers=hdr, json={"url": URL, "mode": "auto"})
    assert r.status_code == 201 and _job(r.json()["job_id"])["params"]["watermark"] is True
    _, _, pro = make_member(plan="pro")
    assert (
        client.post("/clipper/projects", headers=pro, json={"url": URL, "translate_to": "xx"}).status_code
        == 422
    )


def test_partial_refund_is_idempotent_and_full_refund_after(make_member):
    uid, _, _ = make_member(plan="free")
    job = db.fetch_one(
        "insert into jobs (kind, status, created_by, params) values ('clip','running',%s,'{}') returning id",
        [uid],
    )
    jid = str(job["id"])
    start = tokens.get_wallet(uid).total
    tokens.charge(uid, 200, "clip", job_id=jid)
    assert tokens.partial_refund(jid, 120, "auto: short") == 120
    assert tokens.partial_refund(jid, 120, "auto: short") == 0  # same reason: no double refund
    assert tokens.get_wallet(uid).total == start - 80
    assert tokens.refund_job(jid, "failed") == 80  # a later failure returns only what's still charged
    assert tokens.get_wallet(uid).total == start
    assert tokens.partial_refund(jid, 10, "other") == 0


def test_batch_links(client, make_member, no_queue):
    _, _, free = make_member(plan="free")
    r = client.post("/clipper/batch", headers=free, json={"urls": [URL, "https://vimeo.com/1"]})
    assert r.status_code == 403 and "Batch mode" in r.json()["detail"]
    _, _, biz = make_member(plan="business")
    urls = [URL, "https://vimeo.com/1", "https://www.instagram.com/reel/abc/", URL]  # duplicate dropped
    r = client.post(
        "/clipper/batch", headers=biz, json={"urls": urls, "options": {"mode": "auto", "aspect": "1:1"}}
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["requested"] == 3 and len(body["created"]) == 3 and body["error"] is None
    assert {_job(c["job_id"])["params"]["platform"] for c in body["created"]} == {
        "youtube",
        "vimeo",
        "instagram",
    }
    assert len(no_queue) == 3  # batch jobs queue past the concurrency cap
    bad = client.post("/clipper/batch", headers=biz, json={"urls": [URL, "http://localhost/x"]})
    assert bad.status_code == 400  # one bad link rejects the batch before anything starts
    _, _, pro = make_member(plan="pro")
    many = [f"https://vimeo.com/{i}" for i in range(6)]
    assert client.post("/clipper/batch", headers=pro, json={"urls": many}).status_code == 403  # Pro: 5 max


def test_batch_stops_cleanly_when_tokens_run_out(client, make_member, no_queue):
    uid, _, hdr = make_member(plan="business")
    db.execute("update members set daily_tokens_override = 100 where user_id = %s", [uid])
    tokens.get_wallet(uid)  # refill to the override
    db.execute("update wallets set daily_balance = 100, bonus_balance = 0 where user_id = %s", [uid])
    r = client.post(
        "/clipper/batch",
        headers=hdr,
        json={"urls": [URL, "https://vimeo.com/2"], "options": {"mode": "captions"}},
    )
    body = r.json()
    assert r.status_code == 201 and len(body["created"]) == 2  # 40 + 40 tokens
    r = client.post("/clipper/batch", headers=hdr, json={"urls": [URL], "options": {"mode": "captions"}})
    assert r.json()["created"] == [] and r.json()["error"]["status"] == 402


def test_inspect_detects_platform(client, make_member, monkeypatch):
    monkeypatch.setattr("app.routers.clipper._probe_link", lambda url: {"title": "A talk", "duration": 45})
    _, _, hdr = make_member(plan="free")
    r = client.post(
        "/clipper/inspect", headers=hdr, json={"url": f"https://www.instagram.com/reel/{uuid.uuid4().hex}/"}
    )
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["platform"] == "instagram" and b["short_form"] and "cookies.txt" in b["help"]
    assert b["title"] == "A talk" and b["suggested_mode"] == "captions" and b["too_long"] is False
    assert client.post("/clipper/inspect", headers=hdr, json={"url": "http://10.0.0.1/x"}).status_code == 400


def test_options_reflect_plan(client, make_member):
    _, _, free = make_member(plan="free")
    o = client.get("/clipper/options", headers=free).json()
    assert {a["id"]: a["locked"] for a in o["aspects"]} == {
        "9:16": False,
        "1:1": True,
        "4:5": True,
        "16:9": True,
    }
    assert o["max_batch"] == 1 and any(lang["code"] == "es" for lang in o["languages"])


def test_caption_file_download(client, make_member):
    uid, _, hdr = make_member(plan="free")
    _, _, other = make_member(plan="free")
    pid = db.fetch_one(
        "insert into projects (type, title, created_by) values ('clip','T',%s) returning id", [uid]
    )["id"]
    key = f"projects/{pid}/clips/x/words.json"
    storage.put_bytes(
        key,
        json.dumps(
            [{"text": "Hola", "start": 0, "end": 0.5}, {"text": "amigos.", "start": 0.5, "end": 1.2}]
        ).encode(),
    )
    clip = db.fetch_one(
        "insert into clips (project_id, idx, start_s, end_s, filename, words_key, language) "
        "values (%s,1,0,1.2,'01-hola.mp4',%s,'es') returning id",
        [pid, key],
    )
    r = client.get(f"/clips/{clip['id']}/captions.srt", headers=hdr)
    assert r.status_code == 200 and "00:00:00,000 --> 00:00:01,200\nHola amigos." in r.text
    assert 'filename="01-hola.es.srt"' in r.headers["content-disposition"]
    assert client.get(f"/clips/{clip['id']}/captions.vtt", headers=hdr).text.startswith("WEBVTT")
    assert client.get(f"/clips/{clip['id']}/captions.txt", headers=other).status_code == 404  # not yours
    assert client.get(f"/clips/{clip['id']}/captions.doc", headers=hdr).status_code == 422
    db.execute("delete from projects where id = %s", [pid])


def test_brand_kit(client, make_member):
    uid, _, free = make_member(plan="free")
    assert client.get("/brand", headers=free).json()["available"] is False
    assert client.put("/brand", headers=free, json={"handle": "@me"}).status_code == 403
    uid, _, pro = make_member(plan="pro")
    r = client.put(
        "/brand", headers=pro, json={"handle": "@mychannel", "primary_color": "#00FF88", "progress_bar": True}
    )
    assert r.status_code == 200 and r.json()["handle"] == "@mychannel" and r.json()["saved"]
    assert client.put("/brand", headers=pro, json={"handle": "<script>"}).status_code == 422
    # logo from a finished image upload
    up = str(uuid.uuid4())
    src = f"uploads/{uid}/{up}/logo.png"
    storage.put_bytes(src, b"\x89PNG fake", "image/png")
    db.execute(
        "insert into uploads (id, user_id, purpose, r2_key, filename, content_type, size_bytes, part_size, status) "
        "values (%s,%s,'image',%s,'logo.png','image/png',9,9,'complete')",
        [up, uid, src],
    )
    r = client.put("/brand/logo", headers=pro, json={"upload_id": up})
    assert r.status_code == 200, r.text
    key = r.json()["logo_key"]
    assert key.startswith(f"brand/{uid}/logo-") and r.json()["logo_url"]
    # the brand kit is snapshotted into clip jobs that use it
    job = client.post("/clipper/projects", headers=pro, json={"url": URL, "use_brand": True})
    assert job.status_code == 201
    p = _job(job.json()["job_id"])["params"]
    assert (
        p["brand"]["logo_key"] == key and p["brand"]["handle"] == "@mychannel" and p["progress_bar"] is True
    )
    assert client.delete("/brand/logo", headers=pro).json()["logo_key"] is None
    assert not storage.exists(key)
