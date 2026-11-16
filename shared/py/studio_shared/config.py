"""Environment configuration. All secrets come from env vars only."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(REPO_ROOT / ".env", ".env"), extra="ignore")

    # Database (direct Postgres connection, service role; bypasses RLS)
    database_url: SecretStr = SecretStr("postgresql://postgres:postgres@127.0.0.1:54322/postgres")

    # Supabase (auth verification + admin API for invites)
    supabase_url: str = "http://127.0.0.1:54321"
    supabase_service_role_key: SecretStr = SecretStr("")
    supabase_jwt_secret: SecretStr | None = None  # HS256 projects; otherwise JWKS is used

    # Redis
    redis_url: str = "redis://127.0.0.1:6379/0"

    # S3-compatible storage (Cloudflare R2 in production)
    s3_endpoint: str = "http://127.0.0.1:9090"
    s3_public_endpoint: str | None = None  # endpoint browsers use, if different
    s3_region: str = "auto"
    s3_access_key_id: SecretStr = SecretStr("dev")
    s3_secret_access_key: SecretStr = SecretStr("dev")
    s3_bucket: str = "shorts-studio"

    # App
    app_encryption_key: SecretStr = SecretStr("")  # Fernet key (base64, 32 bytes)
    owner_email: str | None = None  # the single owner/founder account (must be a verified email)
    # how browsers/calendar apps/Razorpay reach the API (feed links, webhook URL); on Render it defaults to the
    # service's own public URL
    public_api_url: str = Field(
        default_factory=lambda: os.environ.get("RENDER_EXTERNAL_URL", "http://127.0.0.1:8000")
    )
    webhook_allow_private: bool = False  # dev/tests only: allow http and private addresses for webhooks
    web_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    gemini_api_key: SecretStr | None = None  # optional env override for the admin-set key
    # Razorpay (optional: the owner can also set these in Admin → Payments; env wins)
    razorpay_key_id: str | None = None
    razorpay_key_secret: SecretStr | None = None
    razorpay_webhook_secret: SecretStr | None = None
    razorpay_api: str = "https://api.razorpay.com/v1"
    studio_fake_razorpay: bool = False  # tests only: orders are created locally, no network
    max_upload_bytes: int = 4 * 1024**3
    jobs_per_user_per_minute: int = 10

    # Worker
    tmp_dir: Path = Path("/tmp/shorts-studio")
    fonts_dir: Path = REPO_ROOT / "shared" / "fonts"
    models_dir: Path = REPO_ROOT / "models"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    worker_media_concurrency: int = 2
    worker_ai_concurrency: int = 8
    image_concurrency: int = Field(default=4, ge=1, le=16)

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.web_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
