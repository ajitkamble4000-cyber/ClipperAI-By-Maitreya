"""Health and first-run setup (creates the first admin)."""

from __future__ import annotations

import hmac

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from studio_shared import db
from studio_shared.config import get_settings

from .. import supabase_admin

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict:
    db.fetch_one("select 1 as ok")
    return {"ok": True}


def _has_members() -> bool:
    row = db.fetch_one("select exists(select 1 from members) as e")
    return bool(row and row["e"])


@router.get("/setup/status")
def setup_status() -> dict:
    return {"needs_setup": not _has_members()}


class SetupIn(BaseModel):
    token: str
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    display_name: str | None = Field(default=None, max_length=80)


@router.post("/setup")
def setup(body: SetupIn) -> dict:
    expected = get_settings().setup_token
    if not expected or not expected.get_secret_value():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Setup is disabled (SETUP_TOKEN is not set)")
    if not hmac.compare_digest(body.token, expected.get_secret_value()):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Wrong setup token")
    if _has_members():
        raise HTTPException(status.HTTP_409_CONFLICT, "Setup has already been completed")
    user = supabase_admin.create_user(body.email, body.password)
    db.execute(
        "insert into members (user_id, email, role, display_name) values (%s, %s, 'admin', %s) "
        "on conflict (user_id) do update set role = 'admin'",
        [user["id"], body.email.lower(), body.display_name],
    )
    return {"ok": True}
