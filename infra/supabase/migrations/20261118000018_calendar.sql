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
