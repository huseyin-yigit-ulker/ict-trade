"""BTC/ETH live-signal -> backtest validation.

Three independent checks per live signal (from ict_trade.signals):

1. PARITY (only meaningful for current-engine '1h/live' rows):
   Re-run the SAME engine the backtest uses, on a DAG-style 6000-bar window
   ending at the signal's bar, restricted to the production strategy set
   [B,C,D,E]. If it emits a signal at that bar matching direction +
   entry/SL/TP (rel tol 1e-4), the live signal is reproduced by the backtest
   engine -> "occurs in backtest".

2. FULL-HISTORY BACKTEST presence: run the engine over the whole 1h history
   and check whether the matched trade also appears there (context).

3. TP/SL OUTCOME: walk forward on 15m klines (entry limit fill within 180min,
   then TP vs SL; same-bar tie -> SL, conservative). Reported for ALL signals.

Provenance note: only mode='live' rows (1h/4h, strategy populated) come from
the engine the backtest mirrors. NULL/Weekday/Weekend rows are older pipelines
on different timeframes (15m/30m) -> parity is N/A; only outcome is computed.
"""
from __future__ import annotations
import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]   # backtest/
sys.path.insert(0, str(ROOT))
import db  # validation/db.py is on sys.path via cwd
from engine import run_engine as bt_run_engine
from ict.strategies import strategy_b, strategy_c, strategy_d, strategy_e

DAG_STRATS = [strategy_b, strategy_c, strategy_d, strategy_e]
WARMUP = 6000          # must match dag.py
REL_TOL = 1e-4         # entry/sl/tp relative match tolerance
FILL_WINDOW_MIN = 180  # engine EXPIRY_MINUTES: limit must fill within 3h of being actionable

CACHE = Path(__file__).resolve().parent / "klines"
OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)
SYMBOLS = ["BTCUSDT", "ETHUSDT"]


def load_klines():
    k = {}
    for sym in SYMBOLS:
        k[(sym, "1h")] = pd.read_pickle(CACHE / f"{sym}_1h.pkl")
        k[(sym, "15m")] = pd.read_pickle(CACHE / f"{sym}_15m.pkl")
    return k


def load_live_signals() -> list[dict]:
    c = db.live_conn()
    cur = c.cursor()
    cur.execute("""
        SELECT id, symbol, signal_time, created_at, direction, entry, sl, tp,
               coalesce(mode,'<null>') AS mode, strategy, quality, confluence_score,
               ltf_timeframe, htf_timeframe
        FROM ict_trade.signals
        WHERE symbol IN ('BTCUSDT','ETHUSDT')
        ORDER BY symbol, signal_time
    """)
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    c.close()
    for r in rows:
        r["direction"] = r["direction"].lower()
        for f in ("entry", "sl", "tp"):
            r[f] = float(r[f]) if r[f] is not None else None
        # signal_time tz-aware UTC
        r["signal_time"] = pd.Timestamp(r["signal_time"]).tz_convert("UTC")
    return rows


def relclose(a: float, b: float, tol: float = REL_TOL) -> bool:
    if a is None or b is None:
        return False
    denom = max(abs(a), abs(b), 1e-9)
    return abs(a - b) / denom <= tol


# ----------------------------------------------------------------------------
# 1) PARITY: DAG-style windowed re-run (1h only)
# ----------------------------------------------------------------------------

def parity_windowed(sig: dict, df1h: pd.DataFrame) -> dict:
    ts = sig["signal_time"].floor("h")
    if ts not in df1h.index:
        return {"parity": "no_bar", "detail": f"bar {ts} not in klines"}
    bar_idx = df1h.index.get_loc(ts)
    if bar_idx < WARMUP - 1:
        return {"parity": "no_warmup", "detail": f"only {bar_idx+1} bars before"}
    sl0 = bar_idx - WARMUP + 1
    win = df1h.iloc[sl0:bar_idx + 1].copy()
    last = len(win) - 1
    emitted = bt_run_engine(sig["symbol"], win, start_index=last, end_index=last,
                            strategies=DAG_STRATS)
    same_dir = [s for s in emitted if s.direction == sig["direction"]]
    # exact price match
    for s in same_dir:
        if (relclose(s.entry, sig["entry"]) and relclose(s.stop_loss, sig["sl"])
                and relclose(s.take_profit_1, sig["tp"])):
            de = abs(s.entry - sig["entry"]) / max(abs(sig["entry"]), 1e-9)
            return {"parity": "reproduced", "bt_strategy": s.strategy,
                    "bt_entry": s.entry, "bt_sl": s.stop_loss, "bt_tp": s.take_profit_1,
                    "max_rel_diff": round(max(de,
                        abs(s.stop_loss - sig["sl"]) / max(abs(sig["sl"]), 1e-9),
                        abs(s.take_profit_1 - sig["tp"]) / max(abs(sig["tp"]), 1e-9)), 8)}
    if same_dir:
        s = same_dir[0]
        return {"parity": "diff_levels", "bt_strategy": s.strategy,
                "bt_entry": s.entry, "bt_sl": s.stop_loss, "bt_tp": s.take_profit_1}
    if emitted:
        return {"parity": "opp_dir", "detail": f"engine emitted {emitted[0].direction} only"}
    return {"parity": "no_signal", "detail": "engine emitted nothing at this bar"}


