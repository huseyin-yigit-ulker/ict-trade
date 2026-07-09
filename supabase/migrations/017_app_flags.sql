-- 017 — global uygulama bayrakları (2026-07-09): admin panelinden aç/kapa edilebilen
-- sistem anahtarları. İlk kullanan: 'positions_digest' — açık-işlem Telegram özeti cron'u
-- (sync/positions_digest.py, dag/crontab */5). Cron VM crontab'ında sabittir; web'den satır
-- silinemez, bunun yerine cron her tetiklendiğinde bu bayrağı okur ve KAPALI ise sessizce
-- no-op yapar (executor kill_requested kalıbının aynısı).
--
--   * app_flags               — key/enabled tek-satır konfig; authenticated SELECT eder.
--   * admin_set_flag(key,bool)— yalnız admin; upsert + audit_log (admin_kill_all şablonu).
--
-- IDEMPOTENT. apply_sql.py --file ile (owner DSN) uygula.

create table if not exists ict_trade.app_flags (
  key        text primary key,
  enabled    boolean not null default true,
  updated_at timestamptz not null default now(),
  updated_by uuid
);

-- Varsayılan: açık-işlem özeti AÇIK (bugünkü davranışı korur).
insert into ict_trade.app_flags (key, enabled) values ('positions_digest', true)
  on conflict (key) do nothing;

-- RLS: herkes (authenticated) okuyabilir; yazma yalnız security-definer RPC üzerinden.
alter table ict_trade.app_flags enable row level security;
drop policy if exists app_flags_read on ict_trade.app_flags;
create policy app_flags_read on ict_trade.app_flags
  for select to authenticated using (true);
grant select on ict_trade.app_flags to authenticated;

-- ---------------------------------------------------------------- admin toggle
create or replace function ict_trade.admin_set_flag(p_key text, p_enabled boolean)
returns boolean language plpgsql security definer set search_path = ict_trade as $$
begin
  if not ict_trade.is_admin() then raise exception 'forbidden'; end if;
  if coalesce(length(trim(p_key)), 0) = 0 then raise exception 'empty key'; end if;
  insert into ict_trade.app_flags (key, enabled, updated_at, updated_by)
  values (p_key, p_enabled, now(), auth.uid())
  on conflict (key) do update
    set enabled = excluded.enabled, updated_at = now(), updated_by = auth.uid();
  insert into ict_trade.audit_log (user_id, actor, action, detail)
  values (null, auth.uid(), 'admin_set_flag',
          jsonb_build_object('key', p_key, 'enabled', p_enabled));
  return p_enabled;
end $$;
grant execute on function ict_trade.admin_set_flag to authenticated;

notify pgrst, 'reload schema';
