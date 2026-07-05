-- 005b — CUTOVER half: act-once / one-open / snapshot keys become PER (user, network).
--
-- ⚠️ Run ONLY inside the Phase-5 halt window (LIVE_TRADING_ENABLED=false), AFTER
--    `sync/users/seed_owner.py --backfill` stamped user_id+network on every existing row.
--    Swapping unique indexes under the running reconciler is the one thing this plan
--    never does.
--
-- NULLS NOT DISTINCT keeps the legacy/rollback path (user_id NULL inserts) deduplicating
-- exactly as before — without it, NULL user_id rows would never conflict and a rollback
-- executor could double-enter. (Postgres 15+, which Supabase runs.)
-- IDEMPOTENT.

-- ---------------------------------------------------------------- live_positions (OPUS)
drop index if exists ict_trade.uq_live_positions_key;
create unique index if not exists uq_live_positions_key
  on ict_trade.live_positions (user_id, network, symbol, signal_time, direction, version)
  nulls not distinct;

drop index if exists ict_trade.uq_live_positions_open_symbol;
create unique index if not exists uq_live_positions_open_symbol
  on ict_trade.live_positions (user_id, network, symbol)
  nulls not distinct
  where state in ('PENDING_ENTRY','ENTRY_WORKING','OPEN_FULL','RUNNER','CLOSING');

create index if not exists live_positions_user_idx on ict_trade.live_positions (user_id, state);

-- ---------------------------------------------------------------- midas_positions
drop index if exists ict_trade.uq_midas_positions_key;
create unique index if not exists uq_midas_positions_key
  on ict_trade.midas_positions (user_id, network, symbol, signal_time, direction, version)
  nulls not distinct;

drop index if exists ict_trade.uq_midas_positions_open_symbol;
create unique index if not exists uq_midas_positions_open_symbol
  on ict_trade.midas_positions (user_id, network, symbol)
  nulls not distinct
  where state in ('PENDING_ENTRY','ENTRY_WORKING','OPEN');

create index if not exists midas_positions_user_idx on ict_trade.midas_positions (user_id, state);

-- ---------------------------------------------------------------- account snapshots
-- PKs move from (network)/(symbol) to per-user composites. Existing rows are already
-- backfilled, so the new PKs are satisfiable. user_id must be NOT NULL for a PK —
-- backfill guarantees it; keep a guard anyway.
do $$
begin
  if exists (select 1 from ict_trade.live_account where user_id is null)
     or exists (select 1 from ict_trade.live_account_snapshot where user_id is null) then
    raise exception 'live_account(_snapshot) still has user_id NULL rows — run seed_owner.py --backfill first';
  end if;
end $$;

alter table ict_trade.live_account alter column user_id set not null;
alter table ict_trade.live_account drop constraint if exists live_account_pkey;
alter table ict_trade.live_account add primary key (user_id, network);

alter table ict_trade.live_account_snapshot alter column user_id set not null;
alter table ict_trade.live_account_snapshot alter column network set not null;
alter table ict_trade.live_account_snapshot drop constraint if exists live_account_snapshot_pkey;
alter table ict_trade.live_account_snapshot add primary key (user_id, network, symbol);

notify pgrst, 'reload schema';
