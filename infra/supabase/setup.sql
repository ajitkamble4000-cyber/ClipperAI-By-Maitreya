-- ClipperAI by Maitreya: complete database setup for a NEW Supabase project.
-- Paste into Supabase → SQL Editor → New query, then click Run. Generated from migrations/ by
-- infra/scripts/build-setup-sql.sh; do not edit by hand. Run it once, on an empty project.

begin;

-- ======================================================================== 20261115000001_core.sql
-- Shorts Studio core schema: members, invites, settings, projects, jobs.
-- Single workspace. Every table has RLS; only workspace members can read.
-- Writes that need secrets or queueing go through the API (service role).

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------- members
create table public.members (
  user_id      uuid primary key references auth.users(id) on delete cascade,
  email        text not null unique,
  display_name text,
  role         text not null default 'member' check (role in ('admin', 'member')),
  created_at   timestamptz not null default now()
);

create table public.invites (
  id          uuid primary key default gen_random_uuid(),
  email       text not null,
  role        text not null default 'member' check (role in ('admin', 'member')),
  invited_by  uuid references public.members(user_id) on delete set null,
  created_at  timestamptz not null default now(),
  accepted_at timestamptz
);
create unique index invites_open_email on public.invites (lower(email)) where accepted_at is null;

-- Helpers used by RLS policies. SECURITY DEFINER so policies on members
-- do not recurse into themselves.
create or replace function public.is_member() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.members where user_id = auth.uid());
$$;

create or replace function public.is_admin() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.members where user_id = auth.uid() and role = 'admin');
$$;

-- When an invited user first appears in auth.users, turn the invite into a membership.
create or replace function public.accept_invite_on_signup() returns trigger
language plpgsql security definer set search_path = public as $$
declare inv public.invites;
begin
  select * into inv from public.invites
   where lower(email) = lower(new.email) and accepted_at is null
   order by created_at desc limit 1;
  if found then
    insert into public.members (user_id, email, role)
    values (new.id, new.email, inv.role)
    on conflict (user_id) do nothing;
    update public.invites set accepted_at = now() where id = inv.id;
  end if;
  return new;
end $$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.accept_invite_on_signup();

-- ---------------------------------------------------------------- settings
-- Singleton row. Holds encrypted secrets, so NO client access at all:
-- the API reads it with the service role and returns masked values.
create table public.settings (
  id                    int primary key default 1 check (id = 1),
  gemini_key_enc        text,
  gemini_key_last4      text,
  models                jsonb not null default '{}'::jsonb,   -- {text,image,tts,video}
  monthly_budget_usd    numeric(10,2),
  proxy_enc             text,
  cookies_r2_key        text,
  source_retention_days int not null default 7 check (source_retention_days between 1 and 365),
  whisper_model         text not null default 'small',
  updated_at            timestamptz not null default now()
);
insert into public.settings (id) values (1);

-- Per-model price table (the Gemini API does not return prices). Admin-editable.
create table public.model_pricing (
  model               text primary key,      -- prefix match, e.g. 'gemini-2.5-flash'
  input_per_mtok      numeric(12,4) not null default 0,
  output_per_mtok     numeric(12,4) not null default 0,
  audio_out_per_mtok  numeric(12,4) not null default 0,
  per_image           numeric(12,4) not null default 0,
  per_video_second    numeric(12,4) not null default 0,
  updated_at          timestamptz not null default now()
);

-- ---------------------------------------------------------------- projects
create table public.projects (
  id            uuid primary key default gen_random_uuid(),
  type          text not null check (type in ('clip', 'story')),
  title         text not null default 'Untitled',
  status        text not null default 'draft',
  created_by    uuid references public.members(user_id) on delete set null,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  thumbnail_key text,
  meta          jsonb not null default '{}'::jsonb
);
create index projects_created_at on public.projects (created_at desc);
create index projects_title_trgm on public.projects using gin (to_tsvector('simple', title));

create or replace function public.touch_updated_at() returns trigger
language plpgsql as $$ begin new.updated_at = now(); return new; end $$;
create trigger projects_touch before update on public.projects
  for each row execute function public.touch_updated_at();

-- ---------------------------------------------------------------- uploads
-- Browser -> R2 multipart uploads, tracked so they can be resumed.
create table public.uploads (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references public.members(user_id) on delete cascade,
  purpose      text not null default 'source',
  r2_key       text not null,
  multipart_id text,
  filename     text not null,
  content_type text not null,
  size_bytes   bigint not null,
  part_size    bigint not null,
  status       text not null default 'uploading' check (status in ('uploading', 'complete', 'aborted')),
  created_at   timestamptz not null default now(),
  completed_at timestamptz
);

-- ---------------------------------------------------------------- jobs
create table public.jobs (
  id          uuid primary key default gen_random_uuid(),
  project_id  uuid references public.projects(id) on delete cascade,
  kind        text not null,
  status      text not null default 'queued'
              check (status in ('queued', 'running', 'succeeded', 'failed', 'canceled')),
  step        text,
  percent     int not null default 0 check (percent between 0 and 100),
  message     text,
  error       text,
  params      jsonb not null default '{}'::jsonb,
  result      jsonb not null default '{}'::jsonb,
  attempts    int not null default 0,
  heartbeat_at timestamptz,
  created_by  uuid references public.members(user_id) on delete set null,
  created_at  timestamptz not null default now(),
  started_at  timestamptz,
  finished_at timestamptz
);
create index jobs_project on public.jobs (project_id, created_at desc);
create index jobs_status on public.jobs (status) where status in ('queued', 'running');

create table public.job_steps (
  job_id      uuid not null references public.jobs(id) on delete cascade,
  name        text not null,
  status      text not null default 'pending' check (status in ('pending', 'running', 'done', 'failed', 'skipped')),
  output      jsonb not null default '{}'::jsonb,
  started_at  timestamptz,
  finished_at timestamptz,
  primary key (job_id, name)
);

create table public.job_logs (
  id      bigserial primary key,
  job_id  uuid not null references public.jobs(id) on delete cascade,
  ts      timestamptz not null default now(),
  level   text not null default 'info',
  message text not null
);
create index job_logs_job on public.job_logs (job_id, id);

-- ---------------------------------------------------------------- usage
create table public.usage_events (
  id            bigserial primary key,
  ts            timestamptz not null default now(),
  user_id       uuid references public.members(user_id) on delete set null,
  project_id    uuid references public.projects(id) on delete set null,
  job_id        uuid references public.jobs(id) on delete set null,
  model         text not null,
  kind          text not null,            -- text | image | tts | video | embed
  input_tokens  int not null default 0,
  output_tokens int not null default 0,
  images        int not null default 0,
  seconds       numeric(10,2) not null default 0,
  cost_usd      numeric(12,6) not null default 0,
  meta          jsonb not null default '{}'::jsonb
);
create index usage_events_ts on public.usage_events (ts desc);

-- ---------------------------------------------------------------- RLS
alter table public.members       enable row level security;
alter table public.invites       enable row level security;
alter table public.settings      enable row level security;
alter table public.model_pricing enable row level security;
alter table public.projects      enable row level security;
alter table public.uploads       enable row level security;
alter table public.jobs          enable row level security;
alter table public.job_steps     enable row level security;
alter table public.job_logs      enable row level security;
alter table public.usage_events  enable row level security;

create policy members_read  on public.members       for select to authenticated using (public.is_member());
create policy invites_read  on public.invites       for select to authenticated using (public.is_admin());
-- settings: no policies => no client access.
create policy pricing_read  on public.model_pricing for select to authenticated using (public.is_member());

