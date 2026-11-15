"""Supabase JWT verification and role checks."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from studio_shared import db
from studio_shared.config import get_settings


@dataclass
class Member:
    user_id: str
    email: str
    role: str
    display_name: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


@lru_cache
def _jwks() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{get_settings().supabase_url}/auth/v1/.well-known/jwks.json", cache_keys=True)


def verify_token(token: str) -> dict[str, Any]:
    s = get_settings()
    try:
        alg = jwt.get_unverified_header(token).get("alg", "")
        if alg == "HS256":
            if not s.supabase_jwt_secret:
                raise jwt.InvalidTokenError("HS256 token but SUPABASE_JWT_SECRET is not configured")
            key: Any = s.supabase_jwt_secret.get_secret_value()
        else:
            key = _jwks().get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=[alg], audience="authenticated", leeway=30)
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session") from e
    if not claims.get("sub"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session")
    return claims


def _bearer(request: Request) -> str:
    h = request.headers.get("authorization", "")
    if not h.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    return h[7:].strip()


def current_member(request: Request) -> Member:
    claims = verify_token(_bearer(request))
    row = db.fetch_one(
        "select user_id, email, role, display_name from members where user_id = %s", [claims["sub"]]
    )
    if not row:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not a member of this workspace")
    return Member(str(row["user_id"]), row["email"], row["role"], row["display_name"])


def require_admin(member: Annotated[Member, Depends(current_member)]) -> Member:
    if not member.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only")
    return member


CurrentMember = Annotated[Member, Depends(current_member)]
AdminMember = Annotated[Member, Depends(require_admin)]
