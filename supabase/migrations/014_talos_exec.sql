-- 014 — TALOS-X testnet (paper) executor (2026-07-08): user_stream_settings domain'i + owner satırı.
--
-- TALOS artık Binance TESTNET'e gerçek emir gönderir (paper hesap; sync/talos_exec/ — MIDAS-X'in
-- birebir kopyası, kendi talos_positions/talos_orders tablolarıyla). Bunun için:
--   * user_stream_settings.stream CHECK'ine 'talos' eklenir
--   * talos'a MAINNET kilidi konur (talos_testnet_only — MIDAS'ın eski kilidinin talos kopyası;
--     TALOS FX-maliyet modelidir, Binance taker'da ölür → mainnet bilinçli olarak kapalı)
--   * owner'a (talos, testnet) enabled satırı açılır ($5 risk, 1 eşzamanlı — tg_uss_guard doğrular)
--
-- IDEMPOTENT. apply: python sync/users/apply_sql.py --file supabase/migrations/014_talos_exec.sql

alter table ict_trade.user_stream_settings
  drop constraint if exists user_stream_settings_stream_check;
alter table ict_trade.user_stream_settings
  add constraint user_stream_settings_stream_check
  check (stream in ('opus','midas','talos'));

alter table ict_trade.user_stream_settings
  drop constraint if exists talos_testnet_only;
alter table ict_trade.user_stream_settings
  add constraint talos_testnet_only
  check (not (stream = 'talos' and network = 'mainnet'));

-- owner satırı (kanonik admin): testnet, $5 risk, tek pozisyon. tg_uss_guard enable'ı
-- geçerli testnet anahtarına + bakiyeye karşı doğrular; satır varsa dokunma.
insert into ict_trade.user_stream_settings
  (user_id, stream, network, enabled, risk_usd, max_concurrent, max_total_risk_usd, symbols)
select p.user_id, 'talos', 'testnet', true, 5, 1, 25, '{XAUUSDT}'
  from ict_trade.profiles p
 where p.role = 'admin'
 order by p.created_at
 limit 1
on conflict (user_id, stream, network) do nothing;

notify pgrst, 'reload schema';