create policy projects_read   on public.projects for select to authenticated using (public.is_member());
create policy projects_update on public.projects for update to authenticated
  using (public.is_member()) with check (public.is_member());
create policy projects_delete on public.projects for delete to authenticated
  using (public.is_admin() or created_by = auth.uid());

create policy uploads_read on public.uploads   for select to authenticated using (user_id = auth.uid());
create policy jobs_read    on public.jobs      for select to authenticated using (public.is_member());
create policy steps_read   on public.job_steps for select to authenticated using (public.is_member());
create policy logs_read    on public.job_logs  for select to authenticated using (public.is_member());
create policy usage_read   on public.usage_events for select to authenticated using (public.is_member());

-- Least privilege for the anon role: nothing.
revoke all on all tables in schema public from anon;

-- ---------------------------------------------------------------- realtime
alter publication supabase_realtime add table public.jobs, public.job_steps, public.projects;

-- ======================================================================== 20261115000002_content.sql
-- Content tables for Clipper and Story Studio, plus shared libraries.

-- ---------------------------------------------------------------- sources (clipper input)
create table public.sources (
  id             uuid primary key default gen_random_uuid(),
  project_id     uuid not null references public.projects(id) on delete cascade,
  kind           text not null check (kind in ('upload', 'url')),
  url            text,
  r2_key         text,
  filename       text,
  size_bytes     bigint,
  duration_s     numeric(10,3),
  width          int,
  height         int,
  fps            numeric(8,3),
  content_hash   text,                -- for transcript cache
  meta           jsonb not null default '{}'::jsonb,
  expires_at     timestamptz,
  deleted_at     timestamptz,
  created_at     timestamptz not null default now()
);
create index sources_project on public.sources (project_id);
create index sources_expiry on public.sources (expires_at) where deleted_at is null;

-- Transcript cache, keyed by source content hash + model.
create table public.transcripts (
  content_hash text not null,
  model        text not null,
  language     text,
  r2_key       text not null,
  created_at   timestamptz not null default now(),
  primary key (content_hash, model)
);

-- ---------------------------------------------------------------- clips
create table public.clips (
  id             uuid primary key default gen_random_uuid(),
  project_id     uuid not null references public.projects(id) on delete cascade,
  source_id      uuid references public.sources(id) on delete set null,
  idx            int not null,
  start_s        numeric(10,3) not null,
  end_s          numeric(10,3) not null,
  title          text not null default '',
  hook_text      text not null default '',
  description    text not null default '',
  hashtags       text[] not null default '{}',
  virality_score int not null default 0,
  reason         text not null default '',
  mode           text not null default 'ai' check (mode in ('ai', 'basic')),
  reframe        text not null default 'face',
  caption_style  jsonb not null default '{}'::jsonb,
  status         text not null default 'pending',
  base_key       text,        -- reframed 9:16, no captions (re-used for restyle)
  video_key      text,        -- final with captions
  thumb_key      text,
  filename       text,
  duration_s     numeric(10,3),
  updated_at     timestamptz not null default now(),
  created_at     timestamptz not null default now()
);
create index clips_project on public.clips (project_id, idx);
create trigger clips_touch before update on public.clips
  for each row execute function public.touch_updated_at();

-- ---------------------------------------------------------------- stories
create table public.stories (
  project_id      uuid primary key references public.projects(id) on delete cascade,
  idea            text not null default '',
  input_mode      text not null default 'idea' check (input_mode in ('idea', 'script')),
  genre           text not null default 'what_if',
  visual_style    text not null default 'realistic_3d',
  length_s        int not null default 45 check (length_s in (30, 45, 60, 90)),
  language        text not null default 'en' check (language in ('en', 'hi', 'hinglish')),
  voice           text,
  speaking_style  text not null default 'dramatic',
  voiceover_key   text,               -- user-uploaded voiceover
  motion_mode     text not null default 'standard' check (motion_mode in ('standard', 'premium')),
  music_track_id  uuid,
  music_auto      boolean not null default true,
  music_volume    numeric(4,2) not null default 0.25,
  sfx_enabled     boolean not null default true,
  caption_style   jsonb not null default '{}'::jsonb,
  hook_overlay    boolean not null default true,
  title           text not null default '',
  description     text not null default '',
  hashtags        text[] not null default '{}',
  hook_text       text not null default '',
  narration_key   text,               -- generated full narration audio
  alignment_key   text,               -- word timestamps JSON
  render_key      text,
  thumb_key       text,
  updated_by      uuid references public.members(user_id) on delete set null,
  updated_at      timestamptz not null default now()
);
create trigger stories_touch before update on public.stories
  for each row execute function public.touch_updated_at();

create table public.scenes (
  id                uuid primary key default gen_random_uuid(),
  project_id        uuid not null references public.projects(id) on delete cascade,
  idx               int not null,
  narration         text not null default '',
  image_prompt      text not null default '',
  camera_motion     text not null default 'zoom-in'
                    check (camera_motion in ('zoom-in', 'zoom-out', 'pan-left', 'pan-right', 'shake', 'static')),
  duration_estimate numeric(6,2) not null default 4,
  sfx_suggestion    text not null default '',
  on_screen_text    text not null default '',
  image_key         text,
  image_source      text check (image_source in ('ai', 'upload')),
  image_hash        text,
  video_key         text,             -- Veo result
  video_status      text,             -- null | queued | running | done | failed
  use_premium       boolean not null default false,
  audio_start_s     numeric(10,3),
  audio_end_s       numeric(10,3),
  updated_at        timestamptz not null default now(),
  created_at        timestamptz not null default now()
);
create index scenes_project on public.scenes (project_id, idx);
create trigger scenes_touch before update on public.scenes
  for each row execute function public.touch_updated_at();

create table public.characters (
  id           uuid primary key default gen_random_uuid(),
  project_id   uuid not null references public.projects(id) on delete cascade,
  name         text not null,
  description  text not null default '',
  ref_key      text,
  locked       boolean not null default false,
  created_at   timestamptz not null default now()
);
create index characters_project on public.characters (project_id);

