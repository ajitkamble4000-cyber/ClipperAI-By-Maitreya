"""Admin settings (Gemini key, models, budget, downloads, pricing) and the usage dashboard."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from studio_shared import app_settings, db, usage
from studio_shared.gemini import Gemini, GeminiError
from studio_shared.gemini.models import classify

from ..auth import AdminMember, CurrentMember, OwnerMember, audit

router = APIRouter(tags=["settings"])
WHISPER = Literal["tiny", "base", "small", "medium", "large-v3", "large-v3-turbo", "distil-large-v3"]


@router.get("/settings")
def get_settings_view(_: AdminMember) -> dict:
    return {**app_settings.public_view(), "budget_state": usage.budget_state()}


class ModelsIn(BaseModel):
    text: str | None = Field(default=None, max_length=120)
    image: str | None = Field(default=None, max_length=120)
    tts: str | None = Field(default=None, max_length=120)
    video: str | None = Field(default=None, max_length=120)


class SettingsIn(BaseModel):
    models: ModelsIn | None = None
    monthly_budget_usd: float | None = Field(default=None, ge=0, le=100000)
    clear_budget: bool = False
    source_retention_days: int | None = Field(default=None, ge=1, le=365)
    whisper_model: WHISPER | None = None


@router.put("/settings")
def update_settings(body: SettingsIn, _: AdminMember) -> dict:
    fields: dict[str, Any] = {}
    if body.models is not None:
        fields["models"] = {k: v for k, v in body.models.model_dump().items() if v}
    if body.clear_budget:
        db.execute("update settings set monthly_budget_usd = null where id = 1")
    elif body.monthly_budget_usd is not None:
        fields["monthly_budget_usd"] = Decimal(str(body.monthly_budget_usd))
    if body.source_retention_days is not None:
        fields["source_retention_days"] = body.source_retention_days
    if body.whisper_model:
        fields["whisper_model"] = body.whisper_model
    app_settings.update(fields)
    return get_settings_view(_)


class KeyIn(BaseModel):
    key: str | None = Field(default=None, max_length=200)


def _test(key: str | None) -> dict:
    try:
        models = Gemini(api_key=key).list_models() if key else Gemini().list_models()
    except GeminiError as e:
        return {"ok": False, "error": str(e)}
    roles = classify(models)
    return {"ok": True, "models": len(models), "roles": {k: len(v) for k, v in roles.items()}}


@router.put("/settings/gemini-key")
def set_key(body: KeyIn, admin: OwnerMember) -> dict:
    if body.key:
        key = body.key.strip()
        if len(key) < 20 or " " in key:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "That doesn't look like an API key")
        result = _test(key)
        if not result["ok"]:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Key test failed: {result['error']}")
        app_settings.set_gemini_key(key)
    else:
        app_settings.set_gemini_key(None)
    audit(admin, "settings.gemini_key", "settings", "gemini", set=bool(body.key))
    return get_settings_view(admin)


@router.post("/settings/test-key")
def test_key(_: AdminMember) -> dict:
    if app_settings.gemini_key_source() == "none":
        return {"ok": False, "error": "No key is set."}
    return _test(None)


@router.get("/settings/models")
def list_models(_: AdminMember) -> dict:
    """Model choices for each role, from Gemini's models list (nothing hardcoded)."""
    try:
        return classify(Gemini().list_models())
    except GeminiError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e


class ProxyIn(BaseModel):
    url: str | None = Field(default=None, max_length=500)


@router.put("/settings/proxy")
def set_proxy(body: ProxyIn, _: OwnerMember) -> dict:
    if body.url:
        p = urlparse(body.url.strip())
        if p.scheme not in ("http", "https", "socks5", "socks5h") or not p.hostname:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Proxy must look like http://user:pass@host:port or socks5://host:port",
            )
        app_settings.set_proxy(body.url.strip())
    else:
        app_settings.set_proxy(None)
    return {"proxy_set": bool(body.url)}


@router.post("/settings/cookies")
async def upload_cookies(_: OwnerMember, file: Annotated[UploadFile, File()]) -> dict:
    data = await file.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "cookies.txt is too large (max 1 MB)")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "cookies.txt must be a text file") from e
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    if not lines or not all(len(ln.split("\t")) >= 7 for ln in lines[:20]):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This isn't a Netscape-format cookies.txt (export it with a 'Get cookies.txt' browser extension).",
        )
    app_settings.save_cookies(text)
    return {"cookies_set": True, "cookies": len(lines)}


@router.delete("/settings/cookies")
def delete_cookies(_: OwnerMember) -> dict:
    app_settings.clear_cookies()
    return {"cookies_set": False}


