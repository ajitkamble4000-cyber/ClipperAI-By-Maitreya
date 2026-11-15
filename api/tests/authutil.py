from __future__ import annotations

import os

import httpx
from studio_shared.config import get_settings

ANON_KEY = os.environ.get(
    "SUPABASE_ANON_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9."
    "CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0",
)


def _admin_headers() -> dict[str, str]:
    k = get_settings().supabase_service_role_key.get_secret_value()
    return {"apikey": k, "Authorization": f"Bearer {k}"}


def create_auth_user(email: str, password: str = "test-password-123") -> str:
    r = httpx.post(
        f"{get_settings().supabase_url}/auth/v1/admin/users",
        headers=_admin_headers(),
        json={"email": email, "password": password, "email_confirm": True},
    )
    r.raise_for_status()
    return str(r.json()["id"])


def sign_in(email: str, password: str = "test-password-123") -> str:
    r = httpx.post(
        f"{get_settings().supabase_url}/auth/v1/token",
        params={"grant_type": "password"},
        headers={"apikey": ANON_KEY},
        json={"email": email, "password": password},
    )
    r.raise_for_status()
    return str(r.json()["access_token"])