-- Content-addressed cache of generated assets (images, audio, video).
create table public.assets (
  hash        text primary key,
  kind        text not null,
  r2_key      text not null,
  meta        jsonb not null default '{}'::jsonb,
  created_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------- libraries
create table public.visual_styles (
  id          text primary key,
  name        text not null,
  prompt      text not null,
  example_key text,
  builtin     boolean not null default false,
  created_by  uuid references public.members(user_id) on delete set null,
  created_at  timestamptz not null default now()
);

create table public.music_tracks (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  mood        text not null check (mood in ('suspense', 'horror', 'upbeat', 'epic', 'funny', 'calm', 'emotional')),
  r2_key      text not null,
  duration_s  numeric(10,3),
  created_by  uuid references public.members(user_id) on delete set null,
  created_at  timestamptz not null default now()
);

create table public.sfx (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  tag         text not null,           -- whoosh | boom | heartbeat | riser | ...
  r2_key      text not null,
  duration_s  numeric(10,3),
  created_by  uuid references public.members(user_id) on delete set null,
  created_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------- RLS
alter table public.sources       enable row level security;
alter table public.transcripts   enable row level security;
alter table public.clips         enable row level security;
alter table public.stories       enable row level security;
alter table public.scenes        enable row level security;
alter table public.characters    enable row level security;
alter table public.assets        enable row level security;
alter table public.visual_styles enable row level security;
alter table public.music_tracks  enable row level security;
alter table public.sfx           enable row level security;

create policy sources_read on public.sources for select to authenticated using (public.is_member());

create policy clips_read   on public.clips for select to authenticated using (public.is_member());
create policy clips_update on public.clips for update to authenticated
  using (public.is_member()) with check (public.is_member());

-- Storyboard drafts are edited directly from the browser (autosave), by any member.
create policy stories_read   on public.stories for select to authenticated using (public.is_member());
create policy stories_update on public.stories for update to authenticated
  using (public.is_member()) with check (public.is_member());

create policy scenes_read   on public.scenes for select to authenticated using (public.is_member());
create policy scenes_insert on public.scenes for insert to authenticated with check (public.is_member());
create policy scenes_update on public.scenes for update to authenticated
  using (public.is_member()) with check (public.is_member());
create policy scenes_delete on public.scenes for delete to authenticated using (public.is_member());

create policy characters_read   on public.characters for select to authenticated using (public.is_member());
create policy characters_update on public.characters for update to authenticated
  using (public.is_member()) with check (public.is_member());
create policy characters_delete on public.characters for delete to authenticated using (public.is_member());

create policy styles_read on public.visual_styles for select to authenticated using (public.is_member());
create policy music_read  on public.music_tracks  for select to authenticated using (public.is_member());
create policy sfx_read    on public.sfx           for select to authenticated using (public.is_member());
-- transcripts, assets: worker-only (no client policies).

-- Columns a browser must never change directly (keys are set by workers only).
revoke update on public.clips from authenticated;
grant update (title, description, hashtags, hook_text, caption_style) on public.clips to authenticated;
revoke update on public.scenes from authenticated;
grant update (idx, narration, image_prompt, camera_motion, duration_estimate, sfx_suggestion,
              on_screen_text, use_premium) on public.scenes to authenticated;
revoke insert on public.scenes from authenticated;
grant insert (project_id, idx, narration, image_prompt, camera_motion, duration_estimate,
              sfx_suggestion, on_screen_text) on public.scenes to authenticated;
revoke update on public.stories from authenticated;
grant update (idea, genre, visual_style, length_s, language, voice, speaking_style, motion_mode,
              music_track_id, music_auto, music_volume, sfx_enabled, caption_style, hook_overlay,
              title, description, hashtags, hook_text, updated_by) on public.stories to authenticated;
revoke update on public.characters from authenticated;
grant update (name, description, locked) on public.characters to authenticated;
revoke update on public.projects from authenticated;
grant update (title) on public.projects to authenticated;

revoke all on all tables in schema public from anon;

alter publication supabase_realtime add table public.clips, public.scenes, public.stories, public.characters;

-- ======================================================================== 20261115000003_seed_data.sql
-- Default data: price estimates (edit in Settings → Pricing) and built-in visual styles.
-- Prices are USD and are matched by longest model-name prefix. They are estimates
-- taken from Google's public price list at build time; check them against
-- https://ai.google.dev/gemini-api/docs/pricing and adjust.

insert into public.model_pricing (model, input_per_mtok, output_per_mtok, audio_out_per_mtok, per_image, per_video_second) values
  ('gemini-2.5-pro',              1.25, 10.00,  0,     0,     0),
  ('gemini-2.5-flash-lite',       0.10,  0.40,  0,     0,     0),
  ('gemini-2.5-flash',            0.30,  2.50,  0,     0,     0),
  ('gemini-2.5-flash-image',      0.30,  0,     0,     0.039, 0),
  ('gemini-2.5-flash-preview-tts',0.50,  0,    10.00,  0,     0),
  ('gemini-2.5-pro-preview-tts',  1.00,  0,    20.00,  0,     0),
  ('gemini-3-pro',                2.00, 12.00,  0,     0,     0),
  ('gemini-3-pro-image',          2.00,  0,     0,     0.134, 0),
  ('gemini-3-flash',              0.50,  3.00,  0,     0,     0),
  ('imagen-4',                    0,     0,     0,     0.04,  0),
  ('veo-2',                       0,     0,     0,     0,     0.35),
  ('veo-3.0-fast',                0,     0,     0,     0,     0.15),
  ('veo-3.0',                     0,     0,     0,     0,     0.40),
  ('veo-3.1-fast',                0,     0,     0,     0,     0.15),
  ('veo-3.1',                     0,     0,     0,     0,     0.40)
on conflict (model) do nothing;

insert into public.visual_styles (id, name, prompt, builtin) values
  ('realistic_3d', 'Realistic 3D render',
   'Hyper-realistic 3D render, cinematic lighting, volumetric light, dramatic rim light, shallow depth of field, Unreal Engine 5 quality, highly detailed textures, photoreal materials, epic scale, vertical 9:16 composition with the subject centered', true),
  ('pixar_3d', 'Pixar-style 3D',
   'Stylized 3D animation in the style of a modern animated feature film, soft global illumination, appealing rounded character design, expressive faces, vibrant saturated colors, subsurface scattering, vertical 9:16 composition', true),
  ('dark_horror', 'Dark horror illustration',
   'Dark horror digital illustration, desaturated palette with deep shadows, sickly green and blood red accents, heavy film grain, fog, unsettling atmosphere, chiaroscuro lighting, vertical 9:16 composition', true),
  ('anime', 'Anime',
   'High quality anime key visual, clean line art, cel shading, vivid colors, dramatic sky, detailed background art, cinematic anime lighting, vertical 9:16 composition', true),
  ('comic', 'Comic',
   'Bold comic book art, thick ink outlines, halftone dot shading, dynamic angles, high-contrast flat colors, graphic novel panel style, vertical 9:16 composition', true)
on conflict (id) do nothing;

-- ======================================================================== 20261115000004_scene_characters.sql
-- Which recurring characters appear in each scene (drives reference images for consistency).
alter table public.scenes add column characters text[] not null default '{}';
grant update (characters) on public.scenes to authenticated;
grant insert (characters) on public.scenes to authenticated;

-- ======================================================================== 20261115000005_veo.sql
-- Veo long-running operations are persisted per scene so a restarted worker resumes polling
-- instead of paying for a second generation.
alter table public.scenes add column veo_operation text;
alter table public.scenes add column veo_error text;
alter table public.scenes add column veo_started_at timestamptz;

-- ======================================================================== 20261115000006_later_features.sql
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

-- ======================================================================== 20261116000007_business_accounts.sql
-- V2: a public product. Anyone can sign up (email verified); projects are private to their creator;
-- one owner (OWNER_EMAIL, enforced by the API) appoints admins; a Staff / Creator team gets everything
-- free and shares a team library; plans gate features and token allowances.

-- ---------------------------------------------------------------- plans
create table public.plans (
  id               text primary key,
  name             text not null,
  description      text not null default '',
  daily_tokens     int,                       -- null = unlimited
  price_usd_month  numeric(10,2) not null default 0,
  features         text[] not null default '{}',
  limits           jsonb not null default '{}'::jsonb,
  public           boolean not null default true,   -- shown on the pricing page
  highlight        boolean not null default false,
  sort             int not null default 0,
  updated_at       timestamptz not null default now()
);

insert into public.plans (id, name, description, daily_tokens, price_usd_month, features, limits, public, highlight, sort) values
  ('free', 'Free', 'Everything you need to try it: clips, captions and stories.', 1000, 0,
   array['clipper','captions','story','exports','basic_voices'],
   '{"max_clips_per_job": 5, "max_upload_mb": 1024, "max_source_minutes": 60, "concurrent_jobs": 1, "watermark": true, "max_batch": 1}',
   true, false, 1),
  ('pro', 'Pro', 'For creators posting every day: more tokens, no watermark, pro tools.', 5000, 19,
   array['clipper','captions','story','exports','basic_voices','no_watermark','visual_analysis','brand_kit','translation',
         'filler_removal','keyword_emphasis','templates','premium_voices','thumbnails','title_variants','share_links','output_formats'],
   '{"max_clips_per_job": 15, "max_upload_mb": 2048, "max_source_minutes": 180, "concurrent_jobs": 3, "watermark": false, "max_batch": 5}',
   true, true, 2),
  ('business', 'Business', 'For agencies and teams: premium AI video, batch mode and the biggest limits.', 20000, 49,
   array['clipper','captions','story','exports','basic_voices','no_watermark','visual_analysis','brand_kit','translation',
         'filler_removal','keyword_emphasis','templates','premium_voices','thumbnails','title_variants','share_links','output_formats',
         'premium_video','batch','priority'],
   '{"max_clips_per_job": 20, "max_upload_mb": 4096, "max_source_minutes": 240, "concurrent_jobs": 6, "watermark": false, "max_batch": 25}',
   true, false, 3),
  ('team', 'Team (Staff & Creators)', 'Internal: staff and content creators get everything free.', null, 0,
   array['clipper','captions','story','exports','basic_voices','no_watermark','visual_analysis','brand_kit','translation',
         'filler_removal','keyword_emphasis','templates','premium_voices','thumbnails','title_variants','share_links','output_formats',
         'premium_video','batch','priority'],
   '{"max_clips_per_job": 20, "max_upload_mb": 4096, "max_source_minutes": 240, "concurrent_jobs": 10, "watermark": false, "max_batch": 50}',
   false, false, 9);

alter table public.plans enable row level security;
create policy plans_read on public.plans for select to anon, authenticated using (true);
grant select on public.plans to anon;

-- ---------------------------------------------------------------- members become user profiles
alter table public.members drop constraint members_role_check;
update public.members set role = 'user' where role = 'member';
alter table public.members add constraint members_role_check check (role in ('owner', 'admin', 'user'));
alter table public.members alter column role set default 'user';
alter table public.members add column plan_id text not null default 'free' references public.plans(id);
alter table public.members add column team text check (team in ('staff', 'creator'));
alter table public.members add column status text not null default 'active' check (status in ('active', 'suspended'));
alter table public.members add column suspended_reason text;
alter table public.members add column last_seen_at timestamptz;
alter table public.members add column onboarding jsonb not null default '{}'::jsonb;
create unique index members_single_owner on public.members ((role)) where role = 'owner';

alter table public.invites drop constraint invites_role_check;
update public.invites set role = 'user' where role = 'member';
alter table public.invites add constraint invites_role_check check (role in ('admin', 'user'));
alter table public.invites alter column role set default 'user';
alter table public.invites add column team text check (team in ('staff', 'creator'));
alter table public.invites add column plan_id text references public.plans(id);

-- Every new auth user gets a profile; an open invite (if any) sets role/team/plan.
create or replace function public.accept_invite_on_signup() returns trigger
language plpgsql security definer set search_path = public as $$
declare inv public.invites;
begin
  select * into inv from public.invites
   where lower(email) = lower(new.email) and accepted_at is null
   order by created_at desc limit 1;
  insert into public.members (user_id, email, role, team, plan_id)
  values (new.id, lower(new.email), coalesce(inv.role, 'user'), inv.team,
          coalesce(inv.plan_id, case when inv.team is not null then 'team' else 'free' end))
  on conflict (user_id) do nothing;
  if inv.id is not null then
    update public.invites set accepted_at = now() where id = inv.id;
  end if;
  return new;
end $$;

-- ---------------------------------------------------------------- helpers for RLS
create or replace function public.is_member() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.members where user_id = auth.uid() and status = 'active');
$$;

create or replace function public.is_admin() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.members where user_id = auth.uid() and role in ('owner', 'admin') and status = 'active');
$$;

