-- 009 — admin araç seti (2026-07-05): /admin modülünün RPC katmanı.
--
--   * admin_list_users()    — profiles ⋈ auth.users (e-posta onayı + son giriş) — sadece admin.
--   * admin_confirm_email() — kullanıcının e-postasını sunucu tarafında onaylar (dashboard'sız).
--   * admin_notify()        — tek kullanıcıya veya TÜM aktif kullanıcılara push duyurusu
--                             (push_outbox kuyruğu; mevcut --drain cron'u dağıtır).
--   * admin_kill_all()      — global acil durdurma: tüm enabled akışlarda kill_requested=true.
--   * admin_user_stats()    — kullanıcı başına açık pozisyon + bugün/toplam realized $.
--   * admin_overview()      — sistem sağlık özeti (kullanıcı sayıları, executor kalp atışı,
--                             son sinyal, son anahtar doğrulaması, bekleyen outbox).
--   * tg_uss_guard FİXİ     — arming-doğrulaması (geçerli anahtar / bakiye / hedge) yalnız
--                             enable veya risk/sembol DEĞİŞİMİNDE koşar; kill_requested gibi
--                             ilgisiz flag güncellemeleri asla bloklanamaz (kill her zaman geçer).
--
-- IDEMPOTENT. apply_sql.py --file ile (owner DSN) uygula.

-- ---------------------------------------------------------------- guard fix
create or replace function ict_trade.tg_uss_guard() returns trigger
language plpgsql security definer set search_path = ict_trade as $$
declare
  k record;
  arming boolean;
begin
  if exists (select 1 from unnest(new.symbols) s
             where not exists (select 1 from ict_trade.stream_universe u
                               where u.stream = new.stream and u.symbol = s)) then
    raise exception 'symbol outside % universe', new.stream;
  end if;
  -- Yalnız ARM anında (enable geçişi) veya risk/sembol/ağ değişiminde doğrula; kill_requested /
  -- drain gibi flag güncellemeleri hiçbir koşulda bloklanmaz (acil durdurma her zaman geçmeli).
  arming := new.enabled and (
    tg_op = 'INSERT'
    or old.enabled is distinct from new.enabled
    or old.risk_usd is distinct from new.risk_usd
    or old.max_concurrent is distinct from new.max_concurrent
    or old.symbols is distinct from new.symbols
    or old.network is distinct from new.network
  );
  if arming then
    select balance_usdt, position_mode_ok into k
      from ict_trade.user_api_keys
     where user_id = new.user_id and network = new.network and status = 'valid'
     order by verified_at desc nulls last limit 1;
    if k is null then
      raise exception 'no verified % API key', new.network;
    end if;
    if k.position_mode_ok is false then
      raise exception 'account is in hedge mode — switch Binance Futures to one-way mode';
    end if;
    if k.balance_usdt is not null
       and new.risk_usd * new.max_concurrent > k.balance_usdt * 0.25 then
      raise exception 'risk %$ x % positions exceeds 25%% of balance (%$)',
        new.risk_usd, new.max_concurrent, round(k.balance_usdt, 2);
    end if;
  end if;
  new.updated_at := now();
  return new;
end $$;

-- ---------------------------------------------------------------- list users (+auth meta)
create or replace function ict_trade.admin_list_users()
returns table (
  user_id uuid, email text, display_name text, role text, status text,
  is_canonical boolean, created_at timestamptz,
  email_confirmed boolean, last_sign_in_at timestamptz
) language plpgsql security definer set search_path = ict_trade as $$
begin
  if not ict_trade.is_admin() then raise exception 'forbidden'; end if;
  return query
    select p.user_id, p.email, p.display_name, p.role, p.status,
           p.is_canonical, p.created_at,
           (u.email_confirmed_at is not null), u.last_sign_in_at
      from ict_trade.profiles p
      left join auth.users u on u.id = p.user_id
     order by p.created_at desc;
end $$;
grant execute on function ict_trade.admin_list_users to authenticated;

-- ---------------------------------------------------------------- confirm email
create or replace function ict_trade.admin_confirm_email(p_user uuid)
returns void language plpgsql security definer set search_path = ict_trade as $$
begin
  if not ict_trade.is_admin() then raise exception 'forbidden'; end if;
  update auth.users set email_confirmed_at = coalesce(email_confirmed_at, now()), updated_at = now()
   where id = p_user;
  if not found then raise exception 'no such user'; end if;
  insert into ict_trade.audit_log (user_id, actor, action, detail)
  values (p_user, auth.uid(), 'admin_confirm_email', '{}'::jsonb);
end $$;
grant execute on function ict_trade.admin_confirm_email to authenticated;

-- ---------------------------------------------------------------- announcement push
create or replace function ict_trade.admin_notify(p_title text, p_body text, p_user uuid default null)
returns integer language plpgsql security definer set search_path = ict_trade as $$
declare n integer;
begin
  if not ict_trade.is_admin() then raise exception 'forbidden'; end if;
  if coalesce(length(trim(p_title)), 0) = 0 then raise exception 'empty title'; end if;
  insert into ict_trade.push_outbox (user_id, payload)
  select p.user_id, jsonb_build_object('title', p_title, 'body', p_body, 'tag', 'admin', 'url', '/')
    from ict_trade.profiles p
   where (p_user is null and p.status = 'active') or p.user_id = p_user;
  get diagnostics n = row_count;
  insert into ict_trade.audit_log (user_id, actor, action, detail)
  values (p_user, auth.uid(), 'admin_notify',
          jsonb_build_object('title', p_title, 'targets', n, 'broadcast', p_user is null));
  return n;
end $$;
grant execute on function ict_trade.admin_notify to authenticated;

-- ---------------------------------------------------------------- global kill
create or replace function ict_trade.admin_kill_all()
returns integer language plpgsql security definer set search_path = ict_trade as $$
declare n integer;
begin
  if not ict_trade.is_admin() then raise exception 'forbidden'; end if;
  update ict_trade.user_stream_settings set kill_requested = true, updated_at = now()
   where enabled = true and kill_requested = false;
  get diagnostics n = row_count;
  insert into ict_trade.audit_log (user_id, actor, action, detail)
  values (null, auth.uid(), 'admin_kill_all', jsonb_build_object('streams', n));
  return n;
end $$;
grant execute on function ict_trade.admin_kill_all to authenticated;

-- ---------------------------------------------------------------- per-user trade stats
create or replace function ict_trade.admin_user_stats()
returns table (user_id uuid, open_count integer, today_usd numeric, total_usd numeric)
language plpgsql security definer set search_path = ict_trade as $$
begin
  if not ict_trade.is_admin() then raise exception 'forbidden'; end if;
  return query
    with allpos as (
      select lp.user_id as uid,
             lp.state in ('PENDING_ENTRY','ENTRY_WORKING','OPEN_FULL','RUNNER','CLOSING') as isopen,
             lp.realized_usd, lp.exit_time
        from ict_trade.live_positions lp where lp.user_id is not null
      union all
      select mp.user_id,
             mp.state in ('PENDING_ENTRY','ENTRY_WORKING','OPEN'),
             mp.realized_usd, mp.exit_time
        from ict_trade.midas_positions mp where mp.user_id is not null
    )
    select a.uid,
           (count(*) filter (where a.isopen))::integer,
           coalesce(sum(a.realized_usd) filter (where a.exit_time >= date_trunc('day', now())), 0),
           coalesce(sum(a.realized_usd), 0)
      from allpos a
     group by a.uid;
end $$;
grant execute on function ict_trade.admin_user_stats to authenticated;

-- ---------------------------------------------------------------- system overview
create or replace function ict_trade.admin_overview()
returns jsonb language plpgsql security definer set search_path = ict_trade as $$
declare out jsonb;
begin
  if not ict_trade.is_admin() then raise exception 'forbidden'; end if;
  select jsonb_build_object(
    'users', (select coalesce(jsonb_object_agg(s.status, s.n), '{}'::jsonb)
                from (select status, count(*) n from ict_trade.profiles group by status) s),
    'open_positions',
      (select count(*) from ict_trade.live_positions
        where state in ('PENDING_ENTRY','ENTRY_WORKING','OPEN_FULL','RUNNER','CLOSING'))
      + (select count(*) from ict_trade.midas_positions
          where state in ('PENDING_ENTRY','ENTRY_WORKING','OPEN')),
    'exec_heartbeat', (select coalesce(jsonb_object_agg(h.network, h.ts), '{}'::jsonb)
                         from (select network, max(updated_at) ts
                                 from ict_trade.live_account group by network) h),
    'last_signal', (select max(signal_time) from ict_trade.signals),
    'last_key_verify', (select max(verified_at) from ict_trade.user_api_keys),
    'outbox_pending', (select count(*) from ict_trade.push_outbox where sent_at is null),
    'invalid_keys', (select count(*) from ict_trade.user_api_keys where status = 'invalid'),
    'enabled_streams', (select count(*) from ict_trade.user_stream_settings where enabled)
  ) into out;
  return out;
end $$;
grant execute on function ict_trade.admin_overview to authenticated;

notify pgrst, 'reload schema';
