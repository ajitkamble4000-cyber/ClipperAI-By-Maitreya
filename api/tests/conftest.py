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

    def _make(
        role: str = "user", *, team: str | None = None, plan: str = "free"
    ) -> tuple[str, str, dict[str, str]]:
        role = "user" if role == "member" else role
        email = f"m-{uuid.uuid4().hex[:10]}@example.com"
        uid = create_auth_user(email)
        # The sign-up trigger already created the profile; set role/team/plan for the test.
        db.execute(
            "update members set role = %s, team = %s, plan_id = %s where user_id = %s",
            [role, team, plan, uid],
        )
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
