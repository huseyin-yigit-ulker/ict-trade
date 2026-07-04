-- PUSU Web Push subscriptions (live Supabase project, schema ict_trade).
-- The dashboard (src/utils/push.js) INSERTs a browser's PushSubscription here; the
-- VM sender (sync/push_notify.py) reads it over a direct Postgres connection
-- (bypasses RLS) to fan out notifications, and deletes dead endpoints.
--
-- Apply once in the Supabase SQL editor (live project).

create table if not exists ict_trade.push_subscriptions (
  id          bigint generated always as identity primary key,
  endpoint    text not null unique,          -- the browser's push endpoint URL
  p256dh      text not null,                 -- subscription public key (base64url)
  auth        text not null,                 -- subscription auth secret (base64url)
  label       text,                          -- UA string / device hint (optional)
  created_at  timestamptz not null default now()
);

alter table ict_trade.push_subscriptions enable row level security;

-- Mirror the existing anon-key model: the browser may register (INSERT / upsert)
-- and unsubscribe (DELETE by its own endpoint). No anon SELECT — only the VM,
-- connecting as the table owner, reads subscriptions to send pushes.
drop policy if exists push_sub_insert on ict_trade.push_subscriptions;
create policy push_sub_insert on ict_trade.push_subscriptions
  for insert to anon with check (true);

drop policy if exists push_sub_delete on ict_trade.push_subscriptions;
create policy push_sub_delete on ict_trade.push_subscriptions
  for delete to anon using (true);