create or replace function public.my_team() returns text
language sql stable security definer set search_path = public as $$
  select team from public.members where user_id = auth.uid() and status = 'active';
$$;

-- A project is visible to its creator, to admins, and (team library) to Staff/Creator team members
-- for projects made by other team members.
create or replace function public.can_view_project(pid uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from public.projects p left join public.members m on m.user_id = p.created_by
     where p.id = pid
       and (p.created_by = auth.uid() or public.is_admin() or (public.my_team() is not null and m.team is not null))
  );
$$;

create or replace function public.can_view_job(jid uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from public.jobs j
     where j.id = jid
       and (j.created_by = auth.uid() or public.is_admin() or (j.project_id is not null and public.can_view_project(j.project_id)))
  );
$$;

-- ---------------------------------------------------------------- audit log
create table public.audit_log (
  id          bigserial primary key,
  ts          timestamptz not null default now(),
  actor_id    uuid references public.members(user_id) on delete set null,
  actor_email text,
  action      text not null,
  target_type text,
  target_id   text,
  details     jsonb not null default '{}'::jsonb
);
create index audit_log_ts on public.audit_log (ts desc);
alter table public.audit_log enable row level security;
create policy audit_read on public.audit_log for select to authenticated using (public.is_admin());

-- ---------------------------------------------------------------- announcements
create table public.announcements (
  id         uuid primary key default gen_random_uuid(),
  message    text not null,
  level      text not null default 'info' check (level in ('info', 'warning', 'success')),
  active     boolean not null default true,
  created_by uuid references public.members(user_id) on delete set null,
  created_at timestamptz not null default now(),
  expires_at timestamptz
);
alter table public.announcements enable row level security;
create policy announcements_read on public.announcements for select to authenticated
  using (active and (expires_at is null or expires_at > now()));

-- ---------------------------------------------------------------- replace "any member sees all" policies
drop policy members_read on public.members;
create policy members_read on public.members for select to authenticated
  using (user_id = auth.uid() or public.is_admin() or (public.my_team() is not null and team is not null));

drop policy pricing_read on public.model_pricing;
create policy pricing_read on public.model_pricing for select to authenticated using (public.is_admin());

drop policy projects_read on public.projects;
drop policy projects_update on public.projects;
drop policy projects_delete on public.projects;
create policy projects_read on public.projects for select to authenticated using (public.can_view_project(id));
create policy projects_update on public.projects for update to authenticated
  using (public.can_view_project(id)) with check (public.can_view_project(id));
create policy projects_delete on public.projects for delete to authenticated
  using (created_by = auth.uid() or public.is_admin());

drop policy jobs_read on public.jobs;
drop policy steps_read on public.job_steps;
drop policy logs_read on public.job_logs;
create policy jobs_read  on public.jobs      for select to authenticated using (public.can_view_job(id));
create policy steps_read on public.job_steps for select to authenticated using (public.can_view_job(job_id));
create policy logs_read  on public.job_logs  for select to authenticated using (public.can_view_job(job_id));

drop policy usage_read on public.usage_events;
create policy usage_read on public.usage_events for select to authenticated using (user_id = auth.uid() or public.is_admin());

drop policy sources_read on public.sources;
create policy sources_read on public.sources for select to authenticated using (public.can_view_project(project_id));

drop policy clips_read on public.clips;
drop policy clips_update on public.clips;
create policy clips_read on public.clips for select to authenticated using (public.can_view_project(project_id));
create policy clips_update on public.clips for update to authenticated
  using (public.can_view_project(project_id)) with check (public.can_view_project(project_id));

drop policy stories_read on public.stories;
drop policy stories_update on public.stories;
create policy stories_read on public.stories for select to authenticated using (public.can_view_project(project_id));
create policy stories_update on public.stories for update to authenticated
  using (public.can_view_project(project_id)) with check (public.can_view_project(project_id));

