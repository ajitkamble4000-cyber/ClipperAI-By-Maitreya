"""Supabase Auth admin API (service role): create users and send invites."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import HTTPException
from studio_shared.config import get_settings


def _headers() -> dict[str, str]:
    key = get_settings().supabase_service_role_key.get_secret_value()
    if not key:
        raise HTTPException(500, "Server is missing SUPABASE_SERVICE_ROLE_KEY")
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _url(path: str) -> str:
    return f"{get_settings().supabase_url}/auth/v1{path}"


def _raise(r: httpx.Response) -> None:
    if r.status_code >= 400:
        try:
            msg = r.json().get("msg") or r.json().get("message") or r.text
        except ValueError:
            msg = r.text
        raise HTTPException(r.status_code if r.status_code < 500 else 502, f"Auth service: {msg}")


def create_user(email: str, password: str) -> dict[str, Any]:
    r = httpx.post(
        _url("/admin/users"),
        headers=_headers(),
        json={"email": email, "password": password, "email_confirm": True},
        timeout=20,
    )
    _raise(r)
    return dict(r.json())


def invite(email: str, redirect_to: str) -> dict[str, Any]:
    r = httpx.post(
        _url("/invite"),
        headers=_headers(),
        params={"redirect_to": redirect_to},
        json={"email": email},
        timeout=20,
    )
    _raise(r)
    return dict(r.json())


def delete_user(user_id: str) -> None:
    r = httpx.delete(_url(f"/admin/users/{user_id}"), headers=_headers(), timeout=20)
    if r.status_code != 404:
        _raise(r)
