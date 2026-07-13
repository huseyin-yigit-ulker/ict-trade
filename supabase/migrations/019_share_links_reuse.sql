-- 019 — paylaşım linki YENİDEN KULLANIMI (2026-07-13): aynı işlem ikinci kez paylaşılınca
-- YENİ token üretme — MEVCUT linki geri ver, sadece süreyi sıfırla.
--
-- Neden: admin aynı grafiği gün içinde birkaç kez paylaşabiliyor. Her seferinde yeni token
-- üretmek (a) daha önce dağıtılmış linki ölü bırakıyor, (b) share_links'i aynı işlemin
-- ölü token'larıyla şişiriyordu. Artık işlem başına TEK kalıcı token var; "Paylaş" ona
-- 60 dk'lık yeni bir ömür verir (revoke edilmişse yeniden canlandırır).
--
--   * uq_share_links_signal  — işlem başına tek satır (upsert anahtarı).
--   * renewed_at             — en son ne zaman yenilendiği (created_at ilk üretimi tutar).
--   * views                  — kasten SIFIRLANMAZ: linkin toplam görüntülenmesi kümülatif.
--
-- IDEMPOTENT. apply_sql.py --file ile (owner DSN) uygula.

alter table ict_trade.share_links add column if not exists renewed_at timestamptz;

-- İşlem başına tek link. (Tabloda çift satır varsa en yenisi hariç sil — yeni tabloda no-op.)
delete from ict_trade.share_links l
 where exists (select 1 from ict_trade.share_links k
                where k.signal_id = l.signal_id
                  and (k.created_at, k.token) > (l.created_at, l.token));
create unique index if not exists uq_share_links_signal on ict_trade.share_links (signal_id);
drop index if exists ict_trade.ix_share_links_signal;   -- tekil indeks onu gereksiz kılıyor

-- ---------------------------------------------------------------- create-or-renew (admin)
create or replace function ict_trade.admin_create_share(
  p_signal_id bigint,
  p_payload   jsonb default '{}'::jsonb,
  p_ttl_minutes integer default 60
) returns jsonb language plpgsql security definer set search_path = ict_trade as $$
declare
  tok  text;
  ttl  integer;
  exp  timestamptz;
  reused boolean := false;
begin
  if not ict_trade.is_admin() then raise exception 'forbidden'; end if;
  if not exists (select 1 from ict_trade.signals s where s.id = p_signal_id) then
    raise exception 'no such signal';
  end if;
  ttl := least(greatest(coalesce(p_ttl_minutes, 60), 5), 1440);
  exp := now() + make_interval(mins => ttl);

  -- Bu işlemin linki VARSA: token'ı KORU, süreyi sıfırla, iptal edilmişse dirilt, geometriyi
  -- (payload) tazele. YOKSA yeni 122-bit token üret.
  select l.token into tok from ict_trade.share_links l where l.signal_id = p_signal_id;
  if tok is not null then
    reused := true;
    update ict_trade.share_links
       set expires_at = exp,
           revoked    = false,
           renewed_at = now(),
           payload    = coalesce(p_payload, payload)
     where token = tok;
  else
    tok := replace(gen_random_uuid()::text, '-', '');
    insert into ict_trade.share_links (token, signal_id, payload, created_by, expires_at)
    values (tok, p_signal_id, coalesce(p_payload, '{}'::jsonb), auth.uid(), exp);
  end if;

  insert into ict_trade.audit_log (user_id, actor, action, detail)
  values (null, auth.uid(), case when reused then 'share_renew' else 'share_create' end,
          jsonb_build_object('signal_id', p_signal_id, 'ttl_min', ttl, 'token', tok));

  return jsonb_build_object('token', tok, 'expires_at', exp, 'ttl_minutes', ttl, 'reused', reused);
end $$;
revoke all on function ict_trade.admin_create_share(bigint, jsonb, integer) from public, anon;
grant execute on function ict_trade.admin_create_share(bigint, jsonb, integer) to authenticated;

-- ---------------------------------------------------------------- list (+ renewed_at)
-- Dönüş kolonları değiştiği için create-or-replace yetmez: önce düşür.
drop function if exists ict_trade.admin_list_shares();
create function ict_trade.admin_list_shares()
returns table (
  token text, signal_id bigint, symbol text, created_at timestamptz, renewed_at timestamptz,
  expires_at timestamptz, revoked boolean, views integer, last_view timestamptz
) language plpgsql security definer set search_path = ict_trade as $$
begin
  if not ict_trade.is_admin() then raise exception 'forbidden'; end if;
  return query
    select l.token, l.signal_id, s.symbol, l.created_at, l.renewed_at,
           l.expires_at, l.revoked, l.views, l.last_view
      from ict_trade.share_links l
      left join ict_trade.signals s on s.id = l.signal_id
     order by coalesce(l.renewed_at, l.created_at) desc
     limit 200;
end $$;
revoke all on function ict_trade.admin_list_shares() from public, anon;
grant execute on function ict_trade.admin_list_shares to authenticated;

notify pgrst, 'reload schema';
