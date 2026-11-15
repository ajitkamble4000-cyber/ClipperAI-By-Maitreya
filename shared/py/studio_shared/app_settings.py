"""Workspace settings stored in the `settings` singleton row. Secrets are encrypted at rest."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import crypto, db, storage
from .config import get_settings

MODEL_ROLES = ("text", "image", "tts", "video")
COOKIES_KEY = "settings/cookies.txt.enc"


def get_row() -> dict[str, Any]:
    row = db.fetch_one("select * from settings where id = 1")
    assert row, "settings row missing (run migrations)"
    return row


def gemini_key() -> str | None:
    env = get_settings().gemini_api_key
    if env and env.get_secret_value():
        return env.get_secret_value()
    enc = get_row()["gemini_key_enc"]
    return crypto.decrypt(enc) if enc else None


def gemini_key_source() -> str:
    env = get_settings().gemini_api_key
    if env and env.get_secret_value():
        return "env"
    return "settings" if get_row()["gemini_key_enc"] else "none"


def set_gemini_key(key: str | None) -> None:
    if key:
        db.execute(
            "update settings set gemini_key_enc = %s, gemini_key_last4 = %s, updated_at = now() where id = 1",
            [crypto.encrypt(key), key[-4:]],
        )
    else:
        db.execute(
            "update settings set gemini_key_enc = null, gemini_key_last4 = null, updated_at = now() where id = 1"
        )


def models() -> dict[str, str]:
    return {k: v for k, v in (get_row()["models"] or {}).items() if k in MODEL_ROLES and v}


def model_for(role: str) -> str | None:
    return models().get(role)


def proxy() -> str | None:
    enc = get_row()["proxy_enc"]
    return crypto.decrypt(enc) if enc else None


def set_proxy(url: str | None) -> None:
    db.execute(
        "update settings set proxy_enc = %s, updated_at = now() where id = 1",
        [crypto.encrypt(url) if url else None],
    )


def save_cookies(text: str) -> None:
    storage.put_bytes(COOKIES_KEY, crypto.encrypt(text).encode(), "application/octet-stream")
    db.execute("update settings set cookies_r2_key = %s, updated_at = now() where id = 1", [COOKIES_KEY])


def clear_cookies() -> None:
    if get_row()["cookies_r2_key"]:
        storage.delete(COOKIES_KEY)
    db.execute("update settings set cookies_r2_key = null, updated_at = now() where id = 1")


def write_cookies_file(dest_dir: Path) -> Path | None:
    """Decrypt cookies.txt into the job temp dir (deleted with it). Returns None if not set."""
    if not get_row()["cookies_r2_key"]:
        return None
    text = crypto.decrypt(storage.get_bytes(COOKIES_KEY).decode())
    path = dest_dir / "cookies.txt"
    path.write_text(text)
    path.chmod(0o600)
    return path


def update(fields: dict[str, Any]) -> None:
    allowed = {"models", "monthly_budget_usd", "source_retention_days", "whisper_model"}
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return
    cols = ", ".join(f"{k} = %({k})s" for k in sets)
    db.execute(f"update settings set {cols}, updated_at = now() where id = 1", sets)


def public_view() -> dict[str, Any]:
    """Settings safe to return to an admin's browser: secrets masked."""
    row = get_row()
    src = gemini_key_source()
    env = get_settings().gemini_api_key
    last4 = (env.get_secret_value()[-4:] if env and env.get_secret_value() else None) or row[
        "gemini_key_last4"
    ]
    return {
        "gemini_key_masked": crypto.mask(None, last4) if src != "none" else None,
        "gemini_key_source": src,
        "models": row["models"] or {},
        "monthly_budget_usd": float(row["monthly_budget_usd"])
        if row["monthly_budget_usd"] is not None
        else None,
        "proxy_set": bool(row["proxy_enc"]),
        "cookies_set": bool(row["cookies_r2_key"]),
        "source_retention_days": row["source_retention_days"],
        "whisper_model": row["whisper_model"],
    }
