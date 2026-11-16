"""Brand kit (Pro+): logo, @handle, colour, default caption preset and progress bar, applied to exports."""

from __future__ import annotations

import uuid
from pathlib import PurePosixPath
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from studio_shared import db, storage

from ..auth import CurrentMember, Member, audit
from ..plans import has_feature, require_feature
from .uploads import take_completed_upload

router = APIRouter(tags=["brand"])

DEFAULTS: dict[str, Any] = {
    "logo_key": None,
    "logo_position": "top-right",
    "logo_opacity": 0.9,
    "handle": "",
    "primary_color": "#FFE500",
    "caption_preset": None,
    "progress_bar": False,
}
LOGO_TYPES = {".png", ".jpg", ".jpeg", ".webp"}


def _view(m: Member) -> dict[str, Any]:
    row = db.fetch_one("select * from brand_kits where user_id = %s", [m.user_id])
    kit = {**DEFAULTS, **({k: row[k] for k in DEFAULTS} if row else {})}
    kit["logo_opacity"] = float(kit["logo_opacity"])
    kit["logo_url"] = storage.presign_get(kit["logo_key"]) if kit["logo_key"] else None
    kit["available"] = has_feature(m, "brand_kit")
    kit["saved"] = bool(row)
    return kit


@router.get("/brand")
def get_brand(m: CurrentMember) -> dict:
    return _view(m)


class BrandIn(BaseModel):
    logo_position: Literal["top-left", "top-right"] | None = None
    logo_opacity: float | None = Field(default=None, ge=0.2, le=1)
    handle: str | None = Field(default=None, max_length=40, pattern=r"^[@#\w.\- ]*$")
    primary_color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    caption_preset: (
        Literal["bold_pop", "karaoke", "minimal", "boxed", "horror", "neon", "typewriter", "bounce", "none"]
        | None
    ) = None
    progress_bar: bool | None = None


@router.put("/brand")
def put_brand(body: BrandIn, m: CurrentMember) -> dict:
    require_feature(m, "brand_kit")
    vals = body.model_dump(exclude_none=True)
    if "handle" in vals:
        vals["handle"] = vals["handle"].strip()
    db.execute("insert into brand_kits (user_id) values (%s) on conflict do nothing", [m.user_id])
    if vals:
        cols = ", ".join(f"{k} = %({k})s" for k in vals)
        db.execute(f"update brand_kits set {cols} where user_id = %(uid)s", {**vals, "uid": m.user_id})
    audit(m, "brand.update", "member", m.user_id, **vals)
    return _view(m)


class LogoIn(BaseModel):
    upload_id: str


@router.put("/brand/logo")
def put_logo(body: LogoIn, m: CurrentMember) -> dict:
    """Use a finished image upload as the logo. It's copied to a stable key that belongs to the brand kit."""
    require_feature(m, "brand_kit")
    up = take_completed_upload(body.upload_id, m.user_id, "image")
    ext = PurePosixPath(up["r2_key"]).suffix.lower()
    if ext not in LOGO_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The logo must be a PNG, JPG or WebP image")
    key = f"brand/{m.user_id}/logo-{uuid.uuid4().hex[:8]}{ext}"
    storage.put_bytes(key, storage.get_bytes(up["r2_key"]), up.get("content_type") or "image/png")
    db.execute("insert into brand_kits (user_id) values (%s) on conflict do nothing", [m.user_id])
    old = db.fetch_one("select logo_key from brand_kits where user_id = %s", [m.user_id])["logo_key"]
    db.execute("update brand_kits set logo_key = %s where user_id = %s", [key, m.user_id])
    if old:
        storage.delete(old)
    return _view(m)


@router.delete("/brand/logo")
def delete_logo(m: CurrentMember) -> dict:
    row = db.fetch_one("select logo_key from brand_kits where user_id = %s", [m.user_id])
    if row and row["logo_key"]:
        db.execute("update brand_kits set logo_key = null where user_id = %s", [m.user_id])
        storage.delete(row["logo_key"])
    return _view(m)