# ----------------------------------------------------------------------------
# 2) FULL-HISTORY backtest index
# ----------------------------------------------------------------------------

def full_backtest_index(df1h: pd.DataFrame, symbol: str) -> dict:
    sigs = bt_run_engine(symbol, df1h, strategies=DAG_STRATS)
    idx = {}
    for s in sigs:
        idx.setdefault((s.timestamp, s.direction), []).append(s)
    return idx


# ----------------------------------------------------------------------------
# 3) OUTCOME on 15m
# ----------------------------------------------------------------------------

@dataclass
class Outcome:
    status: str
    pnl_r: Optional[float] = None
    pnl_pct: Optional[float] = None
    bars_to_exit: Optional[int] = None
    entry_time: Optional[pd.Timestamp] = None
    exit_time: Optional[pd.Timestamp] = None


def outcome_15m(sig: dict, df15: pd.DataFrame) -> Outcome:
    direction, entry, sl, tp = sig["direction"], sig["entry"], sig["sl"], sig["tp"]
    if None in (entry, sl, tp):
        return Outcome("no_prices")
    # known_at: live (1h) actionable at bar close = signal_time + 1h; legacy at insert wall-clock
    if sig["mode"] == "live":
        known_at = sig["signal_time"].floor("h") + pd.Timedelta(hours=1)
    else:
        known_at = sig["signal_time"].ceil("15min")
    pos = df15.index.searchsorted(known_at)
    n = len(df15)
    if pos >= n:
        return Outcome("future")  # signal newer than our klines
    fill_bars = int(FILL_WINDOW_MIN / 15)
    risk = abs(entry - sl)
    if risk <= 0:
        return Outcome("bad_risk")

    # phase 1: wait for entry fill (limit), watching for invalidation
    entry_idx = None
    for i in range(pos, min(pos + fill_bars, n)):
        bar = df15.iloc[i]
        hi, lo = bar["high"], bar["low"]
        if direction == "long":
            entry_touched = lo <= entry
            tp_touched = hi >= tp
            sl_touched = lo <= sl
        else:
            entry_touched = hi >= entry
            tp_touched = lo <= tp
            sl_touched = hi >= sl
        if not entry_touched and (tp_touched or sl_touched):
            return Outcome("invalidated", bars_to_exit=i - pos, exit_time=df15.index[i])
        if entry_touched:
            entry_idx = i
            # same-bar resolution
            if sl_touched and tp_touched:
                return _exit(sig, "sl_hit", entry_idx, i, sl, risk, df15)
            if direction == "long":
                if hi >= tp:
                    return _exit(sig, "tp_hit", entry_idx, i, tp, risk, df15)
                if lo <= sl:
                    return _exit(sig, "sl_hit", entry_idx, i, sl, risk, df15)
            else:
                if lo <= tp:
                    return _exit(sig, "tp_hit", entry_idx, i, tp, risk, df15)
                if hi >= sl:
                    return _exit(sig, "sl_hit", entry_idx, i, sl, risk, df15)
            break
    if entry_idx is None:
        return Outcome("expired")  # limit never filled within window

    # phase 2: filled, walk to TP/SL until end of data
    for j in range(entry_idx + 1, n):
        bar = df15.iloc[j]
        hi, lo = bar["high"], bar["low"]
        if direction == "long":
            tp_touched, sl_touched = hi >= tp, lo <= sl
        else:
            tp_touched, sl_touched = lo <= tp, hi >= sl
        if tp_touched and sl_touched:
            return _exit(sig, "sl_hit", entry_idx, j, sl, risk, df15)
        if tp_touched:
            return _exit(sig, "tp_hit", entry_idx, j, tp, risk, df15)
        if sl_touched:
            return _exit(sig, "sl_hit", entry_idx, j, sl, risk, df15)
    return Outcome("active", entry_time=df15.index[entry_idx])


