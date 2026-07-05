"""Operator kill-switch CLI for the d30so8c live bridge.

    python sync/live_exec/killswitch.py --status     # account + open positions/orders snapshot
    python sync/live_exec/killswitch.py --flatten     # cancel ALL orders + market-close ALL positions
    python sync/live_exec/killswitch.py --halt        # set LIVE_TRADING_ENABLED=false in .env (persistent)

--flatten is the emergency stop: it does not care about state, it cancels every open order on the
enabled symbols and market-closes any residual, then marks the live_positions rows CLOSED. The
persistent halt (--halt) flips the master flag so both crons no-op until you re-enable it.
"""
from __future__ import annotations

import sys
import argparse
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parents[1]))
import _bootenv                                      # noqa: E402,F401  -- MUST precede tsc/scaleout/ict.config
import trade_sync_common as tsc                      # noqa: E402
import config as cfgmod                              # noqa: E402
import state as st                                   # noqa: E402
import notify                                        # noqa: E402
from binance_futures import BinanceFutures, BinanceError   # noqa: E402


def _client(cfg):
    return BinanceFutures(api_key=cfg.api_key, api_secret=cfg.api_secret,
                          base_url=cfg.base_url, proxy=cfg.proxy)


def cmd_status(cfg):
    client = _client(cfg)
    client.sync_time()
    acc = client.account()
    print(f"  wallet=${float(acc.get('totalWalletBalance', 0)):.2f} "
          f"avail=${float(acc.get('availableBalance', 0)):.2f} "
          f"uPnL=${float(acc.get('totalUnrealizedProfit', 0)):.2f}")
    for p in client.position_risk():
        amt = float(p.get("positionAmt", 0) or 0)
        if amt:
            print(f"  POS {p['symbol']:<10} amt={amt} entry={p.get('entryPrice')} "
                  f"uPnL={p.get('unRealizedProfit')}")
    live = tsc.live_conn()
    for pos in st.fetch_open(live, None):
        print(f"  DB  {pos['symbol']:<10} state={pos['state']} qty={pos.get('qty')} "
              f"entry={pos.get('eff_entry')} signal_time={pos['signal_time']}")
    live.close()


def flatten_positions(cfg, client, conn, *, user_id=None, network=None,
                      reason: str = "killswitch") -> int:
    """Cancel every open order (incl. algo conditionals) and MARKET-close every residual position
    on the account behind `client`, then mark the matching live_positions rows CLOSED.
    user_id=None = legacy whole-table semantics (the original --flatten); with a user_id the DB
    update touches ONLY that user's rows (the exchange side is inherently per-account — the
    client IS that user's account). Returns the number of market-closed positions."""
    rows = st.fetch_open(conn, None, user_id=user_id, network=network)
    syms = set(cfg.symbols) | {p["symbol"] for p in rows}
    closed = 0
    for sym in sorted(syms):
        try:
            client.cancel_all_open_orders(sym)
        except BinanceError:
            pass
        try:
            client.cancel_all_algo_orders(sym)      # resting SL/TP conditionals (mainnet)
        except BinanceError:
            pass
        amt = 0.0
        for p in client.position_risk(sym):
            if p.get("symbol") == sym:
                amt = float(p.get("positionAmt", 0) or 0)
        if amt:
            side = "SELL" if amt > 0 else "BUY"
            try:
                client.new_order(symbol=sym, side=side, type="MARKET",
                                 quantity=abs(amt), reduceOnly="true")
                closed += 1
                print(f"  flattened {sym} ({amt})")
            except BinanceError as e:
                print(f"  ! {sym}: {e}")
    cur = conn.cursor()
    q = ("UPDATE ict_trade.live_positions SET state=%s, exit_reason=%s, "
         "exit_time=current_timestamp WHERE state = ANY(%s)")
    params: list = [st.CLOSED, reason, list(st.OPEN_STATES)]
    if user_id is not None:
        q += " AND user_id = %s"
        params.append(user_id)
        if network is not None:
            q += " AND network = %s"
            params.append(network)
    cur.execute(q, tuple(params))
    conn.commit()
    cur.close()
    return closed


def cmd_flatten(cfg):
    if not (cfg.api_key and cfg.api_secret):
        raise SystemExit("no API keys — cannot flatten.")
    client = _client(cfg)
    client.sync_time()
    live = tsc.live_conn()
    closed = flatten_positions(cfg, client, live)
    live.close()
    notify.alert(f"🟥 d30so8c KILLSWITCH --flatten: {closed} position(s) market-closed",
                 chat_id=cfg.telegram_chat_id)
    print(f"  done — {closed} flattened, DB rows marked CLOSED.")


def cmd_flatten_user(cfg, email: str):
    """Flatten ONE user's account (multi-user mode): their keys, their rows only."""
    sys.path.insert(0, str(_HERE.parents[1] / "users"))
    import store as ustore  # noqa: E402
    live = tsc.live_conn()
    users = [u for u in ustore.load_exec_users(live, "opus") if u.email.lower() == email.lower()]
    if not users:
        live.close()
        raise SystemExit(f"no loadable exec user {email!r} (needs active profile + valid key)")
    total = 0
    for u in users:
        ucfg = cfgmod.cfg_for_user(cfg, u)
        client = _client(ucfg)
        client.sync_time()
        total += flatten_positions(ucfg, client, live, user_id=u.user_id, network=u.network,
                                   reason="killswitch_admin")
        ustore.audit(live, u.user_id, "kill_executed", {"stream": "opus", "network": u.network,
                                                        "by": "cli", "flattened": total})
    live.close()
    notify.alert(f"🟥 KILLSWITCH --user {email}: {total} position(s) market-closed",
                 chat_id=cfg.telegram_chat_id)
    print(f"  done — {total} flattened for {email}.")


def cmd_halt():
    """Persistently flip LIVE_TRADING_ENABLED=false in .env (both crons then no-op)."""
    env_path = tsc.ENV_PATH
    lines = env_path.read_text().splitlines()
    found = False
    for i, ln in enumerate(lines):
        if ln.strip().startswith("LIVE_TRADING_ENABLED="):
            lines[i] = "LIVE_TRADING_ENABLED=false"
            found = True
    if not found:
        lines.append("LIVE_TRADING_ENABLED=false")
    env_path.write_text("\n".join(lines) + "\n")
    print("  LIVE_TRADING_ENABLED=false written to .env — crons will no-op until re-enabled.")


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--status", action="store_true")
    g.add_argument("--flatten", action="store_true")
    g.add_argument("--halt", action="store_true")
    ap.add_argument("--user", default=None, help="flatten only this user's account (email)")
    args = ap.parse_args()
    if args.halt:
        cmd_halt()
        return
    cfg = cfgmod.load_cfg()
    if args.status:
        cmd_status(cfg)
    elif args.flatten:
        if args.user:
            cmd_flatten_user(cfg, args.user)
        else:
            cmd_flatten(cfg)


if __name__ == "__main__":
    main()
