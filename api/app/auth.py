"""Supabase JWT verification, user profiles, roles (owner / admin / user) and the Staff/Creator team."""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Annotated, Any

import httpx
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
    plan_id: str = "free"
    team: str | None = None
    status: str = "active"
    extra: dict[str, Any] = field(default_factory=dict)
    via_api_key: bool = False

    @property
    def is_owner(self) -> bool:
        return self.role == "owner"

    @property
    def is_admin(self) -> bool:
        """Owner or admin."""
        return self.role in ("owner", "admin")

    @property
    def unlimited(self) -> bool:
        """Owner, admins and the Staff/Creator team never pay tokens."""
        return self.is_admin or self.team is not None or self.plan_id == "team"


def owner_email() -> str | None:
    e = (get_settings().owner_email or os.environ.get("OWNER_EMAIL") or "").strip().lower()
    return e or None


@lru_cache
def _jwks() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{get_settings().supabase_url}/auth/v1/.well-known/jwks.json", cache_keys=True)


_CHECKED: dict[str, tuple[float, dict[str, Any]]] = {}  # token hash → (valid until, claims)


def _ask_supabase(token: str) -> dict[str, Any]:
    """Projects that still sign with the legacy shared secret: when SUPABASE_JWT_SECRET isn't configured, let
    Supabase Auth confirm the session instead (cached for a minute, so it isn't a call per request)."""
    h = hashlib.sha256(token.encode()).hexdigest()
    hit = _CHECKED.get(h)
    if hit and hit[0] > time.time():
        return hit[1]
    s = get_settings()
    try:
        r = httpx.get(
            f"{s.supabase_url}/auth/v1/user",
            headers={
                "apikey": s.supabase_service_role_key.get_secret_value(),
                "Authorization": f"Bearer {token}",
            },
            timeout=10,
        )
    except httpx.HTTPError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Couldn't reach the sign-in service") from e
    if r.status_code != 200:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")
    u = r.json()
    exp = jwt.decode(token, options={"verify_signature": False}).get("exp", time.time() + 60)
    claims = {"sub": u["id"], "email": u.get("email"), "exp": exp, "role": u.get("role", "authenticated")}
    if len(_CHECKED) > 5000:
        _CHECKED.clear()
    _CHECKED[h] = (min(time.time() + 60, float(exp)), claims)
    return claims


def verify_token(token: str) -> dict[str, Any]:
    s = get_settings()
    try:
        alg = jwt.get_unverified_header(token).get("alg", "")
        if alg == "HS256":
            if not s.supabase_jwt_secret or not s.supabase_jwt_secret.get_secret_value():
                return _ask_supabase(token)
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


PROFILE_SQL = """
    select m.user_id, m.email, m.role, m.display_name, m.plan_id, m.team, m.status, m.suspended_reason,
           m.last_seen_at, m.plan_expires_at, u.email_confirmed_at, lower(u.email) as auth_email
      from public.members m join auth.users u on u.id = m.user_id
     where m.user_id = %s
"""


def sync_owner(row: dict[str, Any]) -> dict[str, Any]:
    """The single owner is the account whose VERIFIED email equals OWNER_EMAIL. Nobody else can be owner."""
    oe = owner_email()
    is_owner_account = bool(oe and row["auth_email"] == oe and row["email_confirmed_at"] is not None)
    if is_owner_account and row["role"] != "owner":
        with db.transaction() as c:
            c.execute(
                "update members set role = 'admin' where role = 'owner' and user_id <> %s", [row["user_id"]]
            )
            c.execute(
                "update members set role = 'owner', status = 'active' where user_id = %s", [row["user_id"]]
            )
        row = {**row, "role": "owner", "status": "active"}
    elif not is_owner_account and row["role"] == "owner":
        db.execute("update members set role = 'admin' where user_id = %s", [row["user_id"]])
        row = {**row, "role": "admin"}
    return row


def load_member(user_id: str) -> Member | None:
    row = db.fetch_one(PROFILE_SQL, [user_id])
    if not row:
        # Profiles are created by a trigger on sign-up; create one if an older account lacks it.
        u = db.fetch_one("select id, lower(email) as email from auth.users where id = %s", [user_id])
        if not u:
            return None
        db.execute(
            "insert into members (user_id, email) values (%s, %s) on conflict do nothing",
            [u["id"], u["email"]],
        )
        row = db.fetch_one(PROFILE_SQL, [user_id])
        if not row:
            return None
    row = sync_owner(row)
    if row.get("plan_expires_at") is not None:
        from studio_shared.growth import expire_trial

        if expire_trial(user_id):
            row = db.fetch_one(PROFILE_SQL, [user_id]) or row
    if row["last_seen_at"] is None or (
        db.fetch_one("select now() - %s::timestamptz > interval '5 minutes' as stale", [row["last_seen_at"]])
        or {}
    ).get("stale"):
        db.execute("update members set last_seen_at = now() where user_id = %s", [user_id])
    return Member(
        str(row["user_id"]),
        row["email"],
        row["role"],
        row["display_name"],
        row["plan_id"],
        row["team"],
        row["status"],
        {"suspended_reason": row["suspended_reason"]},
    )


def _api_key_user(key: str) -> str:
    from studio_shared.apikeys import hash_key

    row = db.fetch_one(
        "select id, user_id, last_used_at from api_keys where key_hash = %s and revoked_at is null",
        [hash_key(key)],
    )
    if not row:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
    db.execute(
        "update api_keys set last_used_at = now() where id = %s and (last_used_at is null or last_used_at < now() - interval '1 minute')",
        [row["id"]],
    )
    return str(row["user_id"])


def current_member(request: Request) -> Member:
    api_key = request.headers.get("x-api-key")
    if api_key and not request.headers.get("authorization"):
        m = load_member(_api_key_user(api_key))
        if m:
            from .plans import has_feature

            m.via_api_key = True
            if not has_feature(m, "api_access"):
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN, "The API is part of the Business plan. See Pricing to upgrade."
                )
    else:
        claims = verify_token(_bearer(request))
        m = load_member(claims["sub"])
    if not m:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account not found")
    if m.status != "active":
        reason = m.extra.get("suspended_reason")
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Your account is suspended" + (f": {reason}" if reason else ".")
        )
    return m


def require_session(member: Annotated[Member, Depends(current_member)]) -> Member:
    """Things an API key must never do (manage keys, webhooks, the account): sign in instead."""
    if member.via_api_key:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sign in to do this (API keys can't)")
    return member


def require_admin(member: Annotated[Member, Depends(current_member)]) -> Member:
    if member.via_api_key:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin actions need you to sign in (API keys can't)")
    if not member.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only")
    return member


def require_owner(member: Annotated[Member, Depends(current_member)]) -> Member:
    if member.via_api_key:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Owner actions need you to sign in (API keys can't)")
    if not member.is_owner:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can do this")
    return member


CurrentMember = Annotated[Member, Depends(current_member)]
SessionMember = Annotated[Member, Depends(require_session)]
AdminMember = Annotated[Member, Depends(require_admin)]
OwnerMember = Annotated[Member, Depends(require_owner)]


def audit(
    actor: Member | None,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    **details: Any,
) -> None:
    db.execute(
        "insert into audit_log (actor_id, actor_email, action, target_type, target_id, details) values (%s,%s,%s,%s,%s,%s)",
        [
            actor.user_id if actor else None,
            actor.email if actor else None,
            action,
            target_type,
            target_id,
            details,
        ],
    )
