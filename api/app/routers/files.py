"""Short-lived signed download URLs."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from studio_shared import storage

from ..access import key_allowed
from ..auth import CurrentMember

router = APIRouter(prefix="/files", tags=["files"])

SHARED_PREFIXES = ("projects/", "assets/", "sources/", "jobs/", "library/")


@router.get("/sign")
def sign(
    m: CurrentMember,
    key: str = Query(min_length=3, max_length=1024),
    download: str | None = Query(default=None, max_length=200),
) -> dict:
    if ".." in key or key.startswith("/"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bad key")
    if not key_allowed(key, m):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed")
    return {"url": storage.presign_get(key, expires=900, filename=download), "expires_in": 900}
