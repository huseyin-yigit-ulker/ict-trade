-- 020 — user_signal_watch: ÖLÜ stratejilerin izleme satırlarını temizle (2026-07-14).
--
-- Neden: sync/push_notify.py _watchlist_user_ids() "cardinality(symbols) > 0 olan HERKES"i
-- broadcast'ten düşürür (hedefli push alacakları varsayımıyla). Ama d30so8f3vg (FABLE,
-- emekli 2026-07-07) ve midas (SIRIUS, backtest-only 2026-07-13) artık HİÇ sinyal emit
-- etmiyor -> bu satırların sahipleri broadcast de hedefli push da almıyor (sessiz kayıp).
-- CHECK kısıtı 015 ile zaten ('d30so8f3h7','d30so8f3vg','midas','talos','talos_ichi');
-- kısıta DOKUNULMAZ — yalnız ölü veriyi sil.
--
-- IDEMPOTENT. apply: python sync/users/apply_sql.py --file supabase/migrations/020_signal_watch_cleanup.sql

delete from ict_trade.user_signal_watch where strategy in ('d30so8f3vg', 'midas');

notify pgrst, 'reload schema';
