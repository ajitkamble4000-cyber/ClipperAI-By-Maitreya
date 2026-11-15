"""Per-user fixed-window rate limit on job creation (Redis)."""

from __future__ import annotations

import time
from functools import lru_cache

import redis
from fastapi import HTTPException, status
from studio_shared.config import get_settings


@lru_cache
def _r() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url)


def check_job_rate(user_id: str, cost: int = 1) -> None:
    limit = get_settings().jobs_per_user_per_minute
    key = f"rl:jobs:{user_id}:{int(time.time() // 60)}"
    pipe = _r().pipeline()
    pipe.incrby(key, cost)
    pipe.expire(key, 90)
    count, _ = pipe.execute()
    if int(count) > limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many jobs started. Wait a minute and try again."
        )


def check_ip_rate(ip: str, bucket: str, limit: int = 5) -> None:
    """Fixed-window limit for unauthenticated endpoints (e.g. public share links)."""
    key = f"rl:{bucket}:{ip}:{int(time.time() // 60)}"
    pipe = _r().pipeline()
    pipe.incr(key)
    pipe.expire(key, 90)
    count, _ = pipe.execute()
    if int(count) > limit:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Wait a minute.")
