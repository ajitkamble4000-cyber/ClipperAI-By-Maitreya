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
