from __future__ import annotations

import uuid

import httpx
import pytest
from authutil import _admin_headers, create_auth_user, sign_in
from studio_shared import db
from studio_shared.config import get_settings


@pytest.fixture
def unique_email() -> str:
    return f"t-{uuid.uuid4().hex[:10]}@example.com"


@pytest.fixture
def make_member():
    created: list[str] = []

    def _make(role: str = "member") -> tuple[str, str, dict[str, str]]:
        email = f"m-{uuid.uuid4().hex[:10]}@example.com"
        uid = create_auth_user(email)
        db.execute("insert into members (user_id, email, role) values (%s, %s, %s)", [uid, email, role])
        created.append(uid)
        return uid, email, {"Authorization": f"Bearer {sign_in(email)}"}

    yield _make
    for uid in created:
        httpx.delete(f"{get_settings().supabase_url}/auth/v1/admin/users/{uid}", headers=_admin_headers())


@pytest.fixture
def client():
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c
