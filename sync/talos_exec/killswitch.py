"""Operator kill-switch CLI for the TALOS (gold XAUUSDT) live bridge — scoped to TALOS only.

    python sync/talos_exec/killswitch.py --status     # account + XAUUSDT position/orders + DB rows
    python sync/talos_exec/killswitch.py --flatten     # cancel XAUUSDT orders + market-close + rows CLOSED
    python sync/talos_exec/killswitch.py --flatten --user a@b.c   # ONE user's account/rows (multi-user)
    python sync/talos_exec/killswitch.py --halt        # set TALOS_EXEC_ENABLED=false in .env (TALOS-only)

--flatten is the emergency stop for TALOS: it cancels every open order on the TALOS symbol and
market-closes any residual, then marks the talos_positions rows CLOSED — it does NOT touch OPUS.
--halt flips the TALOS-scoped flag (TALOS_EXEC_ENABLED=false) so only TALOS no-ops; use the OPUS
killswitch --halt (LIVE_TRADING_ENABLED=false) to stop everything.

flatten_positions() is also the executor's kill-switch primitive (user taps "ACİL DURDUR" →
user_stream_settings.kill_requested → the next tick calls it with that user's cfg/scope).
"""
from __future__ import annotations

import sys
import argparse
from pathlib import Path

_HERE = Path(__file__).resolve()
# our own dir MUST be front-most (config.py/state.py also exist in sync/live_exec) — insert it LAST.
sys.path.insert(0, str(_HERE.parents[1] / "live_exec"))
sys.path.insert(0, str(_HERE.parents[1]))
sys.path.insert(0, str(_HERE.parent))
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
    for p in client.position_risk(cfg.symbol):
        amt = float(p.get("positionAmt", 0) or 0)
        if amt:
            print(f"  POS {p['symbol']:<10} amt={amt} entry={p.get('entryPrice')} "
                  f"uPnL={p.get('unRealizedProfit')}")
    live = tsc.live_conn()
    for pos in st.fetch_open(live, [cfg.symbol]):
        print(f"  DB  {pos['symbol']:<10} state={pos['state']} qty={pos.get('qty')} "
              f"entry={pos.get('eff_entry')} cur_sl={pos.get('cur_sl')} signal_time={pos['signal_time']}")
    live.close()


def flatten_positions(cfg, client, conn, *, user_id=None, network=None,
                      reason: str = "killswitch") -> int:
    """Cancel every open order (incl. algo conditionals) and MARKET-close every residual position
    on the account behind `client` for the TALOS symbols, then mark the matching talos_positions
    rows CLOSED. user_id=None = legacy whole-table semantics (the original --flatten); with a
    user_id the DB update touches ONLY that user's rows (the exchange side is inherently
    per-account — the client IS that user's account). Returns the market-closed count."""
    rows = st.fetch_open(conn, None, user_id=user_id, network=network)
    syms = set(cfg.symbols) | {p["symbol"] for p in rows}
    closed = 0
    for sym in sorted(syms):
        try:
            client.cancel_all_open_orders(sym)
        except BinanceError:
            pass
        try:
            client.cancel_all_algo_orders(sym)      # resting SL conditionals (mainnet)
        except BinanceError:
            pass
        amt = 0.0
        for p in client.position_risk(sym):
            if p.get("symbol") == sym:
                amt = float(p.get("positionAmt", 0) or 0)
        if amt:
            side = "SELL" if amt > 0 else "BUY"
            try:
                client.new_order(symbol=sym, side=side, type="MARKET", quantity=abs(amt), reduceOnly="true")
                closed += 1
                print(f"  flattened {sym} ({amt})")
            except BinanceError as e:
                print(f"  ! {sym}: {e}")
    cur = conn.cursor()
    q = ("UPDATE ict_trade.talos_positions SET state=%s, exit_reason=%s, "
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
    notify.alert(f"🟥 TALOS KILLSWITCH --flatten: {closed} {cfg.symbol} position(s) market-closed",
                 chat_id=cfg.telegram_chat_id)
    print(f"  done — {closed} flattened, talos_positions rows marked CLOSED.")


def cmd_flatten_user(cfg, email: str):
    """Flatten ONE user's TALOS account (multi-user mode): their keys, their rows only."""
    sys.path.insert(0, str(_HERE.parents[1] / "users"))
    import store as ustore  # noqa: E402
    live = tsc.live_conn()
    users = [u for u in ustore.load_exec_users(live, "talos") if u.email.lower() == email.lower()]
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
        ustore.audit(live, u.user_id, "kill_executed", {"stream": "talos", "network": u.network,
                                                        "by": "cli", "flattened": total})
    live.close()
    notify.alert(f"🟥 TALOS KILLSWITCH --user {email}: {total} position(s) market-closed",
                 chat_id=cfg.telegram_chat_id)
    print(f"  done — {total} flattened for {email}.")


def cmd_halt():
    """Persistently flip TALOS_EXEC_ENABLED=false in .env (only TALOS no-ops; OPUS unaffected)."""
    env_path = tsc.ENV_PATH
    lines = env_path.read_text().splitlines()
    found = False
    for i, ln in enumerate(lines):
        if ln.strip().startswith("TALOS_EXEC_ENABLED="):
            lines[i] = "TALOS_EXEC_ENABLED=false"
            found = True
    if not found:
        lines.append("TALOS_EXEC_ENABLED=false")
    env_path.write_text("\n".join(lines) + "\n")
    print("  TALOS_EXEC_ENABLED=false written to .env — TALOS executor will no-op until re-enabled.")


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
