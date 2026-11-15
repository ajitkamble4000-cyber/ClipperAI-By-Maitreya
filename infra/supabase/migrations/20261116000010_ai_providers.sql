-- Many AI providers (not only Google). Keys are encrypted by the API (Fernet) and never readable by clients.
create table public.ai_providers (
  id          text primary key,           -- google | openai | anthropic | openrouter | compat | elevenlabs | replicate | stability
  key_enc     text,
  key_last4   text,
  base_url    text,                       -- only for 'compat' (Groq, DeepSeek, Mistral, Together, Ollama, ...)
  enabled     boolean not null default true,
  extra       jsonb not null default '{}'::jsonb,
  updated_at  timestamptz not null default now()
);
alter table public.ai_providers enable row level security;  -- no client policies: server only

-- Move an existing Gemini key into the vault.
insert into public.ai_providers (id, key_enc, key_last4)
select 'google', gemini_key_enc, gemini_key_last4 from public.settings where id = 1 and gemini_key_enc is not null
on conflict (id) do nothing;

alter table public.model_pricing add column per_1k_chars numeric(12,6) not null default 0;     -- TTS billed by characters
alter table public.model_pricing add column per_audio_minute numeric(12,6) not null default 0; -- transcription
alter table public.usage_events add column provider text;
alter table public.usage_events add column characters int not null default 0;

-- Estimates for popular models (USD). Check each provider's price page and edit in Admin → Pricing.
insert into public.model_pricing (model, input_per_mtok, output_per_mtok, per_image, per_video_second, per_1k_chars, per_audio_minute) values
  ('gpt-4.1-mini',               0.40,  1.60, 0,     0,    0,     0),
  ('gpt-4.1-nano',               0.10,  0.40, 0,     0,    0,     0),
  ('gpt-4.1',                    2.00,  8.00, 0,     0,    0,     0),
  ('gpt-4o-mini',                0.15,  0.60, 0,     0,    0,     0),
  ('gpt-4o',                     2.50, 10.00, 0,     0,    0,     0),
  ('gpt-5-mini',                 0.25,  2.00, 0,     0,    0,     0),
  ('gpt-5',                      1.25, 10.00, 0,     0,    0,     0),
  ('gpt-image-1',                5.00,  0,    0.063, 0,    0,     0),
  ('tts-1-hd',                   0,     0,    0,     0,    0.030, 0),
  ('tts-1',                      0,     0,    0,     0,    0.015, 0),
  ('gpt-4o-mini-tts',            0,     0,    0,     0,    0.012, 0),
  ('whisper-1',                  0,     0,    0,     0,    0,     0.006),
  ('whisper-large-v3',           0,     0,    0,     0,    0,     0.002),
  ('claude-opus',               15.00, 75.00, 0,     0,    0,     0),
  ('claude-sonnet',              3.00, 15.00, 0,     0,    0,     0),
  ('claude-haiku',               1.00,  5.00, 0,     0,    0,     0),
  ('eleven_multilingual_v2',     0,     0,    0,     0,    0.200, 0),
  ('eleven_turbo_v2_5',          0,     0,    0,     0,    0.100, 0),
  ('eleven_flash_v2_5',          0,     0,    0,     0,    0.100, 0),
  ('black-forest-labs/flux-schnell', 0, 0,    0.003, 0,    0,     0),
  ('black-forest-labs/flux-dev', 0,     0,    0.025, 0,    0,     0),
  ('black-forest-labs/flux-1.1-pro', 0, 0,    0.040, 0,    0,     0),
  ('kwaivgi/kling',              0,     0,    0,     0.28, 0,     0),
  ('minimax/video',              0,     0,    0,     0.10, 0,     0),
  ('wan-video/wan',              0,     0,    0,     0.05, 0,     0),
  ('stability:core',             0,     0,    0.03,  0,    0,     0),
  ('stability:ultra',            0,     0,    0.08,  0,    0,     0)
on conflict (model) do nothing;
