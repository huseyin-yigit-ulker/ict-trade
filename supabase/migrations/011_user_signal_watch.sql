-- 011 — ict_trade.user_signal_watch: per-user SIGNAL push watchlist (2026-07-05).
--
-- "Bir sinyal, seçtiğim strateji+sembolde oluşursa telefon bildirimi gelsin."
-- Bu tablo YALNIZCA telefon-push fan-out'unu yönlendirir; execution'la ilgisizdir:
--   * notify_signals = false            -> hiç sinyal push'u yok
--   * notify_signals = true, 0 satır    -> TÜM sinyaller (eski broadcast, değişmez)
--   * notify_signals = true, >=1 sembol  -> YALNIZ seçilen (strateji, sembol) çiftleri
--
-- user_stream_settings (EXECUTION seçimi, sadece opus/midas) ve stream_universe
-- (işlem-görülebilir whitelist) tablolarından AYRIDIR. `strategy` = anonim akış KEY'i
-- (version); sync/push_notify.py sinyalin mode'unu bu key'e çevirip eşler. Yalnız 3
-- CANLI akış sinyal ürettiği için domain bu üçüdür (streamMask.LIVE_STREAM_KEYS).
--
-- IDEMPOTENT. apply_sql.py --file supabase/migrations/011_user_signal_watch.sql

create table if not exists ict_trade.user_signal_watch (
  user_id    uuid not null references ict_trade.profiles(user_id) on delete cascade,
  strategy   text not null check (strategy in ('d30so8f3h7','d30so8f3vg','midas')),
  symbols    text[] not null default '{}',
  updated_at timestamptz not null default now(),
  primary key (user_id, strategy)
);

alter table ict_trade.user_signal_watch enable row level security;
grant select, insert, update, delete on ict_trade.user_signal_watch to authenticated;

-- Kullanıcı yalnız kendi satırlarını görür/yazar; admin hepsini (destek için).
drop policy if exists usw_own on ict_trade.user_signal_watch;
create policy usw_own on ict_trade.user_signal_watch for all to authenticated
  using (user_id = auth.uid() or ict_trade.is_admin())
  with check (user_id = auth.uid() or ict_trade.is_admin());

notify pgrst, 'reload schema';
