-- 004 — ict_trade.user_stream_settings: per-user activation, risk, symbols, kill/drain,
-- plus ict_trade.stream_universe (the tradable-symbol whitelist per stream, seeded from
-- scaleout.SO_SYMBOLS by sync/users/apply_sql.py --seed-universe).
--
-- Client-side warnings are advisory; tg_uss_guard is the HARD floor:
--   * symbols must be inside the stream universe
--   * enabling requires a VALID key on that network
--   * risk_usd × max_concurrent must stay ≤ 25% of the last verified balance
--   * hedge-mode (position_mode_ok=false) accounts cannot enable
-- MIDAS is testnet-only by table CHECK (Binance taker fee kills the gold edge — see MIDAS.md).
-- IDEMPOTENT.

create table if not exists ict_trade.stream_universe (
  stream text not null,
  symbol text not null,
  primary key (stream, symbol)
);
grant select on ict_trade.stream_universe to anon, authenticated;

create table if not exists ict_trade.user_stream_settings (
  id                 bigint generated always as identity primary key,
  user_id            uuid not null references ict_trade.profiles(user_id) on delete cascade,
  stream             text not null check (stream in ('opus','midas')),
  network            text not null check (network in ('mainnet','testnet')),
  enabled            boolean not null default false,
  risk_usd           numeric not null default 5 check (risk_usd > 0 and risk_usd <= 1000),
  max_concurrent     integer not null default 5 check (max_concurrent between 1 and 10),
  max_total_risk_usd numeric not null default 25 check (max_total_risk_usd > 0),
  daily_loss_cap_usd numeric check (daily_loss_cap_usd is null or daily_loss_cap_usd > 0),
  symbols            text[] not null default '{}',
  kill_requested     boolean not null default false,  -- UI kill button; executor flattens + clears
  drain              boolean not null default false,  -- disable-with-open-positions: manage to flat
  updated_at         timestamptz not null default now(),
  unique (user_id, stream, network),
  constraint midas_testnet_only check (not (stream = 'midas' and network = 'mainnet'))
);

alter table ict_trade.user_stream_settings enable row level security;
grant select, insert, update on ict_trade.user_stream_settings to authenticated;

drop policy if exists uss_own on ict_trade.user_stream_settings;
create policy uss_own on ict_trade.user_stream_settings for all to authenticated
  using (user_id = auth.uid() or ict_trade.is_admin())
  with check (user_id = auth.uid() or ict_trade.is_admin());

create or replace function ict_trade.tg_uss_guard() returns trigger
language plpgsql security definer set search_path = ict_trade as $$
declare
  k record;
begin
  if exists (select 1 from unnest(new.symbols) s
             where not exists (select 1 from ict_trade.stream_universe u
                               where u.stream = new.stream and u.symbol = s)) then
    raise exception 'symbol outside % universe', new.stream;
  end if;
  if new.enabled then
    select balance_usdt, position_mode_ok into k
      from ict_trade.user_api_keys
     where user_id = new.user_id and network = new.network and status = 'valid'
     order by verified_at desc nulls last limit 1;
    if k is null then
      raise exception 'no verified % API key', new.network;
    end if;
    if k.position_mode_ok is false then
      raise exception 'account is in hedge mode — switch Binance Futures to one-way mode';
    end if;
    if k.balance_usdt is not null
       and new.risk_usd * new.max_concurrent > k.balance_usdt * 0.25 then
      raise exception 'risk %$ x % positions exceeds 25%% of balance (%$)',
        new.risk_usd, new.max_concurrent, round(k.balance_usdt, 2);
    end if;
  end if;
  new.updated_at := now();
  return new;
end $$;

drop trigger if exists uss_guard on ict_trade.user_stream_settings;
create trigger uss_guard before insert or update on ict_trade.user_stream_settings
  for each row execute function ict_trade.tg_uss_guard();

drop trigger if exists audit_uss on ict_trade.user_stream_settings;
create trigger audit_uss after insert or update on ict_trade.user_stream_settings
  for each row execute function ict_trade.tg_audit();

notify pgrst, 'reload schema';
