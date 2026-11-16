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
