-- 005a — ADDITIVE half of the executor user-scoping migration. Safe to apply while the
-- single-user executor is ARMED and running: nullable columns are invisible to it.
-- The index/PK swaps live in 005b and run ONLY inside the Phase-5 halt window,
-- after `seed_owner.py --backfill` has stamped every existing row with the owner.
-- IDEMPOTENT.

alter table ict_trade.live_positions        add column if not exists user_id uuid;
alter table ict_trade.live_positions        add column if not exists network text;
alter table ict_trade.live_orders           add column if not exists user_id uuid;
alter table ict_trade.midas_positions       add column if not exists user_id uuid;
alter table ict_trade.midas_positions       add column if not exists network text;
alter table ict_trade.midas_orders          add column if not exists user_id uuid;
alter table ict_trade.live_account          add column if not exists user_id uuid;
alter table ict_trade.live_account_snapshot add column if not exists user_id uuid;
alter table ict_trade.live_account_snapshot add column if not exists network text;

notify pgrst, 'reload schema';