drop policy scenes_read on public.scenes;
drop policy scenes_insert on public.scenes;
drop policy scenes_update on public.scenes;
drop policy scenes_delete on public.scenes;
create policy scenes_read on public.scenes for select to authenticated using (public.can_view_project(project_id));
create policy scenes_insert on public.scenes for insert to authenticated with check (public.can_view_project(project_id));
create policy scenes_update on public.scenes for update to authenticated
  using (public.can_view_project(project_id)) with check (public.can_view_project(project_id));
create policy scenes_delete on public.scenes for delete to authenticated using (public.can_view_project(project_id));

drop policy characters_read on public.characters;
drop policy characters_update on public.characters;
drop policy characters_delete on public.characters;
create policy characters_read on public.characters for select to authenticated using (public.can_view_project(project_id));
create policy characters_update on public.characters for update to authenticated
  using (public.can_view_project(project_id)) with check (public.can_view_project(project_id));
create policy characters_delete on public.characters for delete to authenticated using (public.can_view_project(project_id));

-- Planned-feature tables become per-user.
alter table public.channels add column user_id uuid references public.members(user_id) on delete cascade;
alter table public.templates add column user_id uuid references public.members(user_id) on delete cascade;
alter table public.batches add column user_id uuid references public.members(user_id) on delete cascade;
drop policy publish_read on public.publish_queue;
drop policy templates_read on public.templates;
drop policy batches_read on public.batches;
drop policy channels_read on public.channels;
create policy publish_read on public.publish_queue for select to authenticated using (created_by = auth.uid() or public.is_admin());
create policy templates_read on public.templates for select to authenticated using (user_id is null or user_id = auth.uid());
create policy batches_read on public.batches for select to authenticated using (user_id = auth.uid() or public.is_admin());
create policy channels_read on public.channels for select to authenticated using (user_id = auth.uid());

alter publication supabase_realtime add table public.announcements;

-- ======================================================================== 20261116000008_tokens.sql
-- Token economy: a daily allowance (refilled every UTC midnight) + bonus tokens granted by admins.
-- Every charge, refund, grant and refill is written to an append-only ledger.

create table public.token_prices (
  action      text primary key,
  label       text not null,
  tokens      int not null check (tokens >= 0),
  unit        text not null default 'each',
  description text not null default '',
  sort        int not null default 0,
  updated_at  timestamptz not null default now()
);

insert into public.token_prices (action, label, tokens, unit, description, sort) values
  ('clip_job',            'Clip job (base)',             50, 'job',        'Download, transcribe and analyse a video', 1),
  ('clip_ai_per_clip',    'AI clip',                     40, 'clip',       'Each clip picked, titled and rendered with AI', 2),
  ('clip_basic_per_clip', 'Basic clip',                  15, 'clip',       'Each clip in basic mode (no AI)', 3),
  ('captions_job',        'Caption a video',             40, 'video',      'Caption a whole short video', 4),
  ('visual_analysis',     'Visual analysis',             60, 'job',        'The AI also watches the video', 5),
  ('translation',         'Translate captions',          30, 'language',   'Captions in another language', 6),
  ('rerender',            'Re-render a clip',            10, 'render',     'New timing, framing or caption style', 7),
  ('story_script',        'Story script',                30, 'script',     'AI script + storyboard', 10),
  ('scene_rewrite',       'Rewrite a scene',              5, 'scene',      'AI rewrite / stronger hook', 11),
  ('character_ref',       'Character reference',         20, 'character',  'Reference image for consistency', 12),
  ('scene_image',         'Scene image',                 25, 'image',      'One 9:16 scene image', 13),
  ('image_edit',          'Edit an image',               25, 'image',      'Edit a scene image with a prompt', 14),
  ('voice_per_30s',       'AI voiceover',                30, '30 seconds', 'Narration voice, per started 30 s', 15),
  ('voice_upload',        'Time my recording',           10, 'recording',  'Align your own voiceover to the script', 16),
  ('render',              'Render a story',              50, 'render',     'Motion, music, captions, final video', 17),
  ('veo_per_second',      'AI video',                    40, 'second',     'Premium AI video per generated second', 18),
  ('thumbnail',           'AI thumbnail',                20, 'thumbnail',  'Generated thumbnail image', 19),
  ('title_variants',      'Title ideas',                  5, 'request',    'Alternative titles and hashtags', 20);

create table public.wallets (
  user_id          uuid primary key references public.members(user_id) on delete cascade,
  daily_balance    int not null default 0 check (daily_balance >= 0),
  daily_reset_at   timestamptz not null default now(),
  bonus_balance    int not null default 0 check (bonus_balance >= 0),
  lifetime_spent   bigint not null default 0,
  updated_at       timestamptz not null default now()
);

create table public.token_ledger (
  id            bigserial primary key,
  ts            timestamptz not null default now(),
  user_id       uuid not null references public.members(user_id) on delete cascade,
  delta         int not null,
  bucket        text not null check (bucket in ('daily', 'bonus', 'mixed', 'none')),
  reason        text not null,              -- charge | refund | grant | revoke | daily_refill | waived
  action        text,
  job_id        uuid references public.jobs(id) on delete set null,
  actor_id      uuid references public.members(user_id) on delete set null,
  daily_after   int,
  bonus_after   int,
  meta          jsonb not null default '{}'::jsonb
);
create index token_ledger_user on public.token_ledger (user_id, ts desc);
create index token_ledger_job on public.token_ledger (job_id) where job_id is not null;

alter table public.members add column daily_tokens_override int check (daily_tokens_override >= 0);
alter table public.jobs add column tokens_charged int not null default 0;

alter table public.token_prices enable row level security;
alter table public.wallets enable row level security;
alter table public.token_ledger enable row level security;
create policy token_prices_read on public.token_prices for select to anon, authenticated using (true);
grant select on public.token_prices to anon;
create policy wallets_read on public.wallets for select to authenticated using (user_id = auth.uid() or public.is_admin());
create policy ledger_read on public.token_ledger for select to authenticated using (user_id = auth.uid() or public.is_admin());

alter publication supabase_realtime add table public.wallets;

-- ======================================================================== 20261116000009_notifications.sql
-- In-app notifications (job finished / failed, token grants, announcements targeted at a user).
create table public.notifications (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references public.members(user_id) on delete cascade,
  kind       text not null default 'info' check (kind in ('info', 'success', 'error', 'tokens')),
  title      text not null,
  body       text not null default '',
  link       text,
  read_at    timestamptz,
  created_at timestamptz not null default now()
);
create index notifications_user on public.notifications (user_id, created_at desc);
alter table public.notifications enable row level security;
create policy notifications_read on public.notifications for select to authenticated using (user_id = auth.uid());
create policy notifications_update on public.notifications for update to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());
revoke update on public.notifications from authenticated;
grant update (read_at) on public.notifications to authenticated;
alter publication supabase_realtime add table public.notifications;

-- ======================================================================== 20261116000010_ai_providers.sql
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

-- ======================================================================== 20261116000011_quick_captions.sql
-- Any-link quick mode & captions tool: output formats, caption files, per-clip render options, brand kits.

-- Clips can now be the whole video (captions tool / short sources in auto mode) and any of four formats.
alter table public.clips drop constraint if exists clips_mode_check;
alter table public.clips add constraint clips_mode_check check (mode in ('ai', 'basic', 'whole'));
alter table public.clips add column aspect text not null default '9:16'
  check (aspect in ('9:16', '1:1', '4:5', '16:9'));
