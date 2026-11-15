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