class PriceIn(BaseModel):
    model: str = Field(min_length=2, max_length=120)
    input_per_mtok: float = Field(default=0, ge=0)
    output_per_mtok: float = Field(default=0, ge=0)
    audio_out_per_mtok: float = Field(default=0, ge=0)
    per_image: float = Field(default=0, ge=0)
    per_video_second: float = Field(default=0, ge=0)


def _floats(row: dict[str, Any]) -> dict[str, Any]:
    return {k: float(v) if isinstance(v, Decimal) else v for k, v in row.items()}


@router.get("/settings/pricing")
def get_pricing(_: AdminMember) -> list[dict]:
    return [_floats(r) for r in db.fetch_all("select * from model_pricing order by model")]


@router.put("/settings/pricing")
def put_price(body: PriceIn, _: AdminMember) -> dict:
    return _floats(
        db.fetch_one(
            """insert into model_pricing (model, input_per_mtok, output_per_mtok, audio_out_per_mtok, per_image, per_video_second)
           values (%s,%s,%s,%s,%s,%s)
           on conflict (model) do update set input_per_mtok = excluded.input_per_mtok, output_per_mtok = excluded.output_per_mtok,
             audio_out_per_mtok = excluded.audio_out_per_mtok, per_image = excluded.per_image,
             per_video_second = excluded.per_video_second, updated_at = now()
           returning *""",
            [
                body.model.strip(),
                body.input_per_mtok,
                body.output_per_mtok,
                body.audio_out_per_mtok,
                body.per_image,
                body.per_video_second,
            ],
        )
    )


@router.delete("/settings/pricing/{model}")
def delete_price(model: str, _: AdminMember) -> dict:
    db.execute("delete from model_pricing where model = %s", [model])
    return {"ok": True}


# ---------------------------------------------------------------- usage
@router.get("/budget")
def budget(_: CurrentMember) -> dict:
    return usage.budget_state()


@router.get("/usage/summary")
def usage_summary(_: AdminMember, days: int = 30) -> dict:
    days = max(7, min(365, days))
    f = lambda rows: [{k: (float(v) if isinstance(v, Decimal) else v) for k, v in r.items()} for r in rows]  # noqa: E731
    per_day = f(
        db.fetch_all(
            """select d::date as day, coalesce(sum(u.cost_usd), 0) as cost, count(u.id) as calls
           from generate_series(current_date - (%s - 1), current_date, interval '1 day') d
           left join usage_events u on u.ts >= d and u.ts < d + interval '1 day'
           group by d order by d""",
            [days],
        )
    )
    per_user = f(
        db.fetch_all(
            """select u.user_id, coalesce(m.display_name, m.email, 'Unattributed') as name, sum(u.cost_usd) as cost, count(*) as calls
           from usage_events u left join members m on m.user_id = u.user_id
           where u.ts >= date_trunc('month', now()) group by u.user_id, m.display_name, m.email order by cost desc"""
        )
    )
    per_model = f(
        db.fetch_all(
            """select model, kind, sum(cost_usd) as cost, count(*) as calls, sum(input_tokens) as input_tokens,
                  sum(output_tokens) as output_tokens, sum(images) as images, sum(seconds) as seconds
           from usage_events where ts >= date_trunc('month', now()) group by model, kind order by cost desc"""
        )
    )
    per_month = f(
        db.fetch_all(
            """select to_char(date_trunc('month', ts), 'YYYY-MM') as month, sum(cost_usd) as cost, count(*) as calls
           from usage_events where ts >= date_trunc('month', now()) - interval '11 months'
           group by 1 order by 1"""
        )
    )
    recent = f(
        db.fetch_all(
            """select u.ts, u.model, u.kind, u.cost_usd, coalesce(m.display_name, m.email) as name, p.title as project
           from usage_events u left join members m on m.user_id = u.user_id left join projects p on p.id = u.project_id
           order by u.ts desc limit 25"""
        )
    )
    return {
        "budget": usage.budget_state(),
        "per_day": per_day,
        "per_user": per_user,
        "per_model": per_model,
        "per_month": per_month,
        "recent": recent,
    }


# ---------------------------------------------------------------- AI providers (many, not only Google)
def _adapter_with(pid: str, key: str | None, base_url: str | None):
    from studio_shared.ai.base import PROVIDERS, Credentials, credentials
    from studio_shared.ai.client import adapter as make_adapter

    if pid not in PROVIDERS or pid == "local":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown provider")
    if key is None and base_url is None:
        return make_adapter(pid)
    cur = credentials(pid)
    creds = Credentials(pid, key or cur.key, (base_url or cur.base_url or "").rstrip("/") or None)
    from studio_shared.ai.adapters.openai_like import OpenAILike
    from studio_shared.ai.adapters.others import Anthropic, ElevenLabs, Replicate, Stability

    cls = {
        "openai": OpenAILike,
        "openrouter": OpenAILike,
        "compat": OpenAILike,
        "anthropic": Anthropic,
        "elevenlabs": ElevenLabs,
        "replicate": Replicate,
        "stability": Stability,
    }.get(pid)
    if cls is None:  # google
        return Gemini(api_key=creds.key)
    return cls(creds)


