"""Independent safety sweep (cron #2) — guarantees no open position is ever unprotected.

Runs on its own schedule, separate from the executor, so a stuck/crashed reconciler can't leave
real exchange risk uncovered. For every Binance position with a non-zero amount it verifies:
  1. a managed live_positions row exists (else ORPHAN — flatten + alert),
  2. a protective stop order is live on the book (else flatten + alert),
  3. clock skew vs Binance is within recvWindow,
  4. total open risk is within MAX_TOTAL_RISK_USD.
Read-only unless it finds a breach; LIVE_TRADING_ENABLED=false makes it a pure reporter.
"""
from __future__ import annotations

import sys
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


def main():
    cfg = cfgmod.load_cfg()
    now = pd.Timestamp.now(tz="UTC")
    print(f"=== d30so8c safety sweep @ {now:%Y-%m-%d %H:%M}Z | "
          f"{'ARMED' if cfg.armed else 'REPORT-ONLY'} ===", flush=True)

    client = BinanceFutures(api_key=cfg.api_key, api_secret=cfg.api_secret,
                            base_url=cfg.base_url, proxy=cfg.proxy)
    try:
        off = client.sync_time()
    except BinanceError as e:
        print(f"[fatal] time: {e}")
        return
    if abs(off) > 4000:
        notify.alert(f"⚠️ d30so8c clock skew {off:+d}ms (> recvWindow risk)", chat_id=cfg.telegram_chat_id)
        print(f"  ! clock skew {off:+d}ms")

    if not (cfg.api_key and cfg.api_secret):
        print("  no API keys — report-only, nothing to sweep.")
        return

    live = tsc.live_conn()
    managed = {p["symbol"]: p for p in st.fetch_open(live, None)}

    breaches = 0
    for p in client.position_risk():
        sym = p.get("symbol")
        amt = float(p.get("positionAmt", 0) or 0)
        if amt == 0 or not (sym or "").endswith("USDT"):
            continue
        pos = managed.get(sym)
        open_orders = client.open_orders(sym)
        has_stop = any(o.get("type") in ("STOP_MARKET", "STOP") for o in open_orders)
        if pos is None:
            breaches += 1
            msg = f"🚨 ORPHAN {sym} amt={amt} (no live_positions row)"
            print(f"  {msg}")
            if cfg.armed:
                client.cancel_all_open_orders(sym)
                _market_flatten(client, sym, amt)
            notify.alert(f"🚨 <b>{sym}</b> ORPHAN flattened ({amt})" if cfg.armed
                         else f"🚨 <b>{sym}</b> ORPHAN (report-only)", chat_id=cfg.telegram_chat_id)
        elif not has_stop:
            breaches += 1
            print(f"  ⚠️ {sym} OPEN with NO protective stop")
            if cfg.armed:
                client.cancel_all_open_orders(sym)
                _market_flatten(client, sym, amt)
            notify.alert(f"⚠️ <b>{sym}</b> had no stop — flattened" if cfg.armed
                         else f"⚠️ <b>{sym}</b> no stop (report-only)", chat_id=cfg.telegram_chat_id)

    open_risk = st.total_open_risk_usd(live, cfg.risk_usd)
    if open_risk > cfg.max_total_risk_usd:
        breaches += 1
        notify.alert(f"⚠️ d30so8c open risk ${open_risk:g} > cap ${cfg.max_total_risk_usd:g}",
                     chat_id=cfg.telegram_chat_id)
    live.close()
    print(f"  swept {len(managed)} managed | breaches={breaches} | open risk ${open_risk:g}")


def _market_flatten(client, sym, amt):
    side = "SELL" if amt > 0 else "BUY"
    try:
        client.new_order(symbol=sym, side=side, type="MARKET",
                         quantity=abs(amt), reduceOnly="true")
    except BinanceError as e:
        print(f"  ! flatten {sym}: {e}")


if __name__ == "__main__":
    main()
