-- 018 — paylaşılabilir işlem linkleri (2026-07-13): admin bir CANLI işlemi 1 saatlik,
-- login gerektirmeyen bir public link olarak paylaşabilir (/p/<token>).
--
--   * share_links            — token → signal_id + donmuş GEOMETRİ (payload) + TTL.
--   * admin_create_share()   — admin-only; token üretir, TTL 5..1440 dk (varsayılan 60).
--   * get_shared_trade()     — PUBLIC (anon): token'ı çözer, süresi/iptali dolmuşsa hata döner.
--   * admin_list_shares()    — admin-only; aktif linkler + görüntülenme sayacı.
--   * admin_revoke_share()   — admin-only; süresi dolmadan linki öldürür.
--
-- GİZLİLİK SÖZLEŞMESİ (bilerek dar): get_shared_trade ASLA strategy / version / mode /
-- quality / confluence_score / context.atrx döndürmez. Public yüzeye çıkan tek canlı alanlar
-- context içinden beyaz-listelenmiş trail / pos / exit_px / pnl_r; geometri (entry/sl/tp/tp1)
-- ise paylaşım anında admin'in tarayıcısında hesaplanıp payload'a DONDURULUR — böylece public
-- sayfa ·0.5R confirm kaydırması / scale-out cap gibi kuralları yeniden türetmek için strateji
-- etiketini bilmek zorunda kalmaz.
--
-- share_links RLS açık + policy YOK ve anon/authenticated'tan revoke edilmiş: tabloya PostgREST
-- üzerinden doğrudan erişilemez, yalnız bu security-definer fonksiyonlar dokunur.
--
-- IDEMPOTENT. apply_sql.py --file ile (owner DSN) uygula.

create table if not exists ict_trade.share_links (
  token       text        primary key,
  signal_id   bigint      not null,
  payload     jsonb       not null default '{}'::jsonb,
  created_by  uuid,
  created_at  timestamptz not null default now(),
  expires_at  timestamptz not null,
  revoked     boolean     not null default false,
  views       integer     not null default 0,
  last_view   timestamptz
);
create index if not exists ix_share_links_created on ict_trade.share_links (created_at desc);
create index if not exists ix_share_links_signal  on ict_trade.share_links (signal_id);

alter table ict_trade.share_links enable row level security;
revoke all on ict_trade.share_links from anon, authenticated;

-- ---------------------------------------------------------------- create (admin)
create or replace function ict_trade.admin_create_share(
  p_signal_id bigint,
  p_payload   jsonb default '{}'::jsonb,
  p_ttl_minutes integer default 60
) returns jsonb language plpgsql security definer set search_path = ict_trade as $$
declare
  tok text;
  ttl integer;
  exp timestamptz;
begin
  if not ict_trade.is_admin() then raise exception 'forbidden'; end if;
  if not exists (select 1 from ict_trade.signals s where s.id = p_signal_id) then
    raise exception 'no such signal';
  end if;
  -- TTL 5 dk .. 24 sa arasına sıkıştır (varsayılan 60 dk).
  ttl := least(greatest(coalesce(p_ttl_minutes, 60), 5), 1440);
  exp := now() + make_interval(mins => ttl);
  -- 122-bit rastgele token (gen_random_uuid çekirdekte — pgcrypto gerekmez).
  tok := replace(gen_random_uuid()::text, '-', '');

  insert into ict_trade.share_links (token, signal_id, payload, created_by, expires_at)
  values (tok, p_signal_id, coalesce(p_payload, '{}'::jsonb), auth.uid(), exp);

  insert into ict_trade.audit_log (user_id, actor, action, detail)
  values (null, auth.uid(), 'share_create',
          jsonb_build_object('signal_id', p_signal_id, 'ttl_min', ttl, 'token', tok));

  return jsonb_build_object('token', tok, 'expires_at', exp, 'ttl_minutes', ttl);
end $$;
-- Postgres YENİ fonksiyonlara PUBLIC execute verir → anon da çağırabilirdi (is_admin() kapısı
-- yine de reddederdi, ama derinlemesine savunma: yüzeyi tamamen kaldır).
revoke all on function ict_trade.admin_create_share(bigint, jsonb, integer) from public, anon;
grant execute on function ict_trade.admin_create_share(bigint, jsonb, integer) to authenticated;

-- ---------------------------------------------------------------- resolve (PUBLIC / anon)
-- Hata durumları exception değil {error: …} olarak döner — public sayfa 4xx gürültüsü yerine
-- "Linkin süresi doldu" ekranını gösterebilsin diye.
create or replace function ict_trade.get_shared_trade(p_token text)
returns jsonb language plpgsql security definer set search_path = ict_trade as $$
declare
  l ict_trade.share_links%rowtype;
  ctx jsonb;
begin
  select * into l from ict_trade.share_links where token = p_token;
  if not found          then return jsonb_build_object('error', 'not_found'); end if;
  if l.revoked          then return jsonb_build_object('error', 'revoked');   end if;
  if l.expires_at <= now() then return jsonb_build_object('error', 'expired'); end if;

  -- CANLI kısım: yalnız beyaz-listelenmiş context alanları (trail/pos/exit_px/pnl_r).
  select s.context into ctx from ict_trade.signals s where s.id = l.signal_id;

  update ict_trade.share_links
     set views = views + 1, last_view = now()
   where token = l.token;

  return jsonb_build_object(
    'expires_at', l.expires_at,
    'payload',    l.payload,
    'live', jsonb_build_object(
      'trail',   ctx -> 'trail',
      'pos',     ctx ->> 'pos',
      'exit_px', ctx ->> 'exit_px',
      'pnl_r',   ctx ->> 'pnl_r'
    )
  );
end $$;
grant execute on function ict_trade.get_shared_trade(text) to anon, authenticated;

-- ---------------------------------------------------------------- list / revoke (admin)
create or replace function ict_trade.admin_list_shares()
returns table (
  token text, signal_id bigint, symbol text, created_at timestamptz,
  expires_at timestamptz, revoked boolean, views integer, last_view timestamptz
) language plpgsql security definer set search_path = ict_trade as $$
begin
  if not ict_trade.is_admin() then raise exception 'forbidden'; end if;
  return query
    select l.token, l.signal_id, s.symbol, l.created_at,
           l.expires_at, l.revoked, l.views, l.last_view
      from ict_trade.share_links l
      left join ict_trade.signals s on s.id = l.signal_id
     order by l.created_at desc
     limit 200;
end $$;
revoke all on function ict_trade.admin_list_shares() from public, anon;
grant execute on function ict_trade.admin_list_shares to authenticated;

create or replace function ict_trade.admin_revoke_share(p_token text)
returns void language plpgsql security definer set search_path = ict_trade as $$
begin
  if not ict_trade.is_admin() then raise exception 'forbidden'; end if;
  update ict_trade.share_links set revoked = true where token = p_token;
  if not found then raise exception 'no such share'; end if;
  insert into ict_trade.audit_log (user_id, actor, action, detail)
  values (null, auth.uid(), 'share_revoke', jsonb_build_object('token', p_token));
end $$;
revoke all on function ict_trade.admin_revoke_share(text) from public, anon;
grant execute on function ict_trade.admin_revoke_share(text) to authenticated;

notify pgrst, 'reload schema';
