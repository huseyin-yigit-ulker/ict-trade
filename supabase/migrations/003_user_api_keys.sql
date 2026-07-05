-- 003 — ict_trade.user_api_keys: per-user Binance API keys, WRITE-ONLY for clients.
--
-- Secrecy model: the browser encrypts key+secret with the VM's RSA-OAEP-SHA256 public
-- key (VITE_EXEC_PUBKEY_B64) BEFORE the insert, so this table only ever holds ciphertext.
-- Clients get NO select on the base table — reads go through the sanitized view
-- user_api_keys_public (last4 + status + balance, never the ciphertext columns).
-- The VM (table owner, RLS-bypassing DSN) decrypts with ~/.exec_keys/exec_rsa.pem.
-- IDEMPOTENT.

create table if not exists ict_trade.user_api_keys (
  id                  bigint generated always as identity primary key,
  user_id             uuid not null references ict_trade.profiles(user_id) on delete cascade,
  network             text not null check (network in ('mainnet','testnet')),
  api_key_enc         text not null,          -- base64(RSA-OAEP-SHA256 ciphertext)
  api_secret_enc      text not null,
  key_last4           text,                   -- computed client-side pre-encryption; display only
  status              text not null default 'pending_verify'
                      check (status in ('pending_verify','valid','invalid','rotated')),
  invalid_reason      text,
  balance_usdt        numeric,                -- filled by sync/users/verify_keys.py
  futures_enabled     boolean,
  withdrawals_enabled boolean,                -- /sapi/v1/account/apiRestrictions (null = unknown)
  position_mode_ok    boolean,                -- one-way position mode (executor requires it)
  verified_at         timestamptz,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

-- One ACTIVE (pending/valid) key per (user, network); rotation retires the old row.
create unique index if not exists uq_user_api_keys_active
  on ict_trade.user_api_keys (user_id, network) where status in ('pending_verify','valid');

create index if not exists user_api_keys_pending_idx
  on ict_trade.user_api_keys (status) where status = 'pending_verify';

alter table ict_trade.user_api_keys enable row level security;

-- INSERT only (first key); everything else via rotate_api_key / the view / the VM.
grant insert on ict_trade.user_api_keys to authenticated;

drop policy if exists uak_insert on ict_trade.user_api_keys;
create policy uak_insert on ict_trade.user_api_keys for insert to authenticated
  with check (user_id = auth.uid() and status = 'pending_verify');

-- Rotation: atomically retire the active key and stage the replacement.
create or replace function ict_trade.rotate_api_key(p_network text, p_key_enc text, p_secret_enc text, p_last4 text)
returns void language plpgsql security definer set search_path = ict_trade as $$
begin
  if auth.uid() is null then
    raise exception 'forbidden';
  end if;
  if p_network not in ('mainnet','testnet') then
    raise exception 'bad network %', p_network;
  end if;
  update ict_trade.user_api_keys
     set status = 'rotated', updated_at = now()
   where user_id = auth.uid() and network = p_network and status in ('pending_verify','valid');
  insert into ict_trade.user_api_keys (user_id, network, api_key_enc, api_secret_enc, key_last4)
  values (auth.uid(), p_network, p_key_enc, p_secret_enc, p_last4);
end $$;

grant execute on function ict_trade.rotate_api_key to authenticated;

-- Sanitized read model. security_invoker=false → runs with the view owner's rights
-- (can read the no-grant base table); the embedded auth.uid() filter is the row guard.
create or replace view ict_trade.user_api_keys_public
with (security_invoker = false, security_barrier = true) as
  select id, user_id, network, key_last4, status, invalid_reason, balance_usdt,
         futures_enabled, withdrawals_enabled, position_mode_ok, verified_at, created_at
  from ict_trade.user_api_keys
  where user_id = auth.uid() or ict_trade.is_admin();

grant select on ict_trade.user_api_keys_public to authenticated;

drop trigger if exists audit_user_api_keys on ict_trade.user_api_keys;
create trigger audit_user_api_keys after insert or update on ict_trade.user_api_keys
  for each row execute function ict_trade.tg_audit();

notify pgrst, 'reload schema';
