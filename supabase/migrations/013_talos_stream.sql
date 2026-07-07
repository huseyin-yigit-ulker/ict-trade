-- 013 — TALOS (3. canlı PAPER akışı, 2026-07-07): sinyal-izleme domain'i + evren satırı.
--
-- TALOS = altın Keltner-trend paper akışı (mode='talos' canlı sinyal + version='talos' backtest).
-- Executor'u YOK — user_stream_settings CHECK'ine (opus/midas) DOKUNULMAZ; yalnız:
--   * user_signal_watch.strategy CHECK'ine 'talos' eklenir (kişisel sinyal push izleme listesi)
--   * stream_universe'e (talos, XAUUSDT) satırı eklenir (izleme kartının sembol listesi)
--
-- IDEMPOTENT. apply: python sync/users/apply_sql.py --file supabase/migrations/013_talos_stream.sql

alter table ict_trade.user_signal_watch
  drop constraint if exists user_signal_watch_strategy_check;
alter table ict_trade.user_signal_watch
  add constraint user_signal_watch_strategy_check
  check (strategy in ('d30so8f3h7','d30so8f3vg','midas','talos'));

insert into ict_trade.stream_universe (stream, symbol)
  values ('talos', 'XAUUSDT')
  on conflict do nothing;

notify pgrst, 'reload schema';
