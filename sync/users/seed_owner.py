"""One-shot owner seeding + legacy-row backfill for the multi-user cutover.

Prereqs (in order):
  1. supabase/migrations/001..004 + 005a + 006 applied (apply_sql.py --phase1)
  2. apply_sql.py --seed-universe (settings inserts validate symbols against it)
  3. the owner has SIGNED UP through the UI (GoTrue creates auth.users + pending profile)
     — inserting into auth.users by hand is deliberately NOT supported (auth.identities /
     instance_id coupling is brittle across Supabase upgrades).

Then:
  .venv/bin/python sync/users/seed_owner.py --email ugur_yigit@hotmail.com
     * promotes the profile: role=admin, status=active, is_canonical=true
     * imports .env BINANCE_API_KEY/SECRET (mainnet) + BINANCE_TESTNET_API_KEY/SECRET
       (testnet) into user_api_keys, RSA-encrypted like a browser submission
     * verifies them INLINE (sync/users/verify_keys.verify_row)
     * inserts user_stream_settings mirroring today's .env:
         opus/mainnet  enabled  risk=RISK_PER_TRADE_USD      symbols=EXEC_ENABLED_SYMBOLS
         opus/testnet  disabled (ready to toggle)
         midas/testnet enabled  risk=MIDAS_RISK_PER_TRADE_USD symbols={XAUUSDT}
       (enabled only flips on when the freshly-verified key came back 'valid' —
        the tg_uss_guard trigger enforces the same server-side)

  .venv/bin/python sync/users/seed_owner.py --email ... --backfill
     * Phase-5 halt window ONLY: stamps user_id (+network) on every legacy row of
       live_positions/live_orders/midas_positions/midas_orders/live_account/
       live_account_snapshot/push_subscriptions so 005b's per-user keys apply cleanly.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parents[1]))
sys.path.insert(0, str(_HERE.parents[1] / "live_exec"))
import crypto as ucrypto                               # noqa: E402
import trade_sync_common as tsc                        # noqa: E402
import verify_keys                                     # noqa: E402


def _owner_uid(conn, email: str) -> str:
    with conn.cursor() as cur:
        cur.execute("select id::text from auth.users where lower(email) = lower(%s)", (email,))
        row = cur.fetchone()
    if not row:
        raise SystemExit(f"No auth user with email {email!r} — sign up through the UI first.")
    return row[0]


def _promote(conn, uid: str, email: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "insert into ict_trade.profiles (user_id, email, display_name, role, status, is_canonical)"
            " values (%s, %s, split_part(%s, '@', 1), 'admin', 'active', true)"
            " on conflict (user_id) do update"
            "   set role='admin', status='active', is_canonical=true, updated_at=now()",
            (uid, email, email))
    conn.commit()
    print(f"[seed] profile {email} -> admin/active/canonical", flush=True)


def _import_key(conn, uid: str, network: str, api_key: str, api_secret: str, priv) -> int | None:
    if not (api_key and api_secret):
        print(f"[seed] no {network} keys in .env — skipped", flush=True)
        return None
    with conn.cursor() as cur:
        cur.execute("select id from ict_trade.user_api_keys"
                    " where user_id=%s and network=%s and status in ('pending_verify','valid')",
                    (uid, network))
        row = cur.fetchone()
        if row:
            print(f"[seed] {network} key already active (id {row[0]}) — left untouched", flush=True)
            return int(row[0])
        pub = priv.public_key()
        cur.execute(
            "insert into ict_trade.user_api_keys (user_id, network, api_key_enc, api_secret_enc, key_last4)"
            " values (%s, %s, %s, %s, %s) returning id",
            (uid, network, ucrypto.encrypt_b64(api_key, pub), ucrypto.encrypt_b64(api_secret, pub),
             api_key[-4:]))
        key_id = int(cur.fetchone()[0])
    conn.commit()
    print(f"[seed] {network} key imported (id {key_id})", flush=True)
    return key_id


def _verify(conn, key_id: int, priv) -> str:
    with conn.cursor() as cur:
        cur.execute("select id, user_id::text, network, api_key_enc, api_secret_enc, status"
                    "  from ict_trade.user_api_keys where id=%s", (key_id,))
        r = cur.fetchone()
    row = dict(zip(("id", "user_id", "network", "api_key_enc", "api_secret_enc", "status"), r))
    if row["status"] == "valid":
        return "valid"
    return verify_keys.verify_row(conn, row, priv)


def _settings(conn, uid: str, stream: str, network: str, *, enabled: bool, risk: float,
              max_concurrent: int, max_total: float, symbols: list[str]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "insert into ict_trade.user_stream_settings"
            " (user_id, stream, network, enabled, risk_usd, max_concurrent, max_total_risk_usd, symbols)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s)"
            " on conflict (user_id, stream, network) do nothing",
            (uid, stream, network, enabled, risk, max_concurrent, max_total, symbols))
    conn.commit()
    print(f"[seed] settings {stream}/{network} enabled={enabled} risk=${risk} symbols={symbols}", flush=True)


def _backfill(conn, uid: str) -> None:
    stamps = [
        ("ict_trade.live_positions", "user_id=%s, network=coalesce(network,'mainnet')"),
        ("ict_trade.live_orders", "user_id=%s"),
        ("ict_trade.midas_positions", "user_id=%s, network=coalesce(network,'testnet')"),
        ("ict_trade.midas_orders", "user_id=%s"),
        ("ict_trade.live_account", "user_id=%s"),
        ("ict_trade.live_account_snapshot", "user_id=%s"),
        ("ict_trade.push_subscriptions", "user_id=%s"),
    ]
    with conn.cursor() as cur:
        for table, setexpr in stamps:
            cur.execute(f"update {table} set {setexpr} where user_id is null", (uid,))
            print(f"[seed] backfill {table}: {cur.rowcount} rows", flush=True)
    conn.commit()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--backfill", action="store_true",
                    help="Phase-5 only: stamp legacy rows with the owner user_id")
    args = ap.parse_args()

    env = tsc._read_env()
    conn = tsc.live_conn()
    try:
        uid = _owner_uid(conn, args.email)
        _promote(conn, uid, args.email)

        if args.backfill:
            _backfill(conn, uid)
            return

        priv = ucrypto.load_private_key()
        main_id = _import_key(conn, uid, "mainnet",
                              env.get("BINANCE_API_KEY", "").strip(),
                              env.get("BINANCE_API_SECRET", "").strip(), priv)
        test_id = _import_key(conn, uid, "testnet",
                              env.get("BINANCE_TESTNET_API_KEY", "").strip(),
                              env.get("BINANCE_TESTNET_API_SECRET", "").strip(), priv)
        main_ok = main_id is not None and _verify(conn, main_id, priv) == "valid"
        test_ok = test_id is not None and _verify(conn, test_id, priv) == "valid"

        symbols = [s.strip().upper() for s in
                   env.get("EXEC_ENABLED_SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT").split(",") if s.strip()]
        risk = float(env.get("RISK_PER_TRADE_USD", 5.0))
        maxc = int(float(env.get("MAX_CONCURRENT_POSITIONS", 5)))
        maxtot = float(env.get("MAX_TOTAL_RISK_USD", 25.0))
        _settings(conn, uid, "opus", "mainnet", enabled=main_ok, risk=risk,
                  max_concurrent=maxc, max_total=maxtot, symbols=symbols)
        _settings(conn, uid, "opus", "testnet", enabled=False, risk=risk,
                  max_concurrent=maxc, max_total=maxtot, symbols=symbols)
        m_risk = float(env.get("MIDAS_RISK_PER_TRADE_USD", 5.0))
        _settings(conn, uid, "midas", "testnet", enabled=test_ok, risk=m_risk,
                  max_concurrent=int(float(env.get("MIDAS_MAX_CONCURRENT", 1))),
                  max_total=m_risk * 2, symbols=["XAUUSDT"])
        print("[seed] done. Next: watch verify statuses in the UI, then Phase-5 cutover.", flush=True)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
