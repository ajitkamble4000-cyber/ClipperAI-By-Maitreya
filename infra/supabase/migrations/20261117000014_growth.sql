-- Growth: promo codes (bonus tokens or plan trials), referrals, and owner site controls.

-- ---------------------------------------------------------------- site controls (settings row id=1)
alter table public.settings add column signups_open boolean not null default true;
alter table public.settings add column jobs_paused boolean not null default false;
alter table public.settings add column maintenance_message text not null default ''
  check (char_length(maintenance_message) <= 300);
alter table public.settings add column referral_reward int not null default 500 check (referral_reward between 0 and 100000);
alter table public.settings add column referral_monthly_cap int not null default 20 check (referral_monthly_cap between 0 and 1000);

-- ---------------------------------------------------------------- plan trials
alter table public.members add column plan_expires_at timestamptz;   -- end of a trial plan
alter table public.members add column plan_before_trial text references public.plans(id);

-- ---------------------------------------------------------------- promo codes
create table public.promo_codes (
  code            text primary key check (code ~ '^[A-Z0-9_-]{3,32}$'),
  kind            text not null check (kind in ('tokens', 'trial')),
  tokens          int not null default 0 check (tokens between 0 and 1000000),
  plan_id         text references public.plans(id),
  trial_days      int check (trial_days between 1 and 365),
  max_redemptions int check (max_redemptions > 0),          -- null = unlimited
  redemptions     int not null default 0,
  expires_at      timestamptz,
  active          boolean not null default true,
  note            text not null default '' check (char_length(note) <= 200),
  created_by      uuid references public.members(user_id) on delete set null,
  created_at      timestamptz not null default now(),
  check ((kind = 'tokens' and tokens > 0) or (kind = 'trial' and plan_id is not null and trial_days is not null))
);
alter table public.promo_codes enable row level security;   -- API only (no grants)

create table public.promo_redemptions (
  code        text not null references public.promo_codes(code) on delete cascade,
  user_id     uuid not null references public.members(user_id) on delete cascade,
  redeemed_at timestamptz not null default now(),
  primary key (code, user_id)
);
alter table public.promo_redemptions enable row level security;
create policy promo_redemptions_read on public.promo_redemptions for select to authenticated using (user_id = auth.uid());
grant select on public.promo_redemptions to authenticated;

-- ---------------------------------------------------------------- referrals
alter table public.members add column referral_code text unique check (referral_code ~ '^[a-z0-9]{6,16}$');

create table public.referrals (
  referred_id  uuid primary key references public.members(user_id) on delete cascade,
  referrer_id  uuid not null references public.members(user_id) on delete cascade,
  status       text not null default 'pending' check (status in ('pending', 'rewarded', 'capped')),
  reward       int not null default 0,
  created_at   timestamptz not null default now(),
  rewarded_at  timestamptz,
  check (referred_id <> referrer_id)
);
create index referrals_referrer on public.referrals (referrer_id, created_at desc);
alter table public.referrals enable row level security;
create policy referrals_read on public.referrals for select to authenticated
  using (referrer_id = auth.uid() or referred_id = auth.uid() or public.is_admin());
grant select on public.referrals to authenticated;

-- ---------------------------------------------------------------- sign-up trigger: closed sign-ups + referrals
create or replace function public.accept_invite_on_signup() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  inv public.invites;
  open boolean;
  ref_code text;
  referrer uuid;
begin
  select * into inv from public.invites
   where lower(email) = lower(new.email) and accepted_at is null
   order by created_at desc limit 1;
  select coalesce(signups_open, true) into open from public.settings where id = 1;
  if open is false and inv.id is null then
    raise exception 'Sign-ups are closed right now' using errcode = 'P0001';
  end if;
  insert into public.members (user_id, email, role, team, plan_id, display_name)
  values (new.id, lower(new.email), coalesce(inv.role, 'user'), inv.team,
          coalesce(inv.plan_id, case when inv.team is not null then 'team' else 'free' end),
          nullif(left(trim(coalesce(new.raw_user_meta_data->>'display_name', '')), 80), ''))
  on conflict (user_id) do nothing;
  if inv.id is not null then
    update public.invites set accepted_at = now() where id = inv.id;
  end if;
  ref_code := lower(nullif(trim(coalesce(new.raw_user_meta_data->>'ref', '')), ''));
  if ref_code is not null then
    select user_id into referrer from public.members where referral_code = ref_code;
    if referrer is not null and referrer <> new.id then
      insert into public.referrals (referred_id, referrer_id) values (new.id, referrer) on conflict do nothing;
    end if;
  end if;
  return new;
end $$;
