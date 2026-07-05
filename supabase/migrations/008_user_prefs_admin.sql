-- 008 — kullanıcı tercihleri + admin merkezî kontrol katmanı (2026-07-05).
--
--   * ict_trade.user_prefs     — UI tercihleri (tema/dil/açılış sayfası) + bildirim
--                                tercihleri (entry/exit/milestone/signals/system).
--                                Kullanıcı kendi satırını yazar; VM push yolları okur.
--   * ict_trade.user_features  — admin'in kullanıcı-başına açtığı yüzeyler
--                                (backtest / istihbarat / işlem merkezi). Satır yoksa
--                                hepsi AÇIK kabul edilir; SADECE admin_set_features
--                                RPC'siyle yazılır (client'a update grant'i yok).
--   * admin_set_features RPC   — upsert + audit.
--   * admin_delete_user RPC    — auth.users satırını siler (cascade: profiles →
--                                keys/settings/prefs/features); açık pozisyon varken,
--                                canonical (owner) hesapta ve kendi hesabında REDDEDER.
--
-- IDEMPOTENT. apply_sql.py --file ile (owner DSN) uygula. NOT: admin_delete_user
-- auth.users'tan siler — function owner'ın (postgres) auth.users DELETE yetkisi olmalı;
-- pooler DSN kullanıcısında yoksa bu dosyayı Supabase SQL editöründe çalıştırın.

-- ------------------------------------------------------------------ user_prefs
create table if not exists ict_trade.user_prefs (
  user_id          uuid primary key references ict_trade.profiles(user_id) on delete cascade,
  theme            text check (theme is null or theme in ('dark','light')),
  lang             text check (lang is null or lang in ('tr','en')),
  default_page     text check (default_page is null or length(default_page) <= 40),
  notify_entry     boolean not null default true,   -- pozisyon girişleri (giriş/ters/atlandı)
  notify_exit      boolean not null default true,   -- kapanışlar (stop/cap/zaman/kapandı)
  notify_milestone boolean not null default true,   -- ara olaylar (TP1, breakeven, iz süren)
  notify_signals   boolean not null default true,   -- merkezî sinyal yayınları (broadcast)
  notify_system    boolean not null default true,   -- sistem/anahtar/güvenlik uyarıları
  updated_at       timestamptz not null default now()
);

create or replace function ict_trade.tg_touch() returns trigger
language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end $$;

drop trigger if exists touch_user_prefs on ict_trade.user_prefs;
create trigger touch_user_prefs before insert or update on ict_trade.user_prefs
  for each row execute function ict_trade.tg_touch();

alter table ict_trade.user_prefs enable row level security;
grant select, insert, update on ict_trade.user_prefs to authenticated;

drop policy if exists user_prefs_own on ict_trade.user_prefs;
create policy user_prefs_own on ict_trade.user_prefs for all to authenticated
  using (user_id = auth.uid() or ict_trade.is_admin())
  with check (user_id = auth.uid());

-- ---------------------------------------------------------------- user_features
create table if not exists ict_trade.user_features (
  user_id      uuid primary key references ict_trade.profiles(user_id) on delete cascade,
  backtest     boolean not null default true,   -- BACKTEST bölümü + /:slug/backtest
  intelligence boolean not null default true,   -- İstihbarat sayfası
  trading      boolean not null default true,   -- İşlem Merkezi (status=active'e ek kapı)
  updated_at   timestamptz not null default now()
);

drop trigger if exists touch_user_features on ict_trade.user_features;
create trigger touch_user_features before insert or update on ict_trade.user_features
  for each row execute function ict_trade.tg_touch();

alter table ict_trade.user_features enable row level security;
grant select on ict_trade.user_features to authenticated;   -- yazma YOK: sadece RPC

drop policy if exists user_features_select on ict_trade.user_features;
create policy user_features_select on ict_trade.user_features for select to authenticated
  using (user_id = auth.uid() or ict_trade.is_admin());

create or replace function ict_trade.admin_set_features(
  p_user uuid, p_backtest boolean, p_intelligence boolean, p_trading boolean)
returns void language plpgsql security definer set search_path = ict_trade as $$
begin
  if not ict_trade.is_admin() then
    raise exception 'forbidden';
  end if;
  if not exists (select 1 from ict_trade.profiles where user_id = p_user) then
    raise exception 'no such user';
  end if;
  insert into ict_trade.user_features (user_id, backtest, intelligence, trading)
  values (p_user, p_backtest, p_intelligence, p_trading)
  on conflict (user_id) do update
    set backtest = excluded.backtest,
        intelligence = excluded.intelligence,
        trading = excluded.trading,
        updated_at = now();
  insert into ict_trade.audit_log (user_id, actor, action, detail)
  values (p_user, auth.uid(), 'admin_set_features',
          jsonb_build_object('backtest', p_backtest, 'intelligence', p_intelligence,
                             'trading', p_trading));
end $$;

grant execute on function ict_trade.admin_set_features to authenticated;

-- -------------------------------------------------------------- admin_delete_user
create or replace function ict_trade.admin_delete_user(p_user uuid)
returns void language plpgsql security definer set search_path = ict_trade as $$
declare
  v_email text;
begin
  if not ict_trade.is_admin() then
    raise exception 'forbidden';
  end if;
  if p_user = auth.uid() then
    raise exception 'kendi hesabınızı silemezsiniz';
  end if;
  select email into v_email from ict_trade.profiles where user_id = p_user;
  if v_email is null then
    raise exception 'no such user';
  end if;
  if exists (select 1 from ict_trade.profiles where user_id = p_user and is_canonical) then
    raise exception 'canonical (owner) hesap silinemez';
  end if;
  if exists (select 1 from ict_trade.live_positions
              where user_id = p_user
                and state in ('PENDING_ENTRY','ENTRY_WORKING','OPEN_FULL','RUNNER','CLOSING'))
     or exists (select 1 from ict_trade.midas_positions
                 where user_id = p_user
                   and state in ('PENDING_ENTRY','ENTRY_WORKING','OPEN')) then
    raise exception 'açık pozisyon var — önce KILL ile düz konuma getirin';
  end if;
  -- FK'sız user_id taşıyan tablolar elle temizlenir; audit satırı silmeden ÖNCE yazılır
  -- (audit_log.user_id FK'sız olduğundan iz kalıcıdır).
  delete from ict_trade.push_subscriptions where user_id = p_user;
  delete from ict_trade.push_outbox where user_id = p_user;
  insert into ict_trade.audit_log (user_id, actor, action, detail)
  values (p_user, auth.uid(), 'admin_delete_user', jsonb_build_object('email', v_email));
  -- auth.users → cascade: profiles → user_api_keys / user_stream_settings / user_prefs / user_features
  delete from auth.users where id = p_user;
end $$;

grant execute on function ict_trade.admin_delete_user to authenticated;

notify pgrst, 'reload schema';