alter table public.clips add column words_key text;             -- caption words exactly as burned (translated / jump-cut)
alter table public.clips add column render_opts jsonb not null default '{}'::jsonb;  -- jump cuts, overlays, emphasis...
alter table public.clips add column language text;              -- caption language of words_key

-- Brand kit (Pro+): logo, handle, colours and defaults applied to every export.
create table public.brand_kits (
  user_id        uuid primary key references public.members(user_id) on delete cascade,
  logo_key       text,
  logo_position  text not null default 'top-right' check (logo_position in ('top-left', 'top-right')),
  logo_opacity   real not null default 0.9 check (logo_opacity between 0.2 and 1),
  handle         text not null default '' check (char_length(handle) <= 40),
  primary_color  text not null default '#FFE500' check (primary_color ~ '^#[0-9A-Fa-f]{6}$'),
  caption_preset text,
  progress_bar   boolean not null default false,
  updated_at     timestamptz not null default now()
);
create trigger brand_kits_touch before update on public.brand_kits
  for each row execute function public.touch_updated_at();
alter table public.brand_kits enable row level security;
create policy brand_kits_read on public.brand_kits for select to authenticated
  using (user_id = auth.uid() or public.is_admin());
grant select on public.brand_kits to authenticated;   -- writes go through the API

-- New priced actions.
insert into public.token_prices (action, label, tokens, unit, description, sort) values
  ('jump_cuts',  'Remove silences & fillers', 10, 'video', 'Tighter pacing: pauses and "um/uh" cut out', 8),
  ('batch_link', 'Batch link',                  0, 'link',  'Extra charge per link in batch mode (on top of the job)', 9)
on conflict (action) do nothing;

-- ======================================================================== 20261116000012_user_panel.sql
-- User panel: plan upgrade requests (approved by the owner/admins until online billing is connected) and
-- public share links for finished clips and stories.

create table public.upgrade_requests (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references public.members(user_id) on delete cascade,
  plan_id     text not null references public.plans(id),
  note        text not null default '' check (char_length(note) <= 500),
  status      text not null default 'pending' check (status in ('pending', 'approved', 'declined', 'canceled')),
  decided_by  uuid references public.members(user_id) on delete set null,
  decided_at  timestamptz,
  reply       text not null default '' check (char_length(reply) <= 500),
  created_at  timestamptz not null default now()
);
create index upgrade_requests_status on public.upgrade_requests (status, created_at desc);
create unique index upgrade_requests_one_pending on public.upgrade_requests (user_id) where status = 'pending';
alter table public.upgrade_requests enable row level security;
create policy upgrade_requests_read on public.upgrade_requests for select to authenticated
  using (user_id = auth.uid() or public.is_admin());
grant select on public.upgrade_requests to authenticated;

create table public.share_links (
  token       text primary key check (char_length(token) between 16 and 64),
  project_id  uuid not null references public.projects(id) on delete cascade,
  clip_id     uuid references public.clips(id) on delete cascade,
  created_by  uuid not null references public.members(user_id) on delete cascade,
  views       int not null default 0,
  expires_at  timestamptz,
  revoked_at  timestamptz,
  created_at  timestamptz not null default now()
);
create index share_links_project on public.share_links (project_id);
alter table public.share_links enable row level security;
create policy share_links_read on public.share_links for select to authenticated
  using (created_by = auth.uid() or public.is_admin());
grant select on public.share_links to authenticated;   -- public viewing goes through the API by token

-- Self sign-up: keep the name typed on the sign-up form.
create or replace function public.accept_invite_on_signup() returns trigger
language plpgsql security definer set search_path = public as $$
declare inv public.invites;
begin
  select * into inv from public.invites
   where lower(email) = lower(new.email) and accepted_at is null
   order by created_at desc limit 1;
  insert into public.members (user_id, email, role, team, plan_id, display_name)
  values (new.id, lower(new.email), coalesce(inv.role, 'user'), inv.team,
          coalesce(inv.plan_id, case when inv.team is not null then 'team' else 'free' end),
          nullif(left(trim(coalesce(new.raw_user_meta_data->>'display_name', '')), 80), ''))
  on conflict (user_id) do nothing;
  if inv.id is not null then
    update public.invites set accepted_at = now() where id = inv.id;
  end if;
  return new;
end $$;

-- ======================================================================== 20261116000013_creator_extras.sql
-- Creator extras: templates (built-in ones have user_id null and are visible to everyone; saving your own
-- needs the Templates feature), AI thumbnails (covers) and title/hashtag ideas.

create index if not exists templates_user on public.templates (user_id, kind, created_at desc);

insert into public.templates (kind, name, settings, user_id) values
  ('clip', 'Podcast highlights', '{"mode":"clips","content_type":"podcast","reframe":"face","num_clips":5,"min_len":30,"max_len":60,"caption_style":{"preset":"bold_pop"},"hook_overlay":true}', null),
  ('clip', 'Gaming moments', '{"mode":"clips","content_type":"gaming","reframe":"action","num_clips":5,"min_len":15,"max_len":45,"caption_style":{"preset":"bold_pop","emoji":true},"hook_overlay":true}', null),
  ('clip', 'Sports highlights', '{"mode":"clips","content_type":"sports","reframe":"action","num_clips":5,"min_len":15,"max_len":40,"caption_style":{"preset":"boxed"},"hook_overlay":true}', null),
  ('clip', 'TikTok captions', '{"mode":"captions","reframe":"face","caption_style":{"preset":"karaoke"},"hook_overlay":false}', null),
  ('clip', 'Clean subtitles', '{"mode":"captions","reframe":"blur","caption_style":{"preset":"minimal","uppercase":false,"words_per_line":6},"hook_overlay":false}', null),
  ('clip', 'YouTube 16:9 (Pro)', '{"mode":"captions","aspect":"16:9","reframe":"center","caption_style":{"preset":"minimal","uppercase":false,"words_per_line":7},"hook_overlay":false,"remove_silence":true}', null),
  ('story', 'Scary story', '{"genre":"scary","visual_style":"dark_horror","length_s":45,"speaking_style":"creepy_whisper"}', null),
  ('story', 'Fun facts', '{"genre":"facts","visual_style":"realistic_3d","length_s":30,"speaking_style":"excited"}', null),
  ('story', 'Kids bedtime', '{"genre":"bedtime","visual_style":"pixar_3d","length_s":60,"speaking_style":"calm"}', null);

alter table public.clips   add column covers jsonb not null default '{}'::jsonb;  -- {"youtube": key, "vertical": key}
alter table public.clips   add column ideas  jsonb not null default '{}'::jsonb;  -- {"titles": [...], "hashtags": [...]}
alter table public.stories add column covers jsonb not null default '{}'::jsonb;
alter table public.stories add column ideas  jsonb not null default '{}'::jsonb;

-- ======================================================================== 20261117000014_growth.sql
-- Growth: promo codes (bonus tokens or plan trials), referrals, and owner site controls.

-- ---------------------------------------------------------------- site controls (settings row id=1)
alter table public.settings add column signups_open boolean not null default true;
alter table public.settings add column jobs_paused boolean not null default false;
alter table public.settings add column maintenance_message text not null default ''
  check (char_length(maintenance_message) <= 300);
alter table public.settings add column referral_reward int not null default 500 check (referral_reward between 0 and 100000);
alter table public.settings add column referral_monthly_cap int not null default 20 check (referral_monthly_cap between 0 and 1000);

-- ---------------------------------------------------------------- plan trials
alter table public.members add column plan_expires_at timestamptz;   -- end of a trial plan
alter table public.members add column plan_before_trial text references public.plans(id);

