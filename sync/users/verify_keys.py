"""Key-verification cron (dag/crontab: every minute, offset 40s).

Picks up ict_trade.user_api_keys rows in 'pending_verify' (active profiles only) and
re-verifies 'valid' rows older than 24h (keeps balance_usdt fresh for the risk guard).
Per key:

  * decrypt (sync/users/crypto.py) and hit the right network:
      mainnet  https://fapi.binance.com   |  testnet  https://testnet.binancefuture.com
  * /fapi/v2/account          -> balance_usdt (totalWalletBalance), futures_enabled (canTrade)
  * /fapi/v1/positionSide/dual-> position_mode_ok (one-way required by the executor)
  * mainnet only: /sapi/v1/account/apiRestrictions (spot host) -> enableWithdrawals.
      TRUE  => status='invalid' (withdrawal-capable keys are refused outright)
      call fails (IP-restricted key without spot scope, etc.) => withdrawals_enabled=NULL,
      key still 'valid' — the UI shows a warning instead.
  * auth errors (-2014/-2015/-1022...) => status='invalid' + reason.

Result is pushed to the user (push_outbox) and audited (actor NULL = system).
Run manually: .venv/bin/python sync/users/verify_keys.py [--all]
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent))                 # sync/users
sys.path.insert(0, str(_HERE.parents[1]))             # sync/
sys.path.insert(0, str(_HERE.parents[1] / "live_exec"))
import crypto as ucrypto                               # noqa: E402
import store as ustore                                 # noqa: E402
import trade_sync_common as tsc                        # noqa: E402
from binance_futures import BinanceFutures, BinanceError  # noqa: E402

MAINNET_BASE = "https://fapi.binance.com"
TESTNET_BASE = "https://testnet.binancefuture.com"
REVERIFY_HOURS = 24


def verify_row(conn, row: dict, priv) -> str:
    """Verify one user_api_keys row; writes the result. Returns the new status."""
    key_id, user_id, network = row["id"], row["user_id"], row["network"]
    env = tsc._read_env()
    proxy = env.get("BINANCE_PROXY", "").strip()

    status, reason = "valid", None
    balance = futures_ok = withdrawals = pos_mode_ok = None
    try:
        api_key = ucrypto.decrypt_b64(row["api_key_enc"], priv)
        api_secret = ucrypto.decrypt_b64(row["api_secret_enc"], priv)
        client = BinanceFutures(api_key=api_key, api_secret=api_secret,
                                base_url=TESTNET_BASE if network == "testnet" else MAINNET_BASE,
                                proxy=proxy)
        client.sync_time()
        acct = client.account()
        balance = float(acct.get("totalWalletBalance", 0.0))
        futures_ok = bool(acct.get("canTrade", True))
        try:
            pos_mode_ok = not bool(client.position_mode().get("dualSidePosition", False))
        except BinanceError:
            pos_mode_ok = None
        if network == "mainnet":
            try:
                restr = client.spot_api_restrictions()
                withdrawals = bool(restr.get("enableWithdrawals", False))
                if withdrawals:
                    status, reason = "invalid", "withdrawals_enabled"
            except BinanceError:
                withdrawals = None          # spot scope unavailable — warn in UI, don't refuse
    except BinanceError as e:
        status, reason = "invalid", f"binance {e.code}: {e.msg}"[:200]
    except Exception as e:  # noqa: BLE001 — decrypt/network wrapper failures
        status, reason = "invalid", f"verify error: {e}"[:200]

    with conn.cursor() as cur:
        cur.execute(
            "update ict_trade.user_api_keys set status=%s, invalid_reason=%s, balance_usdt=%s,"
            " futures_enabled=%s, withdrawals_enabled=%s, position_mode_ok=%s,"
            " verified_at=now(), updated_at=now() where id=%s",
            (status, reason, balance, futures_ok, withdrawals, pos_mode_ok, key_id))
    conn.commit()

    ustore.audit(conn, user_id, "key_verified",
                 {"key_id": key_id, "network": network, "status": status, "reason": reason,
                  "balance_usdt": balance, "position_mode_ok": pos_mode_ok})
    if status == "valid":
        ustore.push_user(conn, user_id, "API anahtarı doğrulandı ✅",
                         f"{network} anahtarınız geçerli. Bakiye: {balance:.2f} USDT."
                         + ("" if pos_mode_ok in (True, None) else " ⚠️ Hesap hedge modda — one-way moda geçin."),
                         tag=f"key-{network}")
    else:
        ustore.push_user(conn, user_id, "API anahtarı REDDEDİLDİ ❌",
                         f"{network}: {reason}. Anahtarı yenileyin (Trading → API Anahtarları).",
                         tag=f"key-{network}")
    print(f"[verify] key {key_id} {network} -> {status}" + (f" ({reason})" if reason else ""), flush=True)
    return status


def _fetch(conn, where: str, params: tuple = ()) -> list[dict]:
    cols = ("id", "user_id", "network", "api_key_enc", "api_secret_enc")
    with conn.cursor() as cur:
        cur.execute(
            f"select k.id, k.user_id::text, k.network, k.api_key_enc, k.api_secret_enc"
            f"  from ict_trade.user_api_keys k"
            f"  join ict_trade.profiles p on p.user_id = k.user_id and p.status = 'active'"
            f" where {where} order by k.id", params)
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def main() -> None:
    reverify_all = "--all" in sys.argv
    conn = tsc.live_conn()
    try:
        rows = _fetch(conn, "k.status = 'pending_verify'")
        if reverify_all:
            rows += _fetch(conn, "k.status = 'valid'")
        else:
            rows += _fetch(conn, "k.status = 'valid' and (k.verified_at is null"
                                 " or k.verified_at < now() - interval '%s hours')" % REVERIFY_HOURS)
        if not rows:
            return
        priv = ucrypto.load_private_key()
        for row in rows:
            try:
                verify_row(conn, row, priv)
            except Exception as e:  # noqa: BLE001 — one key must not block the rest
                print(f"[verify] key {row['id']}: {e}", flush=True)
                try:
                    conn.rollback()
                except Exception:  # noqa: BLE001
                    pass
    finally:
        conn.close()


if __name__ == "__main__":
    main()
