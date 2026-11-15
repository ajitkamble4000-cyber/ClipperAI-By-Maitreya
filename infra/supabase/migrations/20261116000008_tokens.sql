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
