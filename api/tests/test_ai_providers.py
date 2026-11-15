"""Multi-provider AI with mocked HTTP: request shapes, parsing, fallback, usage/cost, transcription, admin API."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import httpx
import pytest
from pydantic import BaseModel
from studio_shared import db
from studio_shared.ai.base import ImagePart
from studio_shared.ai.client import AI

pytestmark = pytest.mark.integration
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "worker"))


class Out(BaseModel):
    title: str
    score: int


class Recorder:
    def __init__(self, handler):
        self.calls: list[httpx.Request] = []
        self.handler = handler

    def client(self, timeout: float = 120.0) -> httpx.Client:
        def h(req: httpx.Request) -> httpx.Response:
            self.calls.append(req)
            return self.handler(req)

        return httpx.Client(transport=httpx.MockTransport(h), timeout=timeout)


@pytest.fixture
def models_setting():
    before = db.fetch_one("select models from settings where id = 1")["models"]

    def set_models(m: dict):
        db.execute("update settings set models = %s where id = 1", [m])

    yield set_models
    db.execute("update settings set models = %s where id = 1", [before])


@pytest.fixture
def mock_http(monkeypatch):
    def install(handler) -> Recorder:
        rec = Recorder(handler)
        import studio_shared.ai.adapters.openai_like as ol
        import studio_shared.ai.adapters.others as ot

        monkeypatch.setattr(ol, "http_client", rec.client)
        monkeypatch.setattr(ot, "http_client", rec.client)
        return rec

    return install


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    for k in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENROUTER_API_KEY",
        "ELEVENLABS_API_KEY",
        "REPLICATE_API_TOKEN",
        "STABILITY_API_KEY",
    ):
        monkeypatch.setenv(k, f"test-{k.lower()}-1234")


def test_openai_json_schema_and_usage(mock_http, models_setting):
    models_setting({"text": "openai:gpt-4.1-mini"})

    def handler(req):
        body = json.loads(req.content)
        assert req.url.path == "/v1/chat/completions"
        assert req.headers["authorization"] == "Bearer test-openai_api_key-1234"
        assert body["response_format"]["type"] == "json_schema"
        assert body["response_format"]["json_schema"]["schema"]["properties"]["score"]["type"] == "integer"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"title": "Hi", "score": 7}'}}],
                "usage": {"prompt_tokens": 1000, "completion_tokens": 500},
            },
        )

    rec = mock_http(handler)
    out = AI().generate_json("prompt", Out, system="sys")
    assert out == Out(title="Hi", score=7) and len(rec.calls) == 1
    row = db.fetch_one("select * from usage_events where model = 'gpt-4.1-mini' order by id desc limit 1")
    assert row["provider"] == "openai" and float(row["cost_usd"]) == pytest.approx(
        1000 / 1e6 * 0.40 + 500 / 1e6 * 1.60
    )


def test_vision_frames_are_sent_as_images(mock_http, models_setting):
    models_setting({"text": "openrouter:openai/gpt-4o"})

    def handler(req):
        body = json.loads(req.content)
        assert req.url.host == "openrouter.ai" and req.headers["x-title"] == "Shorts Studio"
        content = body["messages"][-1]["content"]
        kinds = [c["type"] for c in content]
        assert kinds.count("image_url") == 2 and content[1]["image_url"]["url"].startswith(
            "data:image/jpeg;base64,"
        )
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"title": "x", "score": 1}'}}]})

    mock_http(handler)
    frames = [ImagePart(b"\xff\xd8a", label="Frame at 1.0s"), ImagePart(b"\xff\xd8b", label="Frame at 5.0s")]
    assert AI().generate_json([*frames, "what happens?"], Out).score == 1


def test_anthropic_forced_tool_and_fallback(mock_http, models_setting):
    models_setting({"text": "openai:gpt-4.1-mini", "text_fallback": ["anthropic:claude-sonnet-4-5"]})

    def handler(req):
        if req.url.host == "api.openai.com":
            return httpx.Response(503, json={"error": {"message": "overloaded"}})
        body = json.loads(req.content)
        assert req.headers["x-api-key"].startswith("test-anthropic")
        assert body["tool_choice"] == {"type": "tool", "name": "result"}
        return httpx.Response(
            200,
            json={
                "content": [{"type": "tool_use", "input": {"title": "Claude", "score": 9}}],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        )

    rec = mock_http(handler)
    assert AI().generate_json("p", Out).title == "Claude"
    assert [c.url.host for c in rec.calls] == ["api.openai.com", "api.anthropic.com"]


def test_bad_key_is_not_silently_swallowed(mock_http, models_setting):
    from studio_shared.ai.base import ProviderError

    models_setting({"text": "openai:gpt-4.1-mini"})
    mock_http(lambda req: httpx.Response(401, json={"error": {"message": "Incorrect API key"}}))
    with pytest.raises(ProviderError, match="rejected the API key"):
        AI().generate_text("hello")


def test_elevenlabs_tts_and_character_pricing(mock_http, models_setting, monkeypatch):
    models_setting({"tts": "elevenlabs:eleven_multilingual_v2"})
    monkeypatch.setattr("studio_shared.usage.assert_premium_allowed", lambda: None)

    def handler(req):
        assert (
            req.url.path == "/v1/text-to-speech/voice123" and req.url.params["output_format"] == "pcm_24000"
        )
        assert json.loads(req.content)["model_id"] == "eleven_multilingual_v2"
        return httpx.Response(200, content=b"\x00\x01" * 100)

    mock_http(handler)
    pcm = AI().tts("x" * 2000, voice="voice123", style="dramatic")
    assert len(pcm) == 200
    row = db.fetch_one(
        "select * from usage_events where model = 'eleven_multilingual_v2' order by id desc limit 1"
    )
    assert row["characters"] == 2000 and float(row["cost_usd"]) == pytest.approx(0.4)


def test_replicate_image_and_video(mock_http, models_setting, monkeypatch):
    models_setting(
        {"image": "replicate:black-forest-labs/flux-schnell", "video": "replicate:kwaivgi/kling-v2.1"}
    )
    monkeypatch.setattr("studio_shared.usage.assert_premium_allowed", lambda: None)
    state = {"polls": 0}

    def handler(req):
        if req.url.host == "files.example.com":
            return httpx.Response(200, content=b"PNGDATA" if req.url.path.endswith(".png") else b"MP4DATA")
        if req.method == "POST" and "flux-schnell" in req.url.path:
            assert req.headers["prefer"] == "wait=60"
            assert json.loads(req.content)["input"]["aspect_ratio"] == "9:16"
            return httpx.Response(
                201, json={"id": "img1", "status": "succeeded", "output": ["https://files.example.com/a.png"]}
            )
        if req.method == "POST" and "kling" in req.url.path:
            inp = json.loads(req.content)["input"]
            assert inp["start_image"].startswith("data:image/png;base64,") and inp["duration"] == 5
            return httpx.Response(201, json={"id": "vid1", "status": "starting"})
        if req.url.path == "/v1/predictions/vid1":
            state["polls"] += 1
            if state["polls"] < 2:
                return httpx.Response(200, json={"id": "vid1", "status": "processing"})
            return httpx.Response(
                200, json={"id": "vid1", "status": "succeeded", "output": "https://files.example.com/v.mp4"}
            )
        raise AssertionError(req.url)

    mock_http(handler)
    ai = AI()
    assert ai.generate_image("a cat") == b"PNGDATA"
    op = ai.start_video(prompt="move", image=b"img", mime="image/png", seconds=4)
    assert op.name == "replicate:vid1"
    op = ai.get_operation(ai.operation_from_name(op.name))
    assert not op.done
    op = ai.get_operation(op)
    assert op.done and not op.error
    assert ai.download_video(op, model="kwaivgi/kling-v2.1", seconds=4) == b"MP4DATA"


def test_stability_image(mock_http, models_setting, monkeypatch):
    models_setting({"image": "stability:core"})
    monkeypatch.setattr("studio_shared.usage.assert_premium_allowed", lambda: None)

    def handler(req):
        assert req.url.path == "/v2beta/stable-image/generate/core" and req.headers["accept"] == "image/*"
        assert b'name="aspect_ratio"' in req.content and b"9:16" in req.content
        return httpx.Response(200, content=b"IMG")

    mock_http(handler)
    assert AI().generate_image("castle") == b"IMG"
    row = db.fetch_one("select * from usage_events where model = 'stability:core' order by id desc limit 1")
    assert float(row["cost_usd"]) == pytest.approx(0.03)


def test_cloud_transcription_stitches_chunks(mock_http, models_setting, tmp_path, monkeypatch):
    from worker.transcribe import api_impl
    from worker.transcribe.faster_whisper_impl import transcriber_from_settings

    models_setting({"transcribe": "compat:whisper-large-v3"})
    db.execute(
        "insert into ai_providers (id, base_url) values ('compat', 'https://api.groq.com/openai/v1') "
        "on conflict (id) do update set base_url = excluded.base_url"
    )
    monkeypatch.setattr(api_impl, "CHUNK_SECONDS", 2)
    import subprocess

    wav = tmp_path / "a.wav"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=d=3.5", str(wav)], check=True)

    def handler(req):
        assert req.url.host == "api.groq.com" and req.url.path == "/openai/v1/audio/transcriptions"
        assert b"timestamp_granularities" in req.content
        return httpx.Response(
            200,
            json={
                "language": "english",
                "text": "hello world",
                "segments": [{"start": 0, "end": 1.5, "text": "hello world"}],
                "words": [
                    {"word": "hello", "start": 0.1, "end": 0.5},
                    {"word": "world", "start": 0.6, "end": 1.0},
                ],
            },
        )

    rec = mock_http(handler)
    t = transcriber_from_settings()
    assert isinstance(t, api_impl.APITranscriber)
    tr = t.transcribe(wav)
    assert len(rec.calls) == 2 and tr.language == "en"
    assert [round(w.start, 1) for w in tr.words] == [0.1, 0.6, 2.1, 2.6]  # second chunk shifted by 2 s


def test_admin_provider_api(client, make_member, mock_http, models_setting, monkeypatch):
    import uuid

    from authutil import create_auth_user, sign_in
    from studio_shared.config import get_settings

    monkeypatch.delenv("ANTHROPIC_API_KEY")
    _, _, admin = make_member("admin")
    email = f"owner-{uuid.uuid4().hex[:6]}@example.com"
    monkeypatch.setattr(get_settings(), "owner_email", email)
    db.execute("update members set role = 'admin' where role = 'owner'")
    oid = create_auth_user(email)
    owner = {"Authorization": f"Bearer {sign_in(email)}"}
    mock_http(
        lambda req: httpx.Response(
            200, json={"data": [{"id": "claude-sonnet-4-5", "display_name": "Claude Sonnet 4.5"}]}
        )
    )
    try:
        assert (
            client.put(
                "/settings/providers/anthropic", json={"key": "sk-ant-secret-9999"}, headers=admin
            ).status_code
            == 403
        )
        r = client.put("/settings/providers/anthropic", json={"key": "sk-ant-secret-9999"}, headers=owner)
        assert r.status_code == 200 and r.json()["key_masked"].endswith("9999") and "secret" not in r.text
        assert (
            "sk-ant"
            not in (db.fetch_one("select key_enc from ai_providers where id = 'anthropic'")["key_enc"])
        )
        listed = client.get("/settings/providers", headers=admin).json()
        assert {p["id"] for p in listed} >= {
            "openai",
            "anthropic",
            "openrouter",
            "compat",
            "elevenlabs",
            "replicate",
            "stability",
            "google",
            "local",
        }
        assert (
            client.get("/settings/providers/anthropic/models", headers=admin).json()[0]["name"]
            == "claude-sonnet-4-5"
        )
        ok = client.put(
            "/settings/roles",
            json={
                "text": "anthropic:claude-sonnet-4-5",
                "text_fallback": ["openai:gpt-4.1-mini"],
                "transcribe": "local:small",
            },
            headers=owner,
        )
        assert ok.status_code == 200
        bad = client.put("/settings/roles", json={"tts": "anthropic:claude-sonnet-4-5"}, headers=owner)
        assert bad.status_code == 400 and "can't be used for tts" in bad.json()["detail"]
        from studio_shared.gemini import available

        assert available() is True
    finally:
        db.execute("delete from ai_providers where id = 'anthropic'")
        db.execute("update members set role = 'user' where user_id = %s", [oid])


def test_voices_endpoint(client, make_member, models_setting):
    _, _, hdr = make_member("user")
    models_setting({"tts": "openai:gpt-4o-mini-tts"})
    r = client.get("/story/voices", headers=hdr).json()
    assert r["provider"] == "openai" and any(v["name"] == "nova" for v in r["voices"])
    assert base64  # keep import used
