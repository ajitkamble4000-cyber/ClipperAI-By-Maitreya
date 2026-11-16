"""Hosting conveniences: sessions are confirmed by Supabase when the legacy JWT secret isn't configured, and any long
random APP_ENCRYPTION_KEY works (e.g. one Render generates), not only a Fernet key."""

from __future__ import annotations

import time

import httpx
import jwt
import pytest
from pydantic import SecretStr
from studio_shared import crypto
from studio_shared.config import get_settings

pytestmark = pytest.mark.integration


def test_legacy_signed_session_checked_by_supabase(client, make_member, monkeypatch):
    """A project signing with the legacy shared secret (HS256) and no SUPABASE_JWT_SECRET on the server: the API
    asks Supabase Auth to confirm the session (simulated here; local Supabase signs with ES256)."""
    from app import auth

    uid, email, _ = make_member()
    good = jwt.encode(
        {"sub": uid, "aud": "authenticated", "exp": int(time.time()) + 600},
        "only-supabase-knows",
        algorithm="HS256",
    )
    forged = jwt.encode(
        {"sub": uid, "aud": "authenticated", "exp": int(time.time()) + 600}, "attacker", algorithm="HS256"
    )
    calls: list[str] = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        ok = headers["Authorization"] == f"Bearer {good}"
        return httpx.Response(
            200 if ok else 401, json={"id": uid, "email": email} if ok else {"msg": "bad jwt"}
        )

    monkeypatch.setattr(get_settings(), "supabase_jwt_secret", None)
    monkeypatch.setattr(auth.httpx, "get", fake_get)
    auth._CHECKED.clear()
    r = client.get("/me", headers={"Authorization": f"Bearer {good}"})
    assert r.status_code == 200 and r.json()["email"] == email
    assert calls and calls[0].endswith("/auth/v1/user")
    assert client.get("/me", headers={"Authorization": f"Bearer {good}"}).status_code == 200
    assert len(calls) == 1  # cached for a minute
    assert client.get("/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    assert client.get("/me", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401


def test_any_long_secret_works_as_encryption_key(monkeypatch):
    original = get_settings().app_encryption_key
    token = crypto.encrypt("razorpay-secret")  # with the normal Fernet key
    assert crypto.decrypt(token) == "razorpay-secret"

    monkeypatch.setattr(
        get_settings(), "app_encryption_key", SecretStr("x9+Render/Generated==Value-1234567890abcdef")
    )
    t2 = crypto.encrypt("hello")
    assert crypto.decrypt(t2) == "hello"
    with pytest.raises(crypto.CryptoError):  # a different key can't read the old secret
        crypto.decrypt(token)

    monkeypatch.setattr(get_settings(), "app_encryption_key", SecretStr("short"))
    with pytest.raises(crypto.CryptoError, match="too short"):
        crypto.encrypt("x")
    monkeypatch.setattr(get_settings(), "app_encryption_key", original)
