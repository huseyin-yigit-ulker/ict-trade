"""Operator kill-switch CLI for the MIDAS (gold XAUUSDT) live bridge — scoped to MIDAS only.

    python sync/midas_exec/killswitch.py --status     # account + XAUUSDT position/orders + DB rows
    python sync/midas_exec/killswitch.py --flatten     # cancel XAUUSDT orders + market-close + rows CLOSED
    python sync/midas_exec/killswitch.py --halt        # set MIDAS_EXEC_ENABLED=false in .env (MIDAS-only)

--flatten is the emergency stop for MIDAS: it cancels every open order on the MIDAS symbol and
market-closes any residual, then marks the midas_positions rows CLOSED — it does NOT touch OPUS.
--halt flips the MIDAS-scoped flag (MIDAS_EXEC_ENABLED=false) so only MIDAS no-ops; use the OPUS
killswitch --halt (LIVE_TRADING_ENABLED=false) to stop everything.
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


def cmd_flatten(cfg):
    if not (cfg.api_key and cfg.api_secret):
        raise SystemExit("no API keys — cannot flatten.")
    client = _client(cfg)
    client.sync_time()
    live = tsc.live_conn()
    sym = cfg.symbol
    try:
        client.cancel_all_open_orders(sym)
    except BinanceError:
        pass
    try:
        client.cancel_all_algo_orders(sym)
    except BinanceError:
        pass
    amt = 0.0
    for p in client.position_risk(sym):
        if p.get("symbol") == sym:
            amt = float(p.get("positionAmt", 0) or 0)
    closed = 0
    if amt:
        side = "SELL" if amt > 0 else "BUY"
        try:
            client.new_order(symbol=sym, side=side, type="MARKET", quantity=abs(amt), reduceOnly="true")
            closed = 1
            print(f"  flattened {sym} ({amt})")
        except BinanceError as e:
            print(f"  ! {sym}: {e}")
    cur = live.cursor()
    cur.execute("UPDATE ict_trade.midas_positions SET state=%s, exit_reason='killswitch', "
                "exit_time=current_timestamp WHERE state = ANY(%s)",
                (st.CLOSED, list(st.OPEN_STATES)))
    live.commit()
    cur.close()
    live.close()
    notify.alert(f"🟥 MIDAS KILLSWITCH --flatten: {closed} {sym} position(s) market-closed",
                 chat_id=cfg.telegram_chat_id)
    print(f"  done — {closed} flattened, midas_positions rows marked CLOSED.")


def cmd_halt():
    """Persistently flip MIDAS_EXEC_ENABLED=false in .env (only MIDAS no-ops; OPUS unaffected)."""
    env_path = tsc.ENV_PATH
    lines = env_path.read_text().splitlines()
    found = False
    for i, ln in enumerate(lines):
        if ln.strip().startswith("MIDAS_EXEC_ENABLED="):
            lines[i] = "MIDAS_EXEC_ENABLED=false"
            found = True
    if not found:
        lines.append("MIDAS_EXEC_ENABLED=false")
    env_path.write_text("\n".join(lines) + "\n")
    print("  MIDAS_EXEC_ENABLED=false written to .env — MIDAS executor will no-op until re-enabled.")


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--status", action="store_true")
    g.add_argument("--flatten", action="store_true")
    g.add_argument("--halt", action="store_true")
    args = ap.parse_args()
    if args.halt:
        cmd_halt()
        return
    cfg = cfgmod.load_cfg()
    if args.status:
        cmd_status(cfg)
    elif args.flatten:
        cmd_flatten(cfg)


if __name__ == "__main__":
    main()
