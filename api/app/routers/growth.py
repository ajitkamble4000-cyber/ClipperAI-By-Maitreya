"""Growth: public site status, referrals, promo codes (redeem + owner management) and owner site controls."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator, model_validator
from studio_shared import db, growth

from ..auth import AdminMember, CurrentMember, OwnerMember, audit

router = APIRouter(tags=["growth"])


@router.get("/public/site")
def public_site() -> dict:
    """What every page needs to know (no sign-in): sign-ups open, maintenance message."""
    s = growth.site()
    return {
        "signups_open": s["signups_open"],
        "jobs_paused": s["jobs_paused"],
        "maintenance_message": s["maintenance_message"],
        "referral_reward": s["referral_reward"],
    }


# ---------------------------------------------------------------- referrals
@router.get("/referrals")
def my_referrals(m: CurrentMember) -> dict:
    code = growth.referral_code(m.user_id)
    rows = db.fetch_all(
        """select r.status, r.reward, r.created_at, r.rewarded_at, coalesce(m.display_name, split_part(m.email, '@', 1)) as name
             from referrals r join members m on m.user_id = r.referred_id
            where r.referrer_id = %s order by r.created_at desc limit 50""",
        [m.user_id],
    )
    s = growth.site()
    return {
        "code": code,
        "path": f"/signup?ref={code}",
        "reward": s["referral_reward"],
        "monthly_cap": s["referral_monthly_cap"],
        "joined": len(rows),
        "rewarded": sum(1 for r in rows if r["status"] == "rewarded"),
        "tokens_earned": sum(int(r["reward"]) for r in rows if r["status"] == "rewarded"),
        "friends": [
            {**r, "name": (r["name"] or "")[:1].upper() + (r["name"] or "")[1:3] + "…"} for r in rows
        ],
    }


# ---------------------------------------------------------------- promo codes
class RedeemIn(BaseModel):
    code: str = Field(min_length=3, max_length=40)


@router.post("/promo/redeem")
def redeem(body: RedeemIn, m: CurrentMember) -> dict:
    from ..ratelimit import check_ip_rate

    check_ip_rate(m.user_id, "promo", limit=10)  # per user: stops code guessing
    return growth.redeem(m.user_id, body.code)


class PromoIn(BaseModel):
    code: str = Field(min_length=3, max_length=32)
    kind: Literal["tokens", "trial"]
    tokens: int = Field(default=0, ge=0, le=1_000_000)
    plan_id: Literal["pro", "business"] | None = None
    trial_days: int | None = Field(default=None, ge=1, le=365)
    max_redemptions: int | None = Field(default=None, ge=1, le=1_000_000)
    expires_at: datetime | None = None
    note: str = Field(default="", max_length=200)

    @field_validator("code")
    @classmethod
    def clean_code(cls, v: str) -> str:
        v = growth.normalize_code(v)
        if not all(ch.isalnum() or ch in "_-" for ch in v):
            raise ValueError("Use letters, numbers, - and _ only")
        return v

    @model_validator(mode="after")
    def complete(self) -> PromoIn:
        if self.kind == "tokens" and self.tokens <= 0:
            raise ValueError("Set how many tokens the code gives")
        if self.kind == "trial" and (not self.plan_id or not self.trial_days):
            raise ValueError("Pick the plan and number of days for the trial")
        return self


@router.get("/admin/promos")
def list_promos(_: AdminMember) -> list[dict]:
    return db.fetch_all("select * from promo_codes order by created_at desc limit 200")


@router.post("/admin/promos", status_code=201)
def create_promo(body: PromoIn, owner: OwnerMember) -> dict:
    if db.fetch_one("select 1 from promo_codes where code = %s", [body.code]):
        raise HTTPException(status.HTTP_409_CONFLICT, "That code already exists")
    row = db.fetch_one(
        """insert into promo_codes (code, kind, tokens, plan_id, trial_days, max_redemptions, expires_at, note, created_by)
           values (%s,%s,%s,%s,%s,%s,%s,%s,%s) returning *""",
        [
            body.code,
            body.kind,
            body.tokens if body.kind == "tokens" else 0,
            body.plan_id if body.kind == "trial" else None,
            body.trial_days if body.kind == "trial" else None,
            body.max_redemptions,
            body.expires_at,
            body.note,
            owner.user_id,
        ],
    )
    audit(owner, "promo.create", "promo", body.code, kind=body.kind, tokens=body.tokens, plan_id=body.plan_id)
    return row


class PromoPatch(BaseModel):
    active: bool


@router.patch("/admin/promos/{code}")
def update_promo(code: str, body: PromoPatch, owner: OwnerMember) -> dict:
    row = db.fetch_one(
        "update promo_codes set active = %s where code = %s returning *", [body.active, code.upper()]
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Code not found")
    audit(owner, "promo.update", "promo", code.upper(), active=body.active)
    return row


# ---------------------------------------------------------------- site controls (owner)
class SiteIn(BaseModel):
    signups_open: bool | None = None
    jobs_paused: bool | None = None
    maintenance_message: str | None = Field(default=None, max_length=300)
    referral_reward: int | None = Field(default=None, ge=0, le=100_000)
    referral_monthly_cap: int | None = Field(default=None, ge=0, le=1000)


@router.get("/admin/site")
def get_site(_: AdminMember) -> dict:
    s = growth.site()
    s["referrals"] = db.fetch_one(
        "select count(*) as total, count(*) filter (where status = 'rewarded') as rewarded from referrals"
    )
    s["trials_running"] = db.fetch_one("select count(*) as n from members where plan_expires_at > now()")["n"]
    return s


@router.put("/admin/site")
def put_site(body: SiteIn, owner: OwnerMember) -> dict:
    vals = body.model_dump(exclude_none=True)
    if vals:
        cols = ", ".join(f"{k} = %({k})s" for k in vals)
        db.execute(f"update settings set {cols}, updated_at = now() where id = 1", vals)
        audit(owner, "site.update", "settings", "1", **vals)
    return get_site(owner)