-- ---------------------------------------------------------------- promo codes
create table public.promo_codes (
  code            text primary key check (code ~ '^[A-Z0-9_-]{3,32}$'),
  kind            text not null check (kind in ('tokens', 'trial')),
  tokens          int not null default 0 check (tokens between 0 and 1000000),
  plan_id         text references public.plans(id),
  trial_days      int check (trial_days between 1 and 365),
  max_redemptions int check (max_redemptions > 0),          -- null = unlimited
  redemptions     int not null default 0,
  expires_at      timestamptz,
  active          boolean not null default true,
  note            text not null default '' check (char_length(note) <= 200),
  created_by      uuid references public.members(user_id) on delete set null,
  created_at      timestamptz not null default now(),
  check ((kind = 'tokens' and tokens > 0) or (kind = 'trial' and plan_id is not null and trial_days is not null))
);
alter table public.promo_codes enable row level security;   -- API only (no grants)

create table public.promo_redemptions (
  code        text not null references public.promo_codes(code) on delete cascade,
  user_id     uuid not null references public.members(user_id) on delete cascade,
  redeemed_at timestamptz not null default now(),
  primary key (code, user_id)
);
alter table public.promo_redemptions enable row level security;
create policy promo_redemptions_read on public.promo_redemptions for select to authenticated using (user_id = auth.uid());
grant select on public.promo_redemptions to authenticated;

-- ---------------------------------------------------------------- referrals
alter table public.members add column referral_code text unique check (referral_code ~ '^[a-z0-9]{6,16}$');

create table public.referrals (
  referred_id  uuid primary key references public.members(user_id) on delete cascade,
  referrer_id  uuid not null references public.members(user_id) on delete cascade,
  status       text not null default 'pending' check (status in ('pending', 'rewarded', 'capped')),
  reward       int not null default 0,
  created_at   timestamptz not null default now(),
  rewarded_at  timestamptz,
  check (referred_id <> referrer_id)
);
create index referrals_referrer on public.referrals (referrer_id, created_at desc);
alter table public.referrals enable row level security;
create policy referrals_read on public.referrals for select to authenticated
  using (referrer_id = auth.uid() or referred_id = auth.uid() or public.is_admin());
grant select on public.referrals to authenticated;

-- ---------------------------------------------------------------- sign-up trigger: closed sign-ups + referrals
create or replace function public.accept_invite_on_signup() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  inv public.invites;
  open boolean;
  ref_code text;
  referrer uuid;
begin
  select * into inv from public.invites
   where lower(email) = lower(new.email) and accepted_at is null
   order by created_at desc limit 1;
  select coalesce(signups_open, true) into open from public.settings where id = 1;
  if open is false and inv.id is null then
    raise exception 'Sign-ups are closed right now' using errcode = 'P0001';
  end if;
  insert into public.members (user_id, email, role, team, plan_id, display_name)
  values (new.id, lower(new.email), coalesce(inv.role, 'user'), inv.team,
          coalesce(inv.plan_id, case when inv.team is not null then 'team' else 'free' end),
          nullif(left(trim(coalesce(new.raw_user_meta_data->>'display_name', '')), 80), ''))
  on conflict (user_id) do nothing;
  if inv.id is not null then
    update public.invites set accepted_at = now() where id = inv.id;
  end if;
  ref_code := lower(nullif(trim(coalesce(new.raw_user_meta_data->>'ref', '')), ''));
  if ref_code is not null then
    select user_id into referrer from public.members where referral_code = ref_code;
    if referrer is not null and referrer <> new.id then
      insert into public.referrals (referred_id, referrer_id) values (new.id, referrer) on conflict do nothing;
    end if;
  end if;
  return new;
end $$;

-- ======================================================================== 20261117000015_editing.sql
-- Editing extras: compilations are priced; caption edits and exports reuse existing prices.
insert into public.token_prices (action, label, tokens, unit, description, sort) values
  ('compilation', 'Compilation', 20, 'video', 'Join several clips into one video', 21)
on conflict (action) do nothing;

-- ======================================================================== 20261117000016_repurpose.sql
-- Repurpose: AI write-ups from a video, and a searchable transcript index ("search what was said").

alter table public.projects add column repurpose jsonb not null default '{}'::jsonb;

create table public.project_transcripts (
  project_id  uuid primary key references public.projects(id) on delete cascade,
  language    text,
  text        text not null default '',
  segments    jsonb not null default '[]'::jsonb,   -- [{start, end, text}]
  tsv         tsvector generated always as (to_tsvector('simple', coalesce(text, ''))) stored,
  updated_at  timestamptz not null default now()
);
create index project_transcripts_tsv on public.project_transcripts using gin (tsv);
alter table public.project_transcripts enable row level security;   -- searched through the API (access checked)

insert into public.token_prices (action, label, tokens, unit, description, sort) values
  ('repurpose', 'Repurpose a video', 25, 'video', 'Summary, chapters, quotes, blog post, thread, LinkedIn post, newsletter', 22)
on conflict (action) do nothing;

-- ======================================================================== 20261117000017_developer_api.sql
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

-- ======================================================================== 20261118000018_calendar.sql
-- Content calendar: plan when each clip/story goes out on which platform, get reminded, mark it posted.

create table public.schedule_items (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null references public.members(user_id) on delete cascade,
  project_id     uuid not null references public.projects(id) on delete cascade,
  clip_id        uuid references public.clips(id) on delete cascade,
  platform       text not null check (platform in ('youtube', 'tiktok', 'instagram', 'facebook', 'x', 'linkedin', 'other')),
  scheduled_at   timestamptz not null,
  caption        text not null default '' check (char_length(caption) <= 2200),
  status         text not null default 'planned' check (status in ('planned', 'posted', 'skipped')),
  posted_url     text check (char_length(posted_url) <= 2048),
  remind_minutes int not null default 30 check (remind_minutes between 0 and 10080),
  reminded_at    timestamptz,
  created_at     timestamptz not null default now()
);
create index schedule_items_user_time on public.schedule_items (user_id, scheduled_at);
create index schedule_items_due on public.schedule_items (scheduled_at) where status = 'planned' and reminded_at is null;
alter table public.schedule_items enable row level security;
create policy schedule_items_read on public.schedule_items for select to authenticated using (user_id = auth.uid());
grant select on public.schedule_items to authenticated;

-- Private calendar feed (subscribe from Google/Apple Calendar).
alter table public.members add column calendar_token text unique;

-- ======================================================================== 20261118000019_project_sharing.sql
-- Project sharing: invite specific people to a project as viewer (watch, download) or editor (change it).

create table public.project_members (
  project_id uuid not null references public.projects(id) on delete cascade,
  user_id    uuid not null references public.members(user_id) on delete cascade,
  role       text not null check (role in ('viewer', 'editor')),
  added_by   uuid references public.members(user_id) on delete set null,
  created_at timestamptz not null default now(),
  primary key (project_id, user_id)
);
create index project_members_user on public.project_members (user_id);
alter table public.project_members enable row level security;
create policy project_members_read on public.project_members for select to authenticated
  using (user_id = auth.uid() or exists (select 1 from public.projects p where p.id = project_id and p.created_by = auth.uid())
         or public.is_admin());
grant select on public.project_members to authenticated;   -- changes go through the API

-- Seeing a project now includes people it was shared with.
create or replace function public.can_view_project(pid uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from public.projects p left join public.members m on m.user_id = p.created_by
     where p.id = pid
       and (p.created_by = auth.uid() or public.is_admin() or (public.my_team() is not null and m.team is not null)
            or exists (select 1 from public.project_members pm where pm.project_id = pid and pm.user_id = auth.uid()))
  );
