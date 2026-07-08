-- 015 — TALOS-ICHI (araştırma/PAPER akışı, 2026-07-08): sinyal-izleme domain'i + evren satırı.
--
-- TALOS-ICHI = TALOS Keltner-trend + Ichimoku Kumo-rengi yön filtresi (mode='talos_ichi' canlı
-- paper sinyal + version='talos_ichi' backtest). Executor'u YOK — user_stream_settings CHECK'ine
-- (opus/midas) DOKUNULMAZ; yalnız:
--   * user_signal_watch.strategy CHECK'ine 'talos_ichi' eklenir (kişisel push izleme listesi)
--   * stream_universe'e (talos_ichi, XAUUSDT) satırı eklenir (izleme kartının sembol listesi)
--
-- IDEMPOTENT. apply: python sync/users/apply_sql.py --file supabase/migrations/015_talos_ichi_stream.sql

alter table ict_trade.user_signal_watch
  drop constraint if exists user_signal_watch_strategy_check;
alter table ict_trade.user_signal_watch
  add constraint user_signal_watch_strategy_check
  check (strategy in ('d30so8f3h7','d30so8f3vg','midas','talos','talos_ichi'));

insert into ict_trade.stream_universe (stream, symbol)
  values ('talos_ichi', 'XAUUSDT')
  on conflict do nothing;

notify pgrst, 'reload schema';
