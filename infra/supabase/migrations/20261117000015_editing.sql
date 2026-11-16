-- Editing extras: compilations are priced; caption edits and exports reuse existing prices.
insert into public.token_prices (action, label, tokens, unit, description, sort) values
  ('compilation', 'Compilation', 20, 'video', 'Join several clips into one video', 21)
on conflict (action) do nothing;
