-- 001 — ict_trade.profiles: the app-user registry on top of Supabase Auth (GoTrue).
-- Signup flow is ADMIN-APPROVED: every new auth.users row auto-creates a 'pending'
-- profile via trigger; an admin activates it from the /admin panel (admin_set_user RPC,
-- defined in 002 because it writes to audit_log).
--
-- IDEMPOTENT. Apply via sync/users/apply_sql.py (owner DSN) or the Supabase SQL editor
-- (live project). NOTE: the trigger on auth.users needs the postgres role; if the pooler
-- DSN user lacks it, run this one file in the SQL editor instead.

create table if not exists ict_trade.profiles (
  user_id      uuid primary key references auth.users(id) on delete cascade,
  email        text not null,
  display_name text,
  role         text not null default 'user'    check (role in ('user','admin')),
  status       text not null default 'pending' check (status in ('pending','active','disabled')),
  is_canonical boolean not null default false,  -- owner only: executor writeback → trading_signals
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

-- Auto-create a pending profile the moment GoTrue registers a user.
create or replace function ict_trade.handle_new_user() returns trigger
language plpgsql security definer set search_path = ict_trade as $$
begin
  insert into ict_trade.profiles (user_id, email, display_name)
  values (new.id, coalesce(new.email, ''), split_part(coalesce(new.email, ''), '@', 1))
  on conflict (user_id) do nothing;
  return new;
end $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function ict_trade.handle_new_user();

-- Non-recursive admin check: security definer so profiles' own RLS can call it
-- without self-referencing (the classic recursive-policy trap).
create or replace function ict_trade.is_admin() returns boolean
language sql stable security definer set search_path = ict_trade as
$$ select exists (select 1 from ict_trade.profiles
                  where user_id = auth.uid() and role = 'admin' and status = 'active') $$;

alter table ict_trade.profiles enable row level security;

grant usage on schema ict_trade to authenticated;
grant select on ict_trade.profiles to authenticated;
-- column-level: users may edit their display name, NEVER role/status/is_canonical.
grant update (display_name) on ict_trade.profiles to authenticated;

drop policy if exists profiles_select_own on ict_trade.profiles;
create policy profiles_select_own on ict_trade.profiles for select to authenticated
  using (user_id = auth.uid() or ict_trade.is_admin());

drop policy if exists profiles_update_own on ict_trade.profiles;
create policy profiles_update_own on ict_trade.profiles for update to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());

notify pgrst, 'reload schema';
