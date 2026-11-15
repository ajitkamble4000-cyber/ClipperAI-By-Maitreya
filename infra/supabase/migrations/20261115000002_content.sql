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