def _exit(sig, status, entry_idx, exit_idx, exit_price, risk, df15) -> Outcome:
    direction, entry = sig["direction"], sig["entry"]
    sign = 1 if direction == "long" else -1
    pnl_r = (abs(exit_price - entry) / risk) if status == "tp_hit" else -1.0
    pnl_pct = (exit_price - entry) / entry * 100 * sign
    return Outcome(status, pnl_r=round(pnl_r, 4), pnl_pct=round(pnl_pct, 4),
                   bars_to_exit=exit_idx - entry_idx,
                   entry_time=df15.index[entry_idx], exit_time=df15.index[exit_idx])


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------

def main():
    klines = load_klines()
    sigs = load_live_signals()
    print(f"loaded {len(sigs)} BTC/ETH live signals")

    # full-history backtest indices
    bt_idx = {}
    for sym in SYMBOLS:
        bt_idx[sym] = full_backtest_index(klines[(sym, "1h")], sym)
        print(f"  full-history backtest {sym}: {sum(len(v) for v in bt_idx[sym].values())} signals")

    rows = []
    for sig in sigs:
        sym = sig["symbol"]
        df1h = klines[(sym, "1h")]
        df15 = klines[(sym, "15m")]

        # parity only for current-engine 1h signals
        is_live = sig["mode"] == "live"
        par = parity_windowed(sig, df1h) if is_live else {"parity": "n/a_legacy"}

        # full-history presence
        ts_h = sig["signal_time"].floor("h")
        fh = bt_idx[sym].get((ts_h, sig["direction"]), [])
        fh_match = any(relclose(s.entry, sig["entry"]) and relclose(s.stop_loss, sig["sl"])
                       and relclose(s.take_profit_1, sig["tp"]) for s in fh) if fh else False

        out = outcome_15m(sig, df15)

        rows.append({
            "id": sig["id"], "symbol": sym, "mode": sig["mode"],
            "signal_time": sig["signal_time"].isoformat(),
            "direction": sig["direction"], "ltf": sig["ltf_timeframe"], "htf": sig["htf_timeframe"],
            "strategy": sig["strategy"], "confluence": sig["confluence_score"],
            "entry": sig["entry"], "sl": sig["sl"], "tp": sig["tp"],
            "parity": par["parity"],
            "parity_maxreldiff": par.get("max_rel_diff"),
            "fullhist_present": fh_match,
            "outcome": out.status, "pnl_r": out.pnl_r, "pnl_pct": out.pnl_pct,
            "bars_to_exit": out.bars_to_exit,
            "entry_time": out.entry_time.isoformat() if out.entry_time is not None else None,
            "exit_time": out.exit_time.isoformat() if out.exit_time is not None else None,
        })

    # write CSV
    csv_path = OUT / "btc_eth_signal_validation.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {csv_path} ({len(rows)} rows)")

    _summary(rows)
    return rows


def _summary(rows):
    def agg(subset, label):
        n = len(subset)
        if not n:
            return
        print(f"\n### {label}  (n={n})")
        # parity
        par = {}
        for r in subset:
            par[r["parity"]] = par.get(r["parity"], 0) + 1
        print("  parity:", dict(sorted(par.items(), key=lambda x: -x[1])))
        repo = sum(1 for r in subset if r["parity"] == "reproduced")
        live_n = sum(1 for r in subset if r["mode"] == "live")
        if live_n:
            print(f"  reproduced/live = {repo}/{live_n} = {repo/live_n*100:.1f}%")
        fh = sum(1 for r in subset if r["fullhist_present"])
        print(f"  full-history present: {fh}/{n}")
        # outcomes
        oc = {}
        for r in subset:
            oc[r["outcome"]] = oc.get(r["outcome"], 0) + 1
        print("  outcomes:", dict(sorted(oc.items(), key=lambda x: -x[1])))
        closed = [r for r in subset if r["outcome"] in ("tp_hit", "sl_hit")]
        if closed:
            wins = sum(1 for r in closed if r["outcome"] == "tp_hit")
            total_r = sum(r["pnl_r"] or 0 for r in closed)
            print(f"  closed={len(closed)} win_rate={wins/len(closed)*100:.1f}% "
                  f"total_R={total_r:.2f} expectancy_R={total_r/len(closed):.3f}")

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    agg(rows, "ALL BTC+ETH")
    for sym in SYMBOLS:
        agg([r for r in rows if r["symbol"] == sym], sym)
    print("\n--- by provenance (mode) ---")
    for m in ("live", "Weekday", "Weekend", "<null>"):
        agg([r for r in rows if r["mode"] == m], f"mode={m}")


if __name__ == "__main__":
    main()
