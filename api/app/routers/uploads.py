"""Resumable multipart uploads straight from the browser to R2."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from studio_shared import db, storage
from studio_shared.config import get_settings

from ..auth import CurrentMember
from ..plans import limit
from ..validation import safe_filename, validate_upload

router = APIRouter(prefix="/uploads", tags=["uploads"])

Purpose = Literal["source", "voiceover", "music", "sfx", "image"]


class InitIn(BaseModel):
    filename: str = Field(min_length=1, max_length=300)
    size: int = Field(gt=0)
    content_type: str = Field(min_length=1, max_length=120)
    purpose: Purpose = "source"


def _get(upload_id: str, user_id: str) -> dict:
    row = db.fetch_one("select * from uploads where id = %s and user_id = %s", [upload_id, user_id])
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Upload not found")
    return row


def _public(row: dict) -> dict:
    size, part = int(row["size_bytes"]), int(row["part_size"])
    return {
        "id": row["id"],
        "filename": row["filename"],
        "size": size,
        "part_size": part,
        "part_count": (size + part - 1) // part,
        "status": row["status"],
        "purpose": row["purpose"],
        "content_type": row["content_type"],
        "created_at": row["created_at"],
    }


@router.post("", status_code=201)
def init_upload(body: InitIn, m: CurrentMember) -> dict:
    name = safe_filename(body.filename)
    max_bytes = get_settings().max_upload_bytes
    if body.purpose == "source":
        plan_mb = int(limit(m, "max_upload_mb", 1024))
        if body.size > plan_mb * 1024**2:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Your plan uploads files up to {plan_mb // 1024 if plan_mb >= 1024 else plan_mb} "
                f"{'GB' if plan_mb >= 1024 else 'MB'}. Paste a link instead, or upgrade for bigger files.",
            )
    validate_upload(body.purpose, name, body.content_type, body.size, max_bytes)
    part = storage.choose_part_size(body.size)
    row = db.fetch_one(
        """insert into uploads (user_id, purpose, r2_key, filename, content_type, size_bytes, part_size)
           values (%s, %s, '', %s, %s, %s, %s) returning *""",
        [m.user_id, body.purpose, name, body.content_type, body.size, part],
    )
    key = f"uploads/{m.user_id}/{row['id']}/{name}"
    mp = storage.create_multipart(key, body.content_type)
    row = db.fetch_one(
        "update uploads set r2_key = %s, multipart_id = %s where id = %s returning *", [key, mp, row["id"]]
    )
    return _public(row)


@router.get("")
def pending_uploads(m: CurrentMember) -> list[dict]:
    rows = db.fetch_all(
        "select * from uploads where user_id = %s and status = 'uploading' and created_at > now() - interval '2 days' "
        "order by created_at desc limit 20",
        [m.user_id],
    )
    return [_public(r) for r in rows]


@router.get("/{upload_id}")
def get_upload(upload_id: str, m: CurrentMember) -> dict:
    row = _get(upload_id, m.user_id)
    out = _public(row)
    out["parts"] = (
        storage.list_parts(row["r2_key"], row["multipart_id"]) if row["status"] == "uploading" else []
    )
    return out


class PartsIn(BaseModel):
    part_numbers: list[int] = Field(min_length=1, max_length=100)


@router.post("/{upload_id}/parts")
def sign_parts(upload_id: str, body: PartsIn, m: CurrentMember) -> dict:
    row = _get(upload_id, m.user_id)
    if row["status"] != "uploading":
        raise HTTPException(status.HTTP_409_CONFLICT, "Upload is not in progress")
    count = _public(row)["part_count"]
    if any(n < 1 or n > count for n in body.part_numbers):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Part number out of range")
    return {
        "urls": {
            str(n): storage.presign_part(row["r2_key"], row["multipart_id"], n) for n in body.part_numbers
        }
    }


class PartIn(BaseModel):
    part_number: int
    etag: str


class CompleteIn(BaseModel):
    parts: list[PartIn] = Field(min_length=1, max_length=10_000)


@router.post("/{upload_id}/complete")
def complete(upload_id: str, body: CompleteIn, m: CurrentMember) -> dict:
    row = _get(upload_id, m.user_id)
    if row["status"] == "complete":
        return _public(row)
    expected = _public(row)["part_count"]
    if sorted(p.part_number for p in body.parts) != list(range(1, expected + 1)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Expected {expected} parts")
    storage.complete_multipart(row["r2_key"], row["multipart_id"], [p.model_dump() for p in body.parts])
    actual = storage.head(row["r2_key"])["size"]
    if actual != int(row["size_bytes"]):
        storage.delete(row["r2_key"])
        db.execute("update uploads set status = 'aborted' where id = %s", [upload_id])
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Uploaded size does not match")
    row = db.fetch_one(
        "update uploads set status = 'complete', completed_at = now() where id = %s returning *", [upload_id]
    )
    return _public(row)


@router.delete("/{upload_id}")
def abort(upload_id: str, m: CurrentMember) -> dict:
    row = _get(upload_id, m.user_id)
    if row["status"] == "uploading":
        storage.abort_multipart(row["r2_key"], row["multipart_id"])
    db.execute("update uploads set status = 'aborted' where id = %s", [upload_id])
    return {"ok": True}


def take_completed_upload(upload_id: str, user_id: str, purpose: str) -> dict:
    """Used by other routers: a finished upload of the right purpose, owned by the user."""
    row = _get(upload_id, user_id)
    if row["status"] != "complete" or row["purpose"] != purpose:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Upload is not complete")
    return row
