-- Repurpose: AI write-ups from a video, and a searchable transcript index ("search what was said").

alter table public.projects add column repurpose jsonb not null default '{}'::jsonb;

create table public.project_transcripts (
  project_id  uuid primary key references public.projects(id) on delete cascade,
  language    text,
  text        text not null default '',
  segments    jsonb not null default '[]'::jsonb,   -- [{start, end, text}]
  tsv         tsvector generated always as (to_tsvector('simple', coalesce(text, ''))) stored,
  updated_at  timestamptz not null default now()
);
create index project_transcripts_tsv on public.project_transcripts using gin (tsv);
alter table public.project_transcripts enable row level security;   -- searched through the API (access checked)

insert into public.token_prices (action, label, tokens, unit, description, sort) values
  ('repurpose', 'Repurpose a video', 25, 'video', 'Summary, chapters, quotes, blog post, thread, LinkedIn post, newsletter', 22)
on conflict (action) do nothing;
