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
