"""Growth features: site controls, referral rewards, promo codes and plan trials."""

from __future__ import annotations

import secrets
import string
from datetime import UTC, datetime, timedelta
from typing import Any

from . import db, tokens
from .errors import UserError
from .notify import notify

PLAN_RANK = {"free": 0, "pro": 1, "business": 2, "team": 3}


# ---------------------------------------------------------------- site controls
def site() -> dict[str, Any]:
    row = db.fetch_one(
        "select signups_open, jobs_paused, maintenance_message, referral_reward, referral_monthly_cap "
        "from settings where id = 1"
    )
    return (
        dict(row)
        if row
        else {
            "signups_open": True,
            "jobs_paused": False,
            "maintenance_message": "",
            "referral_reward": 500,
            "referral_monthly_cap": 20,
        }
    )


# ---------------------------------------------------------------- referrals
_ALPHABET = string.ascii_lowercase + string.digits


def referral_code(user_id: str) -> str:
    """The user's referral code, created on first use."""
    row = db.fetch_one("select referral_code from members where user_id = %s", [user_id])
    if row and row["referral_code"]:
        return row["referral_code"]
    for _ in range(10):
        code = "".join(secrets.choice(_ALPHABET) for _ in range(8))
        try:
            got = db.fetch_one(
                "update members set referral_code = %s where user_id = %s and referral_code is null returning referral_code",
                [code, user_id],
            )
        except Exception:  # noqa: BLE001 - collision on the unique index: try another
            continue
        if got:
            return got["referral_code"]
        row = db.fetch_one("select referral_code from members where user_id = %s", [user_id])
        if row and row["referral_code"]:
            return row["referral_code"]
    raise UserError("Couldn't create a referral code, try again")


def maybe_reward_referral(user_id: str) -> int:
    """Called when a user's job finishes: the first finished video unlocks the referral reward for both sides.
    Returns the tokens given to the referred user (0 if nothing to do)."""
    s = site()
    reward = int(s["referral_reward"])
    with db.transaction() as c:
        ref = c.execute(
            "select * from referrals where referred_id = %s and status = 'pending' for update", [user_id]
        ).fetchone()
        if not ref:
            return 0
        referrer = str(ref["referrer_id"])
        month_count = c.execute(
            "select count(*) as n from referrals where referrer_id = %s and status = 'rewarded' "
            "and rewarded_at >= date_trunc('month', now())",
            [referrer],
        ).fetchone()["n"]
        capped = month_count >= int(s["referral_monthly_cap"])
        c.execute(
            "update referrals set status = %s, reward = %s, rewarded_at = now() where referred_id = %s",
            ["capped" if capped else "rewarded", reward, user_id],
        )
    if reward <= 0:
        return 0
    tokens.grant(user_id, reward, actor_id=None, note="Welcome bonus from a friend's invite")
    notify(
        user_id,
        f"You got {reward:,} bonus tokens",
        "Thanks for joining through a friend's link.",
        kind="tokens",
    )
    if not capped:
        tokens.grant(referrer, reward, actor_id=None, note="Referral bonus")
        notify(
            referrer,
            f"Your friend made their first video: +{reward:,} tokens",
            "Thanks for spreading the word!",
            kind="tokens",
            link="/account/tokens",
        )
    return reward


# ---------------------------------------------------------------- trials
def expire_trial(user_id: str) -> bool:
    """End an expired trial or paid period: back to the plan they had before. Returns True if one ended."""
    row = db.fetch_one(
        """with old as (select plan_source, plan_id as ended from members where user_id = %(u)s)
           update members set plan_id = coalesce(plan_before_trial, 'free'), plan_expires_at = null,
                  plan_before_trial = null, plan_source = null, renewal_reminded_at = null
            where user_id = %(u)s and plan_expires_at is not null and plan_expires_at <= now()
        returning plan_id, (select plan_source from old) as source, (select ended from old) as ended""",
        {"u": user_id},
    )
    if not row:
        return False
    if row["source"] == "paid":
        title = f"Your {row['ended'].title()} plan has ended"
        body = f"You're back on the {row['plan_id'].title()} plan. Renew any time on Pricing."
    else:
        title = "Your trial has ended"
        body = f"You're back on the {row['plan_id'].title()} plan. Upgrade any time on Pricing."
    notify(user_id, title, body, link="/pricing")
    return True


def expire_trials() -> int:
    ids = db.fetch_all(
        "select user_id from members where plan_expires_at is not null and plan_expires_at <= now()"
    )
    return sum(1 for r in ids if expire_trial(str(r["user_id"])))


# ---------------------------------------------------------------- promo codes
def normalize_code(code: str) -> str:
    return code.strip().upper().replace(" ", "")


def redeem(user_id: str, raw_code: str) -> dict[str, Any]:
    code = normalize_code(raw_code)
    with db.transaction() as c:
        p = c.execute("select * from promo_codes where code = %s for update", [code]).fetchone()
        if not p or not p["active"]:
            raise UserError("That code isn't valid")
        if p["expires_at"] and p["expires_at"] <= datetime.now(UTC):
            raise UserError("That code has expired")
        if p["max_redemptions"] is not None and p["redemptions"] >= p["max_redemptions"]:
            raise UserError("That code has been used up")
        if c.execute(
            "select 1 from promo_redemptions where code = %s and user_id = %s", [code, user_id]
        ).fetchone():
            raise UserError("You've already used this code")
        m = c.execute(
            "select role, team, plan_id, plan_expires_at, plan_source from members where user_id = %s",
            [user_id],
        ).fetchone()
        if p["kind"] == "trial":
            if m["role"] in ("owner", "admin") or m["team"] is not None:
                raise UserError("Your account already has everything unlocked")
            if PLAN_RANK.get(m["plan_id"], 0) >= PLAN_RANK.get(p["plan_id"], 0):
                raise UserError("You're already on this plan or a bigger one")
            if m["plan_expires_at"] is not None:
                raise UserError(
                    "You already have a paid plan running"
                    if m["plan_source"] == "paid"
                    else "You already have a trial running"
                )
            until = datetime.now(UTC) + timedelta(days=int(p["trial_days"]))
            c.execute(
                "update members set plan_before_trial = plan_id, plan_id = %s, plan_expires_at = %s, "
                "plan_source = 'trial' where user_id = %s",
                [p["plan_id"], until, user_id],
            )
        c.execute("insert into promo_redemptions (code, user_id) values (%s, %s)", [code, user_id])
        c.execute("update promo_codes set redemptions = redemptions + 1 where code = %s", [code])
    if p["kind"] == "tokens":
        tokens.grant(user_id, int(p["tokens"]), actor_id=None, note=f"Promo code {code}")
        return {
            "kind": "tokens",
            "tokens": int(p["tokens"]),
            "message": f"{int(p['tokens']):,} bonus tokens added",
        }
    tokens.on_plan_change(user_id)
    plan = db.fetch_one("select name from plans where id = %s", [p["plan_id"]])
    days = int(p["trial_days"])
    return {
        "kind": "trial",
        "plan_id": p["plan_id"],
        "days": days,
        "message": f"{plan['name'] if plan else p['plan_id']} unlocked for {days} day{'s' if days > 1 else ''}",
    }
