"""Personal API keys: shown once, stored as a SHA-256 hash."""

from __future__ import annotations

import hashlib
import secrets

PREFIX = "ss_live_"


def generate() -> str:
    return PREFIX + secrets.token_urlsafe(30)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.strip().encode()).hexdigest()


def display_prefix(key: str) -> str:
    return key[: len(PREFIX) + 6]
