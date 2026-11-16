"""Symmetric encryption for secrets stored in the database (Gemini key, proxy)."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings


class CryptoError(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = get_settings().app_encryption_key.get_secret_value()
    if not key:
        raise CryptoError("APP_ENCRYPTION_KEY is not set")
    try:
        return Fernet(key.encode())  # a proper Fernet key (as generated in DEPLOY.md)
    except ValueError:
        if len(key) < 32:
            raise CryptoError("APP_ENCRYPTION_KEY is too short (use at least 32 random characters)") from None
        # any other long random secret (e.g. one a hosting provider generated): derive a Fernet key from it
        return Fernet(base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest()))


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as e:
        raise CryptoError("Could not decrypt secret (wrong APP_ENCRYPTION_KEY?)") from e


def mask(secret: str | None, last4: str | None = None) -> str | None:
    tail = last4 or (secret[-4:] if secret else None)
    return f"••••••••{tail}" if tail else None
