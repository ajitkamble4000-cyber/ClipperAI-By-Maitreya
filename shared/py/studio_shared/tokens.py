"""Token wallets: a daily allowance refilled at UTC midnight, plus bonus tokens that never expire.

Spending uses the daily balance first, then bonus. Owner, admins and the Staff/Creator team are
unlimited (charges are recorded as 'waived' so usage stays visible). Every change goes to the ledger.
All balance changes run in a transaction with the wallet row locked (no double-spend under concurrency)."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from psycopg import Connection

from . import db
from .errors import UserError


class InsufficientTokens(UserError):
    def __init__(self, need: int, have: int, resets_at: datetime | None) -> None:
        self.need, self.have, self.resets_at = need, have, resets_at
        when = f" Your daily tokens refill at {resets_at:%H:%M} UTC." if resets_at else ""
        super().__init__(f"Not enough tokens: this needs {need}, you have {have}.{when}")


@dataclass
class Wallet:
    user_id: str
    daily_balance: int
    bonus_balance: int
    daily_allowance: int | None  # None = unlimited
    resets_at: datetime
    unlimited: bool
    lifetime_spent: int

    @property
    def total(self) -> int:
        return self.daily_balance + self.bonus_balance

    def to_json(self) -> dict[str, Any]:
        return {
            "daily_balance": self.daily_balance,
            "bonus_balance": self.bonus_balance,
            "total": self.total,
            "daily_allowance": self.daily_allowance,
            "resets_at": self.resets_at.isoformat(),
            "unlimited": self.unlimited,
            "lifetime_spent": self.lifetime_spent,
        }


def next_reset(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def _profile(c: Connection, user_id: str) -> dict[str, Any]:
    row = c.execute(
        """select m.role, m.team, m.plan_id, m.daily_tokens_override, p.daily_tokens
             from members m join plans p on p.id = m.plan_id where m.user_id = %s""",
        [user_id],
    ).fetchone()
    if not row:
        raise UserError("Account not found")
    return row


def _is_unlimited(p: dict[str, Any]) -> bool:
    return p["role"] in ("owner", "admin") or p["team"] is not None or p["daily_tokens"] is None


def _allowance(p: dict[str, Any]) -> int | None:
    if _is_unlimited(p):
        return None
    return p["daily_tokens_override"] if p["daily_tokens_override"] is not None else int(p["daily_tokens"])


def _ledger(
    c: Connection,
    user_id: str,
    delta: int,
    bucket: str,
    reason: str,
    w: dict[str, Any],
    *,
    action: str | None = None,
    job_id: str | None = None,
    actor_id: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    c.execute(
        """insert into token_ledger (user_id, delta, bucket, reason, action, job_id, actor_id, daily_after, bonus_after, meta)
           values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        [
            user_id,
            delta,
            bucket,
            reason,
            action,
            job_id,
            actor_id,
            w["daily_balance"],
            w["bonus_balance"],
            db.jsonb(meta or {}),
        ],
    )


