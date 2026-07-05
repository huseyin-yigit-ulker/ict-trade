-- 007 — Phase-6 tightening: executor state tables become user-private.
--
-- ⚠️ Apply ONLY AFTER the frontend reads /binance, /binance-altin and push.js through
--    the user JWT (authedFetch) — applying earlier 401s those pages for everyone.
--    The VM executors connect as table owner and bypass RLS: unaffected.
-- IDEMPOTENT.

alter table ict_trade.live_positions        enable row level security;
alter table ict_trade.midas_positions       enable row level security;
alter table ict_trade.live_account          enable row level security;
alter table ict_trade.live_account_snapshot enable row level security;
alter table ict_trade.live_orders           enable row level security;
alter table ict_trade.midas_orders          enable row level security;

revoke select on ict_trade.live_positions        from anon;
revoke select on ict_trade.midas_positions       from anon;
revoke select on ict_trade.live_account          from anon;
revoke select on ict_trade.live_account_snapshot from anon;

grant select on ict_trade.live_positions, ict_trade.midas_positions,
                ict_trade.live_account, ict_trade.live_account_snapshot to authenticated;

drop policy if exists lp_select_own on ict_trade.live_positions;
create policy lp_select_own on ict_trade.live_positions for select to authenticated
  using (user_id = auth.uid() or ict_trade.is_admin());

drop policy if exists mp_select_own on ict_trade.midas_positions;
create policy mp_select_own on ict_trade.midas_positions for select to authenticated
  using (user_id = auth.uid() or ict_trade.is_admin());

drop policy if exists la_select_own on ict_trade.live_account;
create policy la_select_own on ict_trade.live_account for select to authenticated
  using (user_id = auth.uid() or ict_trade.is_admin());

drop policy if exists las_select_own on ict_trade.live_account_snapshot;
create policy las_select_own on ict_trade.live_account_snapshot for select to authenticated
  using (user_id = auth.uid() or ict_trade.is_admin());

-- push_subscriptions: retire the legacy anon path (frontend now sends the JWT).
drop policy if exists push_sub_insert on ict_trade.push_subscriptions;
drop policy if exists push_sub_delete on ict_trade.push_subscriptions;
revoke insert, delete on ict_trade.push_subscriptions from anon;

-- signals / trading_signals / stream_universe stay anon-readable (central, public).

notify pgrst, 'reload schema';
