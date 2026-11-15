-- Veo long-running operations are persisted per scene so a restarted worker resumes polling
-- instead of paying for a second generation.
alter table public.scenes add column veo_operation text;
alter table public.scenes add column veo_error text;
alter table public.scenes add column veo_started_at timestamptz;
