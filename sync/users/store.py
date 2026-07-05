"""User loader + per-user helpers for the multi-user executors.

load_exec_users() is the single query both executors (OPUS = sync/live_exec, MIDAS-X =
sync/midas_exec) fan out over: user_stream_settings ⋈ valid user_api_keys ⋈ profiles,
keys decrypted here (sync/users/crypto.py). Selection semantics:

  * a row is loaded when (enabled AND profile active) OR kill_requested OR drain OR the
    user has OPEN positions on that (stream, network) — so a user who disables (or is
    admin-disabled) mid-trade keeps being MANAGED to flat ("drain"), and a kill request
    is honored even after disabling;
  * `entries_allowed` is the executor's gate for NEW entries (enabled + active + no
    kill/drain);
  * MIDAS is hard-locked to testnet here too (defense in depth on top of the table CHECK).

Rows whose key fails to decrypt (rotated PEM?) or is missing are skipped with a log line —
the executor alerts the admin but never crashes the whole tick over one user.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent))                # sync/users -> crypto
sys.path.insert(0, str(_HERE.parents[1]))            # sync/      -> trade_sync_common
import crypto as ucrypto                              # noqa: E402

# stream -> (positions table, states that count as "open")
_POS_TABLES = {
    "opus": ("ict_trade.live_positions",
             ("PENDING_ENTRY", "ENTRY_WORKING", "OPEN_FULL", "RUNNER", "CLOSING")),
    "midas": ("ict_trade.midas_positions",
              ("PENDING_ENTRY", "ENTRY_WORKING", "OPEN")),
}


@dataclass(frozen=True)
class ExecUser:
    user_id: str
    email: str
    is_canonical: bool
    network: str                  # 'mainnet' | 'testnet'
    api_key: str
    api_secret: str
    risk_usd: float
    max_concurrent: int
    max_total_risk_usd: float
    daily_loss_cap_usd: float | None
    symbols: tuple[str, ...]
    kill_requested: bool
    drain: bool
    enabled: bool
    profile_active: bool
    settings_id: int
    key_id: int

    @property
    def entries_allowed(self) -> bool:
        return (self.enabled and self.profile_active
                and not self.kill_requested and not self.drain)


def load_exec_users(conn, stream: str) -> list[ExecUser]:
    pos_table, open_states = _POS_TABLES[stream]
    net_lock = "and s.network = 'testnet'" if stream == "midas" else ""
    sql = f"""
        select s.id, s.user_id::text, p.email, p.is_canonical, s.network,
               s.enabled, s.risk_usd, s.max_concurrent, s.max_total_risk_usd,
               s.daily_loss_cap_usd, s.symbols, s.kill_requested, s.drain,
               (p.status = 'active') as profile_active,
               k.id, k.api_key_enc, k.api_secret_enc,
               exists (select 1 from {pos_table} lp
                        where lp.user_id = s.user_id and lp.network = s.network
                          and lp.state in %s) as has_open
          from ict_trade.user_stream_settings s
          join ict_trade.profiles p on p.user_id = s.user_id
          left join ict_trade.user_api_keys k
            on k.user_id = s.user_id and k.network = s.network and k.status = 'valid'
         where s.stream = %s {net_lock}
         order by p.created_at
    """
    with conn.cursor() as cur:
        cur.execute(sql, (open_states, stream))
        rows = cur.fetchall()

    priv = None
    users: list[ExecUser] = []
    for (sid, uid, email, canonical, network, enabled, risk, maxc, maxrisk,
         losscap, symbols, kill, drain, active, key_id, key_enc, sec_enc, has_open) in rows:
        wanted = (enabled and active) or kill or drain or has_open
        if not wanted:
            continue
        if key_id is None:
            print(f"[users] {email}/{stream}/{network}: no valid key — skipped", flush=True)
            continue
        try:
            if priv is None:
                priv = ucrypto.load_private_key()
            api_key = ucrypto.decrypt_b64(key_enc, priv)
            api_secret = ucrypto.decrypt_b64(sec_enc, priv)
        except Exception as e:  # noqa: BLE001 — one bad row must not kill the tick
            print(f"[users] {email}/{stream}/{network}: key decrypt failed ({e}) — skipped", flush=True)
            continue
        users.append(ExecUser(
            user_id=uid, email=email, is_canonical=bool(canonical), network=network,
            api_key=api_key, api_secret=api_secret,
            risk_usd=float(risk), max_concurrent=int(maxc),
            max_total_risk_usd=float(maxrisk),
            daily_loss_cap_usd=float(losscap) if losscap is not None else None,
            symbols=tuple(symbols or ()), kill_requested=bool(kill), drain=bool(drain),
            enabled=bool(enabled), profile_active=bool(active),
            settings_id=int(sid), key_id=int(key_id),
        ))
    return users


def clear_kill(conn, settings_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute("update ict_trade.user_stream_settings"
                    "   set kill_requested = false, enabled = false, updated_at = now()"
                    " where id = %s", (settings_id,))
    conn.commit()


def realized_today_usd(conn, user_id: str, network: str, stream: str) -> float:
    """Sum of realized_usd for positions CLOSED today (UTC) — the daily-loss-cap input."""
    pos_table, _ = _POS_TABLES[stream]
    with conn.cursor() as cur:
        cur.execute(f"select coalesce(sum(realized_usd), 0) from {pos_table}"
                    "  where user_id = %s and network = %s"
                    "    and exit_time >= date_trunc('day', now())",
                    (user_id, network))
        return float(cur.fetchone()[0] or 0.0)


def daily_pause_notified(conn, user_id: str, stream: str) -> bool:
    """True if the user was already told (today, UTC) that the daily loss cap paused entries."""
    with conn.cursor() as cur:
        cur.execute("select 1 from ict_trade.audit_log"
                    " where user_id = %s and action = 'daily_loss_pause'"
                    "   and detail->>'stream' = %s and created_at >= date_trunc('day', now())"
                    " limit 1", (user_id, stream))
        return cur.fetchone() is not None


def set_key_invalid(conn, key_id: int, reason: str) -> None:
    with conn.cursor() as cur:
        cur.execute("update ict_trade.user_api_keys"
                    "   set status = 'invalid', invalid_reason = %s, updated_at = now()"
                    " where id = %s and status = 'valid'", (reason[:200], key_id))
    conn.commit()


def push_user(conn, user_id: str, title: str, body: str, *, tag: str = "", url: str = "/") -> None:
    """Queue a personal Web Push (drained by sync/push_notify.py). Best-effort."""
    try:
        payload = json.dumps({"title": title, "body": body, "tag": tag, "url": url})
        with conn.cursor() as cur:
            cur.execute("insert into ict_trade.push_outbox (user_id, payload) values (%s, %s::jsonb)",
                        (user_id, payload))
        conn.commit()
    except Exception as e:  # noqa: BLE001
        print(f"[users] push_outbox insert failed: {e}", flush=True)
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass


def audit(conn, user_id: str | None, action: str, detail: dict) -> None:
    """System audit row (actor NULL = VM)."""
    try:
        with conn.cursor() as cur:
            cur.execute("insert into ict_trade.audit_log (user_id, actor, action, detail)"
                        " values (%s, null, %s, %s::jsonb)",
                        (user_id, action, json.dumps(detail, default=str)))
        conn.commit()
    except Exception as e:  # noqa: BLE001
        print(f"[users] audit insert failed: {e}", flush=True)
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
