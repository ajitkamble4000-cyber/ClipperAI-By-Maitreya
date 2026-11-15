-- Structure for features planned but NOT built yet (see docs/ROADMAP.md):
-- publishing to YouTube / Instagram with scheduling, saved templates, batch mode, A/B titles.
-- Tables exist so the data model is settled; no API or UI uses them yet.

create table public.channels (
  id              uuid primary key default gen_random_uuid(),
  platform        text not null check (platform in ('youtube', 'instagram')),
  display_name    text not null,
  external_id     text not null,               -- YouTube channel id / IG business account id
  oauth_token_enc text,                         -- encrypted refresh token (server only)
  scopes          text[] not null default '{}',
  status          text not null default 'connected',
  daily_quota     int,                          -- uploads/day this channel's API project allows
  created_by      uuid references public.members(user_id) on delete set null,
  created_at      timestamptz not null default now(),
  unique (platform, external_id)
);

create table public.publish_queue (
  id            uuid primary key default gen_random_uuid(),
  channel_id    uuid not null references public.channels(id) on delete cascade,
  project_id    uuid references public.projects(id) on delete cascade,
  clip_id       uuid references public.clips(id) on delete cascade,
  title         text not null,
  description   text not null default '',
  tags          text[] not null default '{}',
  privacy       text not null default 'private' check (privacy in ('private', 'unlisted', 'public')),
  scheduled_at  timestamptz,                    -- null = as soon as quota allows
  status        text not null default 'queued' check (status in ('queued', 'uploading', 'scheduled', 'published', 'failed')),
  external_id   text,                           -- platform video id once uploaded
  error         text,
  created_by    uuid references public.members(user_id) on delete set null,
  created_at    timestamptz not null default now()
);
create index publish_queue_due on public.publish_queue (status, scheduled_at);

create table public.templates (
  id          uuid primary key default gen_random_uuid(),
  kind        text not null check (kind in ('story', 'clip')),
  name        text not null,
  settings    jsonb not null,                   -- full preset: genre, style, voice, captions, music...
  created_by  uuid references public.members(user_id) on delete set null,
  created_at  timestamptz not null default now()
);

create table public.batches (
  id          uuid primary key default gen_random_uuid(),
  template_id uuid references public.templates(id) on delete set null,
  topics      text[] not null,
  project_ids uuid[] not null default '{}',
  status      text not null default 'draft',
  created_by  uuid references public.members(user_id) on delete set null,
  created_at  timestamptz not null default now()
);

alter table public.channels      enable row level security;
alter table public.publish_queue enable row level security;
alter table public.templates     enable row level security;
alter table public.batches       enable row level security;
-- Members may read; all writes go through the API. Tokens are never selectable by clients.
create policy publish_read   on public.publish_queue for select to authenticated using (public.is_member());
create policy templates_read on public.templates     for select to authenticated using (public.is_member());
create policy batches_read   on public.batches       for select to authenticated using (public.is_member());
create view public.channels_public with (security_invoker = true) as
  select id, platform, display_name, external_id, status, daily_quota, created_at from public.channels;
create policy channels_read on public.channels for select to authenticated using (public.is_member());
revoke select (oauth_token_enc) on public.channels from authenticated;
revoke all on public.channels, public.publish_queue, public.templates, public.batches from anon;
