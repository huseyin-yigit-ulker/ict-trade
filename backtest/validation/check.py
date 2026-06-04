"""Credibility cross-checks:
(a) my 15m outcome sim vs the engine's OWN backtester (1h) for the 37 live signals
(b) reverse coverage: in the live system's active window, how many backtest
    signals did the live pipeline FAIL to emit?
"""
from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import db
from engine import run_engine as bt_run_engine
from backtester import simulate_signal, TradeStatus
from ict.strategies import strategy_b, strategy_c, strategy_d, strategy_e

DAG_STRATS = [strategy_b, strategy_c, strategy_d, strategy_e]
REL = 1e-4
CACHE = Path(__file__).resolve().parent / "klines"
SYMBOLS = ["BTCUSDT", "ETHUSDT"]


def relclose(a, b, tol=REL):
    if a is None or b is None:
        return False
    return abs(a - b) / max(abs(a), abs(b), 1e-9) <= tol


def load_live():
    c = db.live_conn(); cur = c.cursor()
    cur.execute("""SELECT symbol, signal_time, direction, entry, sl, tp, mode
                   FROM ict_trade.signals WHERE symbol IN ('BTCUSDT','ETHUSDT')
                   ORDER BY symbol, signal_time""")
    rows = [{"symbol": r[0], "ts": pd.Timestamp(r[1]).tz_convert("UTC"),
             "dir": r[2].lower(), "entry": float(r[3]), "sl": float(r[4]),
             "tp": float(r[5]), "mode": r[6]} for r in cur.fetchall()]
    c.close()
    return rows


def main():
    live = load_live()
    live_by_sym = {s: [r for r in live if r["symbol"] == s] for s in SYMBOLS}

    # full-history backtest signals + their engine-native outcomes
    for sym in SYMBOLS:
        df1h = pd.read_pickle(CACHE / f"{sym}_1h.pkl")
        bt = bt_run_engine(sym, df1h, strategies=DAG_STRATS)
        bt_in_window = {}
        # map for matching
        bt_by_key = {}
        for s in bt:
            bt_by_key.setdefault((s.timestamp, s.direction), []).append(s)

        live_rows = live_by_sym[sym]
        live_live = [r for r in live_rows if r["mode"] == "live"]
        lo = min(r["ts"] for r in live_live)
        hi = max(r["ts"] for r in live_live)
        print("=" * 64)
        print(f"{sym}: live-active window {lo} .. {hi}")
        print(f"  full-history backtest signals total: {len(bt)}")

        bt_window = [s for s in bt if lo <= s.timestamp <= hi]
        print(f"  backtest signals INSIDE live window: {len(bt_window)}")
        print(f"  live('live'-mode) signals in window: {len(live_live)}")

        # reverse coverage: backtest signals not matched by any live row
        missed = []
        for s in bt_window:
            matched = any(r["dir"] == s.direction and relclose(r["entry"], s.entry)
                          and relclose(r["sl"], s.stop_loss) and relclose(r["tp"], s.take_profit_1)
                          for r in live_live)
            if not matched:
                missed.append(s)
        print(f"  backtest signals in window MISSED by live: {len(missed)}")
        for s in missed[:8]:
            print(f"     - {s.timestamp} {s.direction} {s.strategy} entry={s.entry:.2f}")

        # (a) cross-check outcomes: engine backtester (1h) for matched live signals
        agree = disagree = 0
        rows_dbg = []
        for r in live_live:
            key = (r["ts"].floor("h"), r["dir"])
            cands = bt_by_key.get(key, [])
            match = next((s for s in cands if relclose(s.entry, r["entry"])
                          and relclose(s.sl if hasattr(s, "sl") else s.stop_loss, r["sl"])), None)
            if match is None:
                continue
            res = simulate_signal(match, df1h)
            rows_dbg.append((r["ts"], r["dir"], res.status.value, res.pnl_r))
        # tally engine-native outcomes
        from collections import Counter
        cnt = Counter(x[2] for x in rows_dbg)
        print(f"  engine-native (1h backtester) outcomes for matched live signals: {dict(cnt)}")
        closed = [x for x in rows_dbg if x[2] in ("tp_hit", "sl_hit")]
        if closed:
            wins = sum(1 for x in closed if x[2] == "tp_hit")
            tr = sum((x[3] or 0) for x in closed)
            print(f"    closed={len(closed)} winrate={wins/len(closed)*100:.0f}% totalR={tr:.2f}")


if __name__ == "__main__":
    main()
