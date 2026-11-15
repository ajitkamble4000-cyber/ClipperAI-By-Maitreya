-- Which recurring characters appear in each scene (drives reference images for consistency).
alter table public.scenes add column characters text[] not null default '{}';
grant update (characters) on public.scenes to authenticated;
grant insert (characters) on public.scenes to authenticated;
