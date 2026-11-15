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
