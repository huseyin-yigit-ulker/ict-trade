-- 006 — per-user Web Push: push_subscriptions gains user_id (authenticated RLS) and
-- push_outbox is the executor→user personal-notification queue (entry/TP1/SL/key events).
-- Clients have NO grants on push_outbox: executors insert, sync/push_notify.py drains —
-- both over the owner DSN.
--
-- The legacy anon insert/delete policies on push_subscriptions stay until Phase 6
-- (frontend switches push.js to the JWT) — 007_rls_tighten.sql drops them.
-- IDEMPOTENT.

alter table ict_trade.push_subscriptions add column if not exists user_id uuid;

grant select, insert, delete on ict_trade.push_subscriptions to authenticated;

drop policy if exists push_sub_insert_auth on ict_trade.push_subscriptions;
create policy push_sub_insert_auth on ict_trade.push_subscriptions
  for insert to authenticated with check (user_id = auth.uid());

drop policy if exists push_sub_delete_auth on ict_trade.push_subscriptions;
create policy push_sub_delete_auth on ict_trade.push_subscriptions
  for delete to authenticated using (user_id = auth.uid());

drop policy if exists push_sub_select_auth on ict_trade.push_subscriptions;
create policy push_sub_select_auth on ict_trade.push_subscriptions
  for select to authenticated using (user_id = auth.uid());

-- ------------------------------------------------------------------ push_outbox
create table if not exists ict_trade.push_outbox (
  id         bigint generated always as identity primary key,
  user_id    uuid not null,
  payload    jsonb not null,        -- {title, body, tag?, url?}
  created_at timestamptz not null default now(),
  sent_at    timestamptz
);

create index if not exists push_outbox_unsent_idx
  on ict_trade.push_outbox (created_at) where sent_at is null;

alter table ict_trade.push_outbox enable row level security;
-- no client grants on purpose: VM-only queue.

notify pgrst, 'reload schema';
