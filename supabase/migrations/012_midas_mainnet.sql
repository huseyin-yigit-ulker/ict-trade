-- 012 — MIDAS mainnet unlock (2026-07-07): owner decision — MIDAS-X, AFTER-LOSS kapısı +
-- düşük sabit riskle ($3) XAUUSDT'yi Binance MAINNET'te işler. 004'teki midas_testnet_only
-- CHECK'i kapı-öncesi dönemden kalmaydı; kaldırılıyor. tg_uss_guard taban korumaları
-- (geçerli anahtar, bakiye %25 tavanı, one-way mod, universe) aynen geçerli. IDEMPOTENT.

alter table ict_trade.user_stream_settings drop constraint if exists midas_testnet_only;

notify pgrst, 'reload schema';
