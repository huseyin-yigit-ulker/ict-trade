-- 016 — TALOS-ICHI-X MAINNET (gerçek-para) executor (2026-07-08): user_stream_settings + owner satırı.
--
-- Kullanıcı kararı (soru-cevap teyitli): TALOS-ICHI (Ichimoku Kumo yön filtreli TALOS, tam doğrulama
-- bataryasını geçti) canlı gerçek-paraya alındı; MIDAS-X emekli edildi (XAUUSDT'yi tek executor
-- sahiplenir — Binance hesap-başına tek net pozisyon kuralı). sync/talos_ichi_exec/ = MIDAS-X'in
-- birebir kardeşi (kendi talos_ichi_positions/talos_ichi_orders tablolarıyla, mode='talos_ichi').
-- Bunun için:
--   * user_stream_settings.stream CHECK'ine 'talos_ichi' eklenir
--   * MAINNET kilidi KONMAZ (MIDAS'ın 012'de kaldırdığı gibi — gerçek-para bilinçli olarak açık)
--   * owner'a (talos_ichi, mainnet) enabled satırı açılır ($3 risk, 1 eşzamanlı — MIDAS-X'ten devir)
-- ⚠️ FX-maliyet modeli: çok-yıl taker OOS negatif (2026-rejim riski); $3 küçük risk, kitabı izle.
--
-- IDEMPOTENT. apply: python sync/users/apply_sql.py --file supabase/migrations/016_talos_ichi_exec.sql

alter table ict_trade.user_stream_settings
  drop constraint if exists user_stream_settings_stream_check;
alter table ict_trade.user_stream_settings
  add constraint user_stream_settings_stream_check
  check (stream in ('opus','midas','talos','talos_ichi'));

-- MAINNET kilidi YOK (talos_ichi_testnet_only eklenmez) — gerçek-para açık. Eski bir kilit varsa düşür.
alter table ict_trade.user_stream_settings
  drop constraint if exists talos_ichi_testnet_only;

-- owner satırı (kanonik admin): MAINNET, $3 risk, tek pozisyon. tg_uss_guard enable'ı geçerli
-- mainnet anahtarına + bakiyeye karşı doğrular; satır varsa dokunma.
insert into ict_trade.user_stream_settings
  (user_id, stream, network, enabled, risk_usd, max_concurrent, max_total_risk_usd, symbols)
select p.user_id, 'talos_ichi', 'mainnet', true, 3, 1, 25, '{XAUUSDT}'
  from ict_trade.profiles p
 where p.role = 'admin'
 order by p.created_at
 limit 1
on conflict (user_id, stream, network) do nothing;

notify pgrst, 'reload schema';
