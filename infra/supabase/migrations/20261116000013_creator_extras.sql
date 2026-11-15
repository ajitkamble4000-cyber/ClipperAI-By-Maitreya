-- Creator extras: templates (built-in ones have user_id null and are visible to everyone; saving your own
-- needs the Templates feature), AI thumbnails (covers) and title/hashtag ideas.

create index if not exists templates_user on public.templates (user_id, kind, created_at desc);

insert into public.templates (kind, name, settings, user_id) values
  ('clip', 'Podcast highlights', '{"mode":"clips","content_type":"podcast","reframe":"face","num_clips":5,"min_len":30,"max_len":60,"caption_style":{"preset":"bold_pop"},"hook_overlay":true}', null),
  ('clip', 'Gaming moments', '{"mode":"clips","content_type":"gaming","reframe":"action","num_clips":5,"min_len":15,"max_len":45,"caption_style":{"preset":"bold_pop","emoji":true},"hook_overlay":true}', null),
  ('clip', 'Sports highlights', '{"mode":"clips","content_type":"sports","reframe":"action","num_clips":5,"min_len":15,"max_len":40,"caption_style":{"preset":"boxed"},"hook_overlay":true}', null),
  ('clip', 'TikTok captions', '{"mode":"captions","reframe":"face","caption_style":{"preset":"karaoke"},"hook_overlay":false}', null),
  ('clip', 'Clean subtitles', '{"mode":"captions","reframe":"blur","caption_style":{"preset":"minimal","uppercase":false,"words_per_line":6},"hook_overlay":false}', null),
  ('clip', 'YouTube 16:9 (Pro)', '{"mode":"captions","aspect":"16:9","reframe":"center","caption_style":{"preset":"minimal","uppercase":false,"words_per_line":7},"hook_overlay":false,"remove_silence":true}', null),
  ('story', 'Scary story', '{"genre":"scary","visual_style":"dark_horror","length_s":45,"speaking_style":"creepy_whisper"}', null),
  ('story', 'Fun facts', '{"genre":"facts","visual_style":"realistic_3d","length_s":30,"speaking_style":"excited"}', null),
  ('story', 'Kids bedtime', '{"genre":"bedtime","visual_style":"pixar_3d","length_s":60,"speaking_style":"calm"}', null);

alter table public.clips   add column covers jsonb not null default '{}'::jsonb;  -- {"youtube": key, "vertical": key}
alter table public.clips   add column ideas  jsonb not null default '{}'::jsonb;  -- {"titles": [...], "hashtags": [...]}
alter table public.stories add column covers jsonb not null default '{}'::jsonb;
alter table public.stories add column ideas  jsonb not null default '{}'::jsonb;