def _locked_wallet(c: Connection, user_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Wallet row FOR UPDATE, created and refilled as needed."""
    p = _profile(c, user_id)
    c.execute(
        "insert into wallets (user_id, daily_reset_at) values (%s, now()) on conflict do nothing", [user_id]
    )
    w = c.execute("select * from wallets where user_id = %s for update", [user_id]).fetchone()
    allowance = _allowance(p)
    now = datetime.now(UTC)
    if w["daily_reset_at"] <= now:
        new_daily = allowance or 0
        delta = new_daily - w["daily_balance"]
        w = c.execute(
            "update wallets set daily_balance = %s, daily_reset_at = %s, updated_at = now() where user_id = %s returning *",
            [new_daily, next_reset(now), user_id],
        ).fetchone()
        if allowance is not None:
            _ledger(c, user_id, delta, "daily", "daily_refill", w, meta={"allowance": allowance})
    return p, w


def _wallet_obj(p: dict[str, Any], w: dict[str, Any]) -> Wallet:
    return Wallet(
        str(w["user_id"]),
        w["daily_balance"],
        w["bonus_balance"],
        _allowance(p),
        w["daily_reset_at"],
        _is_unlimited(p),
        int(w["lifetime_spent"]),
    )


def get_wallet(user_id: str) -> Wallet:
    with db.transaction() as c:
        p, w = _locked_wallet(c, user_id)
        return _wallet_obj(p, w)


def charge(
    user_id: str, tokens: int, action: str, *, job_id: str | None = None, meta: dict[str, Any] | None = None
) -> Wallet:
    tokens = max(0, int(tokens))
    with db.transaction() as c:
        p, w = _locked_wallet(c, user_id)
        if _is_unlimited(p):
            if tokens:
                _ledger(
                    c,
                    user_id,
                    0,
                    "none",
                    "waived",
                    w,
                    action=action,
                    job_id=job_id,
                    meta={**(meta or {}), "tokens": tokens},
                )
            return _wallet_obj(p, w)
        have = w["daily_balance"] + w["bonus_balance"]
        if tokens > have:
            raise InsufficientTokens(tokens, have, w["daily_reset_at"])
        from_daily = min(tokens, w["daily_balance"])
        from_bonus = tokens - from_daily
        w = c.execute(
            """update wallets set daily_balance = daily_balance - %s, bonus_balance = bonus_balance - %s,
                      lifetime_spent = lifetime_spent + %s, updated_at = now() where user_id = %s returning *""",
            [from_daily, from_bonus, tokens, user_id],
        ).fetchone()
        bucket = "daily" if not from_bonus else "bonus" if not from_daily else "mixed"
        _ledger(
            c,
            user_id,
            -tokens,
            bucket,
            "charge",
            w,
            action=action,
            job_id=job_id,
            meta={**(meta or {}), "from_daily": from_daily, "from_bonus": from_bonus},
        )
        if job_id:
            c.execute("update jobs set tokens_charged = tokens_charged + %s where id = %s", [tokens, job_id])
        return _wallet_obj(p, w)


def _job_payer(c: Connection, job_id: str) -> str | None:
    row = c.execute(
        "select user_id from token_ledger where job_id = %s and reason = 'charge' limit 1", [job_id]
    ).fetchone()
    return str(row["user_id"]) if row else None


def _returnable(c: Connection, job_id: str, w: dict[str, Any]) -> tuple[int, int]:
    """(daily, bonus) that would go back if the job were refunded now: charges since the last full refund,
    minus partial refunds ('adjust') already given since then. `w` is the payer's locked wallet."""
    rows = c.execute("select * from token_ledger where job_id = %s order by id", [job_id]).fetchall()
    last_refund = max((r["id"] for r in rows if r["reason"] == "refund"), default=0)
    charges = [r for r in rows if r["reason"] == "charge" and r["id"] > last_refund]
    back_daily = back_bonus = 0
    for r in charges:
        fd, fb = int(r["meta"].get("from_daily", 0)), int(r["meta"].get("from_bonus", 0))
        same_day = r["ts"] > w["daily_reset_at"] - timedelta(days=1)
        back_daily += fd if same_day else 0
        back_bonus += fb + (0 if same_day else fd)
    for r in rows:
        if r["reason"] == "adjust" and r["id"] > last_refund:
            back_daily -= int(r["meta"].get("back_daily", 0))
            back_bonus -= int(r["meta"].get("back_bonus", 0))
    return max(0, back_daily), max(0, back_bonus)


def _give_back(c: Connection, user_id: str, daily: int, bonus: int) -> dict[str, Any]:
    return c.execute(
        """update wallets set daily_balance = daily_balance + %s, bonus_balance = bonus_balance + %s,
                  lifetime_spent = greatest(0, lifetime_spent - %s), updated_at = now() where user_id = %s returning *""",
        [daily, bonus, daily + bonus, user_id],
    ).fetchone()


def _bucket(daily: int, bonus: int) -> str:
    return "mixed" if daily and bonus else ("daily" if daily else "bonus")


def refund_job(job_id: str, reason: str = "refund") -> int:
    """Give back everything charged for a job (idempotent). Tokens spent from today's allowance go back
    to the daily balance if it's still the same day; otherwise they come back as bonus tokens."""
    with db.transaction() as c:
        user_id = _job_payer(c, job_id)
        if not user_id:
            return 0
        _, w = _locked_wallet(c, user_id)
        back_daily, back_bonus = _returnable(c, job_id, w)
        total = back_daily + back_bonus
        if not total:
            return 0
        w = _give_back(c, user_id, back_daily, back_bonus)
        _ledger(
            c,
            user_id,
            total,
            _bucket(back_daily, back_bonus),
            "refund",
            w,
            job_id=job_id,
            meta={"why": reason},
        )
        c.execute("update jobs set tokens_charged = 0 where id = %s", [job_id])
        return total


def partial_refund(job_id: str, amount: int, why: str) -> int:
    """Give back part of a job's charge (e.g. auto mode turned out to be a single captioned video)."""
    amount = max(0, int(amount))
    if not amount:
        return 0
    with db.transaction() as c:
        user_id = _job_payer(c, job_id)
        if not user_id:
            return 0
        _, w = _locked_wallet(c, user_id)
        done = c.execute(
            """select 1 from token_ledger where job_id = %s and reason = 'adjust' and meta->>'why' = %s
                 and id > coalesce((select max(id) from token_ledger where job_id = %s and reason = 'refund'), 0)""",
            [job_id, why, job_id],
        ).fetchone()
        if done:  # idempotent per reason (a resumed job must not refund twice)
            return 0
        can_daily, can_bonus = _returnable(c, job_id, w)
        amount = min(amount, can_daily + can_bonus)
        if not amount:
            return 0
        give_daily = min(amount, can_daily)
        give_bonus = amount - give_daily
        w = _give_back(c, user_id, give_daily, give_bonus)
        _ledger(
            c,
            user_id,
            amount,
            _bucket(give_daily, give_bonus),
            "adjust",
            w,
            job_id=job_id,
            meta={"why": why, "back_daily": give_daily, "back_bonus": give_bonus},
        )
        c.execute(
            "update jobs set tokens_charged = greatest(0, tokens_charged - %s) where id = %s",
            [amount, job_id],
        )
        return amount


def on_plan_change(user_id: str, *, actor_id: str | None = None) -> Wallet:
    """After an upgrade the new daily allowance applies today: top up to it (never take tokens away)."""
    with db.transaction() as c:
        p, w = _locked_wallet(c, user_id)
        allowance = _allowance(p)
        if allowance is not None and allowance > w["daily_balance"]:
            delta = allowance - w["daily_balance"]
            w = c.execute(
                "update wallets set daily_balance = %s, updated_at = now() where user_id = %s returning *",
                [allowance, user_id],
            ).fetchone()
            _ledger(
                c, user_id, delta, "daily", "plan_change", w, actor_id=actor_id, meta={"allowance": allowance}
            )
        return _wallet_obj(p, w)


def grant(user_id: str, amount: int, *, actor_id: str | None, note: str = "") -> Wallet:
    """Admin grant (positive) or revoke (negative) of bonus tokens. Revokes never go below zero."""
    with db.transaction() as c:
        p, w = _locked_wallet(c, user_id)
        new_bonus = max(0, w["bonus_balance"] + int(amount))
        delta = new_bonus - w["bonus_balance"]
        w = c.execute(
            "update wallets set bonus_balance = %s, updated_at = now() where user_id = %s returning *",
            [new_bonus, user_id],
        ).fetchone()
        _ledger(
            c,
            user_id,
            delta,
            "bonus",
            "grant" if amount >= 0 else "revoke",
            w,
            actor_id=actor_id,
            meta={"note": note[:300]},
        )
        return _wallet_obj(p, w)


def ledger(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    return db.fetch_all(
        """select l.id, l.ts, l.delta, l.bucket, l.reason, l.action, l.job_id, l.daily_after, l.bonus_after, l.meta,
                  p.title as project_title
             from token_ledger l left join jobs j on j.id = l.job_id left join projects p on p.id = j.project_id
            where l.user_id = %s order by l.id desc limit %s""",
        [user_id, limit],
    )


# ---------------------------------------------------------------- prices and quotes
_PRICE_CACHE: tuple[float, dict[str, int]] = (0.0, {})


def prices() -> dict[str, int]:
    global _PRICE_CACHE
    if time.monotonic() - _PRICE_CACHE[0] > 15:
        _PRICE_CACHE = (
            time.monotonic(),
            {r["action"]: int(r["tokens"]) for r in db.fetch_all("select action, tokens from token_prices")},
        )
    return _PRICE_CACHE[1]


def clear_price_cache() -> None:
    global _PRICE_CACHE
    _PRICE_CACHE = (0.0, {})


def price(action: str) -> int:
    return prices().get(action, 0)


def quote(kind: str, p: dict[str, Any]) -> tuple[int, dict[str, int]]:
    """Tokens for a job before it runs, with a line-item breakdown."""
    items: dict[str, int] = {}
    if kind == "clip":
        if p.get("mode") == "captions":
            items["captions_job"] = price("captions_job")
        else:  # clips, or auto (charged as clips; refunded down to the captions price if it's a short video)
            items["clip_job"] = price("clip_job")
            per = "clip_basic_per_clip" if p.get("force_basic") else "clip_ai_per_clip"
            items[per] = price(per) * int(p.get("num_clips", 1))
            if p.get("visual_analysis"):
                items["visual_analysis"] = price("visual_analysis")
        if p.get("translate_to"):
            langs = p["translate_to"]
            items["translation"] = price("translation") * (len(langs) if isinstance(langs, list) else 1)
        if p.get("remove_silence") or p.get("remove_fillers"):
            items["jump_cuts"] = price("jump_cuts")
        if p.get("batch"):
            items["batch_link"] = price("batch_link")
    elif kind == "clip_rerender":
        items["rerender"] = price("rerender")
    elif kind == "story_script":
        items["story_script"] = price("story_script")
    elif kind == "story_scene_ai":
        items["scene_rewrite"] = price("scene_rewrite")
    elif kind == "story_characters":
        items["character_ref"] = price("character_ref") * int(p.get("count", 1))
    elif kind == "story_images":
        items["scene_image"] = price("scene_image") * int(p.get("count", 1))
    elif kind == "story_image_one":
        items["image_edit" if p.get("instruction") else "scene_image"] = price(
            "image_edit" if p.get("instruction") else "scene_image"
        )
    elif kind == "story_voice":
        if p.get("uploaded"):
            items["voice_upload"] = price("voice_upload")
        else:
            items["voice_per_30s"] = price("voice_per_30s") * max(
                1, math.ceil(float(p.get("seconds", 30)) / 30)
            )
    elif kind == "story_render":
        items["render"] = price("render")
    elif kind == "story_veo":
        items["veo_per_second"] = price("veo_per_second") * int(p.get("seconds", 0))
    elif kind == "clip_compile":
        items["compilation"] = price("compilation")
    elif kind in ("thumbnail", "title_variants"):
        items[kind] = price(kind) * int(p.get("count", 1))
    return sum(items.values()), items
