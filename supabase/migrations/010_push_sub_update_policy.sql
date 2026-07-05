-- 010 — push_subscriptions UPDATE path (2026-07-05): push.js upserts subscriptions
-- with `on_conflict=endpoint` + `resolution=merge-duplicates`. When the endpoint row
-- already exists (same device re-subscribing, or a legacy user_id=NULL row from the
-- old anon path) PostgREST performs an UPDATE — but 006/007 created only INSERT/DELETE/
-- SELECT policies and no UPDATE grant, so RLS silently DENIED the update and the client
-- surfaced a generic "Bildirim ayarlanamadı". Grant UPDATE + add the owner-scoped policy.
--
-- IDEMPOTENT. apply_sql.py --file supabase/migrations/010_push_sub_update_policy.sql

grant update on ict_trade.push_subscriptions to authenticated;

drop policy if exists push_sub_update_auth on ict_trade.push_subscriptions;
create policy push_sub_update_auth on ict_trade.push_subscriptions
  for update to authenticated
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

notify pgrst, 'reload schema';
