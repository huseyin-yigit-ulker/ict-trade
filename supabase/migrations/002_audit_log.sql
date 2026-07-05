-- 002 — ict_trade.audit_log + the generic row-change audit trigger + admin_set_user RPC.
-- Every security-relevant mutation (key submit/rotate/verify, settings change, kill,
-- admin action) lands here. Users see their own trail; admins see everything.
-- IDEMPOTENT.

create table if not exists ict_trade.audit_log (
  id         bigint generated always as identity primary key,
  user_id    uuid,                 -- whose account/settings the action concerns
  actor      uuid,                 -- who did it (auth.uid(); NULL = VM/system)
  action     text not null,        -- key_rotated|key_verified|user_stream_settings_update|admin_set_user|kill_requested|...
  detail     jsonb,
  created_at timestamptz not null default now()
);

create index if not exists audit_log_user_idx on ict_trade.audit_log (user_id, created_at desc);

alter table ict_trade.audit_log enable row level security;
grant select, insert on ict_trade.audit_log to authenticated;

drop policy if exists audit_select on ict_trade.audit_log;
create policy audit_select on ict_trade.audit_log for select to authenticated
  using (user_id = auth.uid() or ict_trade.is_admin());

drop policy if exists audit_insert on ict_trade.audit_log;
create policy audit_insert on ict_trade.audit_log for insert to authenticated
  with check (actor = auth.uid());

-- Generic audit trigger for the user-settings tables. Ciphertext columns are stripped
-- INSIDE the old/new objects so encrypted key material never reaches the audit trail.
create or replace function ict_trade.tg_audit() returns trigger
language plpgsql security definer set search_path = ict_trade as $$
begin
  insert into ict_trade.audit_log (user_id, actor, action, detail)
  values (
    coalesce(new.user_id, old.user_id),
    auth.uid(),
    tg_table_name || '_' || lower(tg_op),
    jsonb_build_object(
      'old', to_jsonb(old) - 'api_key_enc' - 'api_secret_enc',
      'new', to_jsonb(new) - 'api_key_enc' - 'api_secret_enc'
    )
  );
  return coalesce(new, old);
end $$;

-- Admin actions go through this RPC — there is never a broad UPDATE grant on
-- profiles.role/status. Activation, disabling and (de)promoting all audit themselves.
create or replace function ict_trade.admin_set_user(p_user uuid, p_status text default null, p_role text default null)
returns void language plpgsql security definer set search_path = ict_trade as $$
begin
  if not ict_trade.is_admin() then
    raise exception 'forbidden';
  end if;
  if p_status is not null and p_status not in ('pending','active','disabled') then
    raise exception 'bad status %', p_status;
  end if;
  if p_role is not null and p_role not in ('user','admin') then
    raise exception 'bad role %', p_role;
  end if;
  update ict_trade.profiles
     set status = coalesce(p_status, status),
         role = coalesce(p_role, role),
         updated_at = now()
   where user_id = p_user;
  if not found then
    raise exception 'no such user';
  end if;
  insert into ict_trade.audit_log (user_id, actor, action, detail)
  values (p_user, auth.uid(), 'admin_set_user',
          jsonb_build_object('status', p_status, 'role', p_role));
end $$;

grant execute on function ict_trade.admin_set_user to authenticated;

notify pgrst, 'reload schema';
