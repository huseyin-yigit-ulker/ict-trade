"""Independent MIDAS safety sweep (cron #2) — guarantees the gold position is never left unwatched.

Runs on its own schedule, separate from the executor, and is SCOPED to MIDAS's symbol only (XAUUSDT)
so it can never touch the OPUS/Donchian positions (and vice-versa). For the MIDAS symbol it checks:
  1. ORPHAN — a Binance XAUUSDT position with no managed midas_positions row (flatten + alert),
  2. reconciler-freshness — MIDAS's own XAUUSDT snapshot is stale, so the 8h/session time-exits (which
     depend on the cron running) aren't being enforced (alert),
  3. clock skew vs Binance within recvWindow.
Read-only unless it finds a breach; disabled/dry-run makes it a pure reporter.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

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


def _market_flatten(client, sym, amt):
    side = "SELL" if amt > 0 else "BUY"
    try:
        client.new_order(symbol=sym, side=side, type="MARKET", quantity=abs(amt), reduceOnly="true")
    except BinanceError as e:
        print(f"  ! flatten {sym}: {e}")


def main():
    cfg = cfgmod.load_cfg()
    now = pd.Timestamp.now(tz="UTC")
    print(f"=== MIDAS ({cfg.exec_version}) safety sweep @ {now:%Y-%m-%d %H:%M}Z | {cfg.symbol} | "
          f"{'ARMED' if cfg.armed else 'REPORT-ONLY'} ===", flush=True)

    client = BinanceFutures(api_key=cfg.api_key, api_secret=cfg.api_secret,
                            base_url=cfg.base_url, proxy=cfg.proxy)
    try:
        off = client.sync_time()
    except BinanceError as e:
        print(f"[fatal] time: {e}")
        return
    if abs(off) > 4000:
        notify.alert(f"⚠️ MIDAS clock skew {off:+d}ms (> recvWindow risk)", chat_id=cfg.telegram_chat_id)
        print(f"  ! clock skew {off:+d}ms")

    if not (cfg.api_key and cfg.api_secret):
        print("  no API keys — report-only, nothing to sweep.")
        return

    live = tsc.live_conn()
    managed = {p["symbol"]: p for p in st.fetch_open(live, [cfg.symbol])}
    breaches = 0

    # (1) ORPHAN — a MIDAS-symbol position on Binance with no managed midas_positions row.
    amt = 0.0
    for p in client.position_risk(cfg.symbol):
        if p.get("symbol") == cfg.symbol:
            amt = float(p.get("positionAmt", 0) or 0)
    if amt != 0 and managed.get(cfg.symbol) is None:
        breaches += 1
        print(f"  🚨 ORPHAN {cfg.symbol} amt={amt} (no midas_positions row)")
        if cfg.armed:
            try:
                client.cancel_all_open_orders(cfg.symbol)
            except BinanceError:
                pass
            _market_flatten(client, cfg.symbol, amt)
        notify.alert(f"🚨 <b>{cfg.symbol}</b> MIDAS ORPHAN {'flattened' if cfg.armed else '(report-only)'} ({amt})",
                     chat_id=cfg.telegram_chat_id)

    # (2) reconciler-freshness — MIDAS writes its own XAUUSDT snapshot each run (OPUS never trades gold),
    # so this staleness is INDEPENDENT of the OPUS executor. A dead MIDAS cron = unenforced 8h/session exit.
    cur = live.cursor()
    cur.execute("SELECT extract(epoch FROM now() - updated_at) FROM ict_trade.live_account_snapshot "
                "WHERE symbol=%s", (cfg.symbol,))
    row = cur.fetchone(); cur.close()
    stale_s = float(row[0]) if row and row[0] is not None else None
    if managed and stale_s is not None and stale_s > 360:   # >6 min since MIDAS last ran
        breaches += 1
        print(f"  ⚠️ MIDAS reconciler stale {stale_s:.0f}s with {len(managed)} open position(s)")
        notify.alert(f"⚠️ MIDAS executor {stale_s/60:.0f}dk’dır çalışmıyor, {cfg.symbol} pozisyonu korumasız!",
                     chat_id=cfg.telegram_chat_id)

    live.close()
    print(f"  swept {len(managed)} managed | breaches={breaches}")


if __name__ == "__main__":
    main()
