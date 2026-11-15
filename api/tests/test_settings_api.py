"""Settings: masked key, test key, models from the API, budget, cookies, proxy, pricing; usage dashboard."""

from __future__ import annotations

import httpx
import pytest
from studio_shared import db

pytestmark = pytest.mark.integration


@pytest.fixture
def fake_models(monkeypatch):
    from studio_shared.gemini import client as gc

    def list_models(self):
        return [
            {"name": "gemini-2.5-flash", "display_name": "Gemini 2.5 Flash", "actions": ["generateContent"]},
            {"name": "gemini-2.5-flash-image", "display_name": "Image", "actions": ["generateContent"]},
            {"name": "gemini-2.5-flash-preview-tts", "display_name": "TTS", "actions": ["generateContent"]},
            {
                "name": "veo-3.1-fast-generate-preview",
                "display_name": "Veo",
                "actions": ["predictLongRunning"],
            },
            {"name": "text-embedding-004", "display_name": "Emb", "actions": ["embedContent"]},
        ]

    monkeypatch.setattr(gc.Gemini, "list_models", list_models)


@pytest.fixture
def restore_settings():
    before = db.fetch_one("select * from settings where id = 1")
    yield
    db.execute(
        "update settings set gemini_key_enc = %s, gemini_key_last4 = %s, models = %s, monthly_budget_usd = %s, "
        "proxy_enc = %s, cookies_r2_key = %s where id = 1",
        [
            before["gemini_key_enc"],
            before["gemini_key_last4"],
            before["models"],
            before["monthly_budget_usd"],
            before["proxy_enc"],
            before["cookies_r2_key"],
        ],
    )


def test_key_is_encrypted_masked_and_never_returned(client, make_member, fake_models, restore_settings):
    _, _, admin = make_member("admin")
    _, _, member = make_member("member")
    key = "AIzaSyTEST-not-a-real-key-1234567890abcd"
    assert client.put("/settings/gemini-key", json={"key": key}, headers=member).status_code == 403
    r = client.put("/settings/gemini-key", json={"key": key}, headers=admin)
    assert r.status_code == 200, r.text
    assert key not in r.text and r.json()["gemini_key_masked"].endswith("abcd")
    row = db.fetch_one("select gemini_key_enc from settings where id = 1")
    assert key not in row["gemini_key_enc"]
    assert key not in client.get("/settings", headers=admin).text
    assert client.post("/settings/test-key", headers=admin).json() == {
        "ok": True,
        "models": 5,
        "roles": {"text": 1, "image": 1, "tts": 1, "video": 1},
    }
    roles = client.get("/settings/models", headers=admin).json()
    assert [m["name"] for m in roles["video"]] == ["veo-3.1-fast-generate-preview"]
    assert all("embedding" not in m["name"] for m in roles["text"])


def test_bad_key_rejected(client, make_member, monkeypatch, restore_settings):
    from studio_shared.gemini import client as gc

    def boom(self):
        raise gc.GeminiError("The Gemini API key was rejected.")

    monkeypatch.setattr(gc.Gemini, "list_models", boom)
    _, _, admin = make_member("admin")
    r = client.put(
        "/settings/gemini-key", json={"key": "AIzaSyBAD-key-xxxxxxxxxxxxxxxxxxxxxxx"}, headers=admin
    )
    assert r.status_code == 400 and "rejected" in r.json()["detail"]


def test_budget_models_proxy_cookies(client, make_member, restore_settings):
    _, _, admin = make_member("admin")
    r = client.put(
        "/settings", json={"monthly_budget_usd": 25, "models": {"text": "gemini-2.5-flash"}}, headers=admin
    )
    assert r.json()["monthly_budget_usd"] == 25 and r.json()["models"] == {"text": "gemini-2.5-flash"}
    assert client.put("/settings/proxy", json={"url": "ftp://x"}, headers=admin).status_code == 400
    assert client.put(
        "/settings/proxy", json={"url": "http://u:p@proxy.example.com:8080"}, headers=admin
    ).json() == {"proxy_set": True}
    assert "proxy.example.com" not in client.get("/settings", headers=admin).text
    bad = client.post(
        "/settings/cookies", files={"file": ("cookies.txt", b"hello", "text/plain")}, headers=admin
    )
    assert bad.status_code == 400
    good = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tabc\n"
    r = client.post(
        "/settings/cookies", files={"file": ("cookies.txt", good.encode(), "text/plain")}, headers=admin
    )
    assert r.json() == {"cookies_set": True, "cookies": 1}
    assert client.get("/settings", headers=admin).json()["cookies_set"] is True


def test_usage_summary_and_budget_levels(client, make_member, restore_settings):
    uid, _, admin = make_member("admin")
    db.execute("update settings set monthly_budget_usd = 10 where id = 1")
    db.execute(
        "insert into usage_events (user_id, model, kind, cost_usd) values (%s, 'gemini-x', 'image', 8.5)",
        [uid],
    )
    try:
        s = client.get("/usage/summary", headers=admin).json()
        assert s["budget"]["level"] in ("warn", "blocked")
        assert any(u["user_id"] == uid and u["cost"] >= 8.5 for u in s["per_user"])
        assert len(s["per_day"]) == 30 and s["per_day"][-1]["cost"] >= 8.5
        assert client.get("/budget", headers=admin).json()["level"] in ("warn", "blocked")
    finally:
        db.execute("delete from usage_events where model = 'gemini-x'")


def test_pricing_editable_by_admin_only(client, make_member):
    _, _, admin = make_member("admin")
    _, _, member = make_member("member")
    body = {"model": "test-model-x", "per_image": 0.5}
    assert client.put("/settings/pricing", json=body, headers=member).status_code == 403
    assert client.put("/settings/pricing", json=body, headers=admin).json()["per_image"] == 0.5
    assert any(p["model"] == "test-model-x" for p in client.get("/settings/pricing", headers=member).json())
    client.delete("/settings/pricing/test-model-x", headers=admin)
    assert httpx