def _test_provider(pid: str, key: str | None = None, base_url: str | None = None) -> dict:
    from studio_shared.ai.base import ProviderError

    try:
        models = _adapter_with(pid, key, base_url).list_models()
    except (ProviderError, GeminiError) as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:  # noqa: BLE001 - network errors, bad URLs
        return {"ok": False, "error": f"Could not reach the provider: {e}"[:300]}
    return {"ok": True, "models": len(models)}


@router.get("/settings/providers")
def providers(_: AdminMember) -> list[dict]:
    from studio_shared.ai.base import provider_status

    return provider_status()


class ProviderIn(BaseModel):
    key: str | None = Field(default=None, max_length=400)
    base_url: str | None = Field(default=None, max_length=300)
    enabled: bool | None = None
    clear_key: bool = False


@router.put("/settings/providers/{pid}")
def save_provider(pid: str, body: ProviderIn, owner: OwnerMember) -> dict:
    from studio_shared.ai.base import provider_status, save_credentials

    if body.base_url:
        p = urlparse(body.base_url)
        if p.scheme not in ("http", "https") or not p.hostname:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Base URL must look like https://api.example.com/v1"
            )
    if body.key or body.base_url:
        result = _test_provider(pid, body.key.strip() if body.key else None, body.base_url)
        if not result["ok"]:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Test failed: {result['error']}")
    save_credentials(
        pid,
        key=body.key.strip() if body.key else None,
        base_url=body.base_url,
        enabled=body.enabled,
        clear_key=body.clear_key,
    )
    if pid == "google" and body.key:
        app_settings.set_gemini_key(body.key.strip())
    audit(
        owner,
        "settings.provider",
        "provider",
        pid,
        key_set=bool(body.key),
        base_url=body.base_url,
        enabled=body.enabled,
        cleared=body.clear_key,
    )
    return next(p for p in provider_status() if p["id"] == pid)


@router.post("/settings/providers/{pid}/test")
def test_provider(pid: str, _: AdminMember) -> dict:
    return _test_provider(pid)


@router.get("/settings/providers/{pid}/models")
def provider_models(pid: str, _: AdminMember) -> list[dict]:
    from studio_shared.ai.base import ProviderError
    from studio_shared.ai.client import AI

    try:
        return AI.list_models(pid)
    except (ProviderError, GeminiError) as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e


class RolesIn(BaseModel):
    """Each value is 'provider:model' (e.g. 'openai:gpt-4.1-mini', 'local:small'); fallbacks are tried in order."""

    text: str | None = Field(default=None, max_length=200)
    image: str | None = Field(default=None, max_length=200)
    tts: str | None = Field(default=None, max_length=200)
    video: str | None = Field(default=None, max_length=200)
    transcribe: str | None = Field(default=None, max_length=200)
    text_fallback: list[str] | None = Field(default=None, max_length=4)
    image_fallback: list[str] | None = Field(default=None, max_length=4)
    tts_fallback: list[str] | None = Field(default=None, max_length=4)


@router.put("/settings/roles")
def set_roles(body: RolesIn, owner: OwnerMember) -> dict:
    from studio_shared.ai.base import PROVIDERS, parse_model_ref

    models = dict(app_settings.get_row()["models"] or {})
    for role, value in body.model_dump(exclude_none=True).items():
        refs = value if isinstance(value, list) else [value]
        for ref in refs:
            parsed = parse_model_ref(ref)
            base_role = role.removesuffix("_fallback")
            if not parsed or base_role not in PROVIDERS[parsed[0]].roles:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{ref!r} can't be used for {base_role}")
        models[role] = value
    for role, value in list(models.items()):
        if value in ("", []):
            models.pop(role)
    db.execute("update settings set models = %s, updated_at = now() where id = 1", [models])
    audit(owner, "settings.roles", "settings", "models", **models)
    return {"models": models}


@router.get("/story/voices")
def story_voices(_: CurrentMember) -> dict:
    """Voices for whichever voice (TTS) provider is selected."""
    from studio_shared.ai.base import NotConfigured, ProviderError, parse_model_ref
    from studio_shared.ai.client import AI

    ref = parse_model_ref(app_settings.model_for("tts")) or ("google", "")
    try:
        return {"provider": ref[0], "voices": AI.voices(ref[0])}
    except (NotConfigured, ProviderError):
        return {"provider": "google", "voices": AI.voices("google")}
