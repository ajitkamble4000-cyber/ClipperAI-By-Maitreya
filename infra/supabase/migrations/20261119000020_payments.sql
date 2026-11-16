-- Online payments with Razorpay: plan subscriptions (month / year) and token packs, in INR.

-- Prices in whole rupees (the owner edits them in Admin → Payments). 0 = not sold online.
alter table public.plans add column price_inr_month integer not null default 0 check (price_inr_month >= 0);
alter table public.plans add column price_inr_year  integer not null default 0 check (price_inr_year >= 0);
update public.plans set price_inr_month = 1499, price_inr_year = 14990 where id = 'pro';
update public.plans set price_inr_month = 3999, price_inr_year = 39990 where id = 'business';

-- Why a plan has an end date: a promo trial or a paid period. When it ends the member goes back to
-- plan_before_trial (their plan before the trial/payment, usually Free).
alter table public.members add column plan_source text check (plan_source in ('trial', 'paid'));
update public.members set plan_source = 'trial' where plan_expires_at is not null;
alter table public.members add column renewal_reminded_at timestamptz;

-- Bonus-token packs sold online.
create table public.token_packs (
  id        text primary key,
  name      text not null,
  tokens    integer not null check (tokens > 0),
  price_inr integer not null check (price_inr > 0),
  active    boolean not null default true,
  sort      integer not null default 0
);
alter table public.token_packs enable row level security;
create policy token_packs_read on public.token_packs for select to anon, authenticated using (active);
grant select on public.token_packs to anon, authenticated;
insert into public.token_packs (id, name, tokens, price_inr, sort) values
  ('starter', 'Starter pack', 5000, 199, 1),
  ('creator', 'Creator pack', 25000, 799, 2),
  ('studio', 'Studio pack', 100000, 2499, 3);

-- One row per checkout. Fulfilment is idempotent: a payment is applied once, whichever of the browser
-- confirmation or the Razorpay webhook arrives first.
create table public.payments (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references public.members(user_id) on delete cascade,
  provider     text not null default 'razorpay',
  kind         text not null check (kind in ('plan', 'tokens')),
  item         jsonb not null,                  -- {plan_id, period} or {pack_id, tokens}
  description  text not null,
  amount       integer not null check (amount > 0),   -- smallest unit (paise)
  currency     text not null default 'INR',
  status       text not null default 'created' check (status in ('created', 'paid', 'failed', 'refunded')),
  order_id     text not null unique,
  payment_id   text unique,
  error        text,
  created_at   timestamptz not null default now(),
  paid_at      timestamptz,
  fulfilled_at timestamptz
);
create index payments_user on public.payments (user_id, created_at desc);
create index payments_paid on public.payments (paid_at desc) where status = 'paid';
alter table public.payments enable row level security;
create policy payments_read on public.payments for select to authenticated
  using (user_id = auth.uid() or public.is_admin());
grant select on public.payments to authenticated;   -- written only by the API

-- Razorpay keys set in the app (environment variables take precedence). Secrets are encrypted.
alter table public.settings add column razorpay_key_id text;
alter table public.settings add column razorpay_secret_enc text;
alter table public.settings add column razorpay_webhook_secret_enc text;