$$;

-- Changing it needs owner/admin/team rights, or an editor share.
create or replace function public.can_edit_project(pid uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from public.projects p left join public.members m on m.user_id = p.created_by
     where p.id = pid
       and (p.created_by = auth.uid() or public.is_admin() or (public.my_team() is not null and m.team is not null)
            or exists (select 1 from public.project_members pm
                        where pm.project_id = pid and pm.user_id = auth.uid() and pm.role = 'editor'))
  );
$$;

drop policy projects_update on public.projects;
create policy projects_update on public.projects for update to authenticated
  using (public.can_edit_project(id)) with check (public.can_edit_project(id));
drop policy clips_update on public.clips;
create policy clips_update on public.clips for update to authenticated
  using (public.can_edit_project(project_id)) with check (public.can_edit_project(project_id));
drop policy stories_update on public.stories;
create policy stories_update on public.stories for update to authenticated
  using (public.can_edit_project(project_id)) with check (public.can_edit_project(project_id));
drop policy scenes_insert on public.scenes;
drop policy scenes_update on public.scenes;
drop policy scenes_delete on public.scenes;
create policy scenes_insert on public.scenes for insert to authenticated with check (public.can_edit_project(project_id));
create policy scenes_update on public.scenes for update to authenticated
  using (public.can_edit_project(project_id)) with check (public.can_edit_project(project_id));
create policy scenes_delete on public.scenes for delete to authenticated using (public.can_edit_project(project_id));
drop policy characters_update on public.characters;
drop policy characters_delete on public.characters;
create policy characters_update on public.characters for update to authenticated
  using (public.can_edit_project(project_id)) with check (public.can_edit_project(project_id));
create policy characters_delete on public.characters for delete to authenticated using (public.can_edit_project(project_id));

-- Collaboration is a Pro feature (and in Business and Team).
update public.plans set features = array_append(features, 'collaboration')
 where id in ('pro', 'business', 'team') and not ('collaboration' = any(features));

-- ======================================================================== 20261119000020_payments.sql
-- Online payments with Razorpay: plan subscriptions (month / year) and token packs, in INR.

-- Prices in whole rupees (the owner edits them in Admin → Payments). 0 = not sold online.
alter table public.plans add column price_inr_month integer not null default 0 check (price_inr_month >= 0);
alter table public.plans add column price_inr_year  integer not null default 0 check (price_inr_year >= 0);
update public.plans set price_inr_month = 1499, price_inr_year = 14990 where id = 'pro';
update public.plans set price_inr_month = 3999, price_inr_year = 39990 where id = 'business';

-- Why a plan has an end date: a promo trial or a paid period. When it ends the member goes back to
-- plan_before_trial (their plan before the trial/payment, usually Free).
alter table public.members add column plan_source text check (plan_source in ('trial', 'paid'));
update public.members set plan_source = 'trial' where plan_expires_at is not null;
alter table public.members add column renewal_reminded_at timestamptz;

-- Bonus-token packs sold online.
create table public.token_packs (
  id        text primary key,
  name      text not null,
  tokens    integer not null check (tokens > 0),
  price_inr integer not null check (price_inr > 0),
  active    boolean not null default true,
  sort      integer not null default 0
);
alter table public.token_packs enable row level security;
create policy token_packs_read on public.token_packs for select to anon, authenticated using (active);
grant select on public.token_packs to anon, authenticated;
insert into public.token_packs (id, name, tokens, price_inr, sort) values
  ('starter', 'Starter pack', 5000, 199, 1),
  ('creator', 'Creator pack', 25000, 799, 2),
  ('studio', 'Studio pack', 100000, 2499, 3);

-- One row per checkout. Fulfilment is idempotent: a payment is applied once, whichever of the browser
-- confirmation or the Razorpay webhook arrives first.
create table public.payments (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references public.members(user_id) on delete cascade,
  provider     text not null default 'razorpay',
  kind         text not null check (kind in ('plan', 'tokens')),
  item         jsonb not null,                  -- {plan_id, period} or {pack_id, tokens}
  description  text not null,
  amount       integer not null check (amount > 0),   -- smallest unit (paise)
  currency     text not null default 'INR',
  status       text not null default 'created' check (status in ('created', 'paid', 'failed', 'refunded')),
  order_id     text not null unique,
  payment_id   text unique,
  error        text,
  created_at   timestamptz not null default now(),
  paid_at      timestamptz,
  fulfilled_at timestamptz
);
create index payments_user on public.payments (user_id, created_at desc);
create index payments_paid on public.payments (paid_at desc) where status = 'paid';
alter table public.payments enable row level security;
create policy payments_read on public.payments for select to authenticated
  using (user_id = auth.uid() or public.is_admin());
grant select on public.payments to authenticated;   -- written only by the API

-- Razorpay keys set in the app (environment variables take precedence). Secrets are encrypted.
alter table public.settings add column razorpay_key_id text;
alter table public.settings add column razorpay_secret_enc text;
alter table public.settings add column razorpay_webhook_secret_enc text;

-- Record the migrations as applied (so the Supabase CLI won't re-run them later).
create schema if not exists supabase_migrations;
create table if not exists supabase_migrations.schema_migrations (version text primary key, statements text[], name text);
insert into supabase_migrations.schema_migrations (version, name) values ('20261115000001', 'core') on conflict do nothing;
insert into supabase_migrations.schema_migrations (version, name) values ('20261115000002', 'content') on conflict do nothing;
insert into supabase_migrations.schema_migrations (version, name) values ('20261115000003', 'seed_data') on conflict do nothing;
insert into supabase_migrations.schema_migrations (version, name) values ('20261115000004', 'scene_characters') on conflict do nothing;
insert into supabase_migrations.schema_migrations (version, name) values ('20261115000005', 'veo') on conflict do nothing;
insert into supabase_migrations.schema_migrations (version, name) values ('20261115000006', 'later_features') on conflict do nothing;
insert into supabase_migrations.schema_migrations (version, name) values ('20261116000007', 'business_accounts') on conflict do nothing;
insert into supabase_migrations.schema_migrations (version, name) values ('20261116000008', 'tokens') on conflict do nothing;
insert into supabase_migrations.schema_migrations (version, name) values ('20261116000009', 'notifications') on conflict do nothing;
insert into supabase_migrations.schema_migrations (version, name) values ('20261116000010', 'ai_providers') on conflict do nothing;
insert into supabase_migrations.schema_migrations (version, name) values ('20261116000011', 'quick_captions') on conflict do nothing;
insert into supabase_migrations.schema_migrations (version, name) values ('20261116000012', 'user_panel') on conflict do nothing;
insert into supabase_migrations.schema_migrations (version, name) values ('20261116000013', 'creator_extras') on conflict do nothing;
insert into supabase_migrations.schema_migrations (version, name) values ('20261117000014', 'growth') on conflict do nothing;
insert into supabase_migrations.schema_migrations (version, name) values ('20261117000015', 'editing') on conflict do nothing;
insert into supabase_migrations.schema_migrations (version, name) values ('20261117000016', 'repurpose') on conflict do nothing;
insert into supabase_migrations.schema_migrations (version, name) values ('20261117000017', 'developer_api') on conflict do nothing;
insert into supabase_migrations.schema_migrations (version, name) values ('20261118000018', 'calendar') on conflict do nothing;
insert into supabase_migrations.schema_migrations (version, name) values ('20261118000019', 'project_sharing') on conflict do nothing;
insert into supabase_migrations.schema_migrations (version, name) values ('20261119000020', 'payments') on conflict do nothing;

commit;
