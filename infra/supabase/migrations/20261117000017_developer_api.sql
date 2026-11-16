-- Developer API (Business): personal API keys and webhooks fired when jobs finish.

create table public.api_keys (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references public.members(user_id) on delete cascade,
  name         text not null check (char_length(name) between 1 and 60),
  prefix       text not null,                 -- first characters, shown so people can tell keys apart
  key_hash     text not null unique,          -- sha256 of the full key; the key itself is shown once
  created_at   timestamptz not null default now(),
  last_used_at timestamptz,
  revoked_at   timestamptz
);
create index api_keys_user on public.api_keys (user_id, created_at desc);
alter table public.api_keys enable row level security;   -- API only

create table public.webhooks (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null references public.members(user_id) on delete cascade,
  url              text not null check (char_length(url) <= 2048),
  secret_enc       text not null,              -- signing secret, encrypted at rest
  events           text[] not null default array['job.succeeded', 'job.failed'],
  active           boolean not null default true,
  failures         int not null default 0,
  last_status      int,
  last_delivery_at timestamptz,
  created_at       timestamptz not null default now()
);
create index webhooks_user on public.webhooks (user_id);
alter table public.webhooks enable row level security;   -- API only

create table public.webhook_deliveries (
  id          uuid primary key default gen_random_uuid(),
  webhook_id  uuid not null references public.webhooks(id) on delete cascade,
  event       text not null,
  attempt     int not null default 1,
  status_code int,
  ok          boolean not null default false,
  error       text,
  duration_ms int,
  created_at  timestamptz not null default now()
);
create index webhook_deliveries_hook on public.webhook_deliveries (webhook_id, created_at desc);
alter table public.webhook_deliveries enable row level security;   -- API only

-- The API is a Business feature (and part of the internal Team plan).
update public.plans set features = array_append(features, 'api_access')
 where id in ('business', 'team') and not ('api_access' = any(features));
