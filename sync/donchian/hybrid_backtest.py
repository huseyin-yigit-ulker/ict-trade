"""Donchian HYBRID multi-timeframe validation — EXPERIMENT (no DB write).

Tests whether confirming a base-timeframe Donchian breakout with a HIGHER timeframe's
trend state improves the edge. Key efficiency: a signal's OUTCOME (R) is independent of
any entry filter — the filter only decides whether the trade is TAKEN. So every base
signal is resolved on 1m exactly ONCE; each HTF-confirmation combo is then just a boolean
mask over the same resolved set. One base pass => the whole validation panel for free.

HTF confirmation signals (evaluated causally — only HTF bars CLOSED by the base signal's
fire time are used):
    htf_dir : HTF close on the trade's side of its 55-bar Donchian midline
              (long -> close > midline; short -> close < midline)  [trend alignment]
    htf_er  : HTF Kaufman efficiency ratio >= ER_MIN (0.35)         [regime confirm]

Panel per base tf (15m / 30m), HTFs = 1h + 4h:
    baseline, 1h_dir, 1h_er, 1h_both, 4h_dir, 4h_er, 4h_both,
    1h&4h_dir, 1h&4h_er, full_align (all four)

    python sync/donchian/hybrid_backtest.py --tf 30m --start 2026-01-01
    python sync/donchian/hybrid_backtest.py --tf 15m --start 2026-01-01 --end 2026-06-17
"""
from __future__ import annotations

import os
import sys
import pickle
import argparse
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))
sys.path.insert(0, str(_HERE.parent))
import trade_sync_common as tsc              # noqa: E402
import strategy as strat                     # noqa: E402
from ict import config as C                  # noqa: E402

TF_MIN = {"15m": 15, "30m": 30, "1h": 60, "4h": 240}
CACHE = Path(os.environ.get("DONCHIAN_1M_CACHE", "/tmp/donchian1m_cache"))


def _warmup(tf: str) -> pd.Timedelta:
    return pd.Timedelta(minutes=TF_MIN[tf] * (strat.N_ENTRY + strat.ER_N) * 6)


def _load_1m(sym, start, end):
    cf = CACHE / f"{sym}.pkl"
    if cf.exists():
        return pickle.loads(cf.read_bytes())
    df = tsc.fetch_1m(sym, start - pd.Timedelta(hours=2), end)
    if df is not None and not df.empty:
        CACHE.mkdir(exist_ok=True)
        cf.write_bytes(pickle.dumps(df))
    return df


def _klines(sym, tf, start, end):
    return tsc.fetch_klines(sym, tf, int(start.timestamp() * 1000), int(end.timestamp() * 1000))


def _htf_eval(htf_df: pd.DataFrame, tf: str):
    """Return (close_time_index, er, mid, close) series for causal HTF lookups."""
    bar = pd.Timedelta(minutes=TF_MIN[tf])
    er = strat.eff_ratio(htf_df["close"])
    hi = htf_df["high"].rolling(strat.N_ENTRY).max().shift(1)
    lo = htf_df["low"].rolling(strat.N_ENTRY).min().shift(1)
    mid = (hi + lo) / 2
    close_time = htf_df.index + bar          # the bar's CLOSE timestamp (real availability)
    return close_time, er.values, mid.values, htf_df["close"].values


def _state_at(close_time, er, mid, close, fire_time, direction):
    """HTF (er_ok, dir_agree) as of fire_time. Unknown HTF history -> (False, False)."""
    pos = int(close_time.searchsorted(fire_time, side="right")) - 1
    if pos < 0 or pos >= len(er):
        return False, False
    m = mid[pos]
    er_ok = er[pos] >= strat.ER_MIN if er[pos] == er[pos] else False   # NaN-safe
    if m != m:                                                          # NaN midline
        return er_ok, False
    dir_agree = (close[pos] > m) if direction == "long" else (close[pos] < m)
    return er_ok, bool(dir_agree)


def run_symbol(sym, base_tf, w_start, w_end):
    base_bar = pd.Timedelta(minutes=TF_MIN[base_tf])
    df = _klines(sym, base_tf, w_start - _warmup(base_tf), w_end)
    if df is None or df.empty:
        return []
    sigs = [s for s in strat.generate_signals(df, sym) if w_start <= s.timestamp < w_end]
    if not sigs:
        return []
    df1m = _load_1m(sym, w_start, w_end)
    if df1m is None or df1m.empty:
        return []

    htf = {}
    for h in ("1h", "4h"):
        hdf = _klines(sym, h, w_start - _warmup(h), w_end)
        htf[h] = _htf_eval(hdf, h) if hdf is not None and not hdf.empty else None

    prev = C.PARTIAL_TP_ENABLED
    C.PARTIAL_TP_ENABLED = False
    rows = []
    try:
        for s in sigs:
            res = tsc.simulate(sym, s.timestamp, s.direction, s.entry, s.stop_loss,
                               s.take_profit_1, df1m=df1m, ltf_minutes=TF_MIN[base_tf],
                               expiry_minutes=s.expiry_minutes)
            if res["status"] not in ("closed_tp", "closed_sl") or res["pnl_r"] is None:
                continue                                  # only resolved trades carry R
            fire = s.timestamp + base_bar
            row = {"r": float(res["pnl_r"]), "win": res["status"] == "closed_tp"}
            for h in ("1h", "4h"):
                if htf[h] is None:
                    row[f"{h}_er"], row[f"{h}_dir"] = False, False
                else:
                    ct, er, mid, cl = htf[h]
                    row[f"{h}_er"], row[f"{h}_dir"] = _state_at(ct, er, mid, cl, fire, s.direction)
            rows.append(row)
    finally:
        C.PARTIAL_TP_ENABLED = prev
    return rows


# combo name -> predicate over a resolved row
COMBOS = {
    "baseline":   lambda r: True,
    "1h_dir":     lambda r: r["1h_dir"],
    "1h_er":      lambda r: r["1h_er"],
    "1h_both":    lambda r: r["1h_dir"] and r["1h_er"],
    "4h_dir":     lambda r: r["4h_dir"],
    "4h_er":      lambda r: r["4h_er"],
    "4h_both":    lambda r: r["4h_dir"] and r["4h_er"],
    "1h&4h_dir":  lambda r: r["1h_dir"] and r["4h_dir"],
    "1h&4h_er":   lambda r: r["1h_er"] and r["4h_er"],
    "full_align": lambda r: r["1h_dir"] and r["1h_er"] and r["4h_dir"] and r["4h_er"],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="30m", choices=["15m", "30m"], help="base timeframe")
    ap.add_argument("--symbols", nargs="*", default=strat.SYMBOLS)
    ap.add_argument("--start", default="2026-01-01")
    ap.add_argument("--end", default=None)
    args = ap.parse_args()

    w_start = pd.Timestamp(args.start, tz="UTC")
    w_end = pd.Timestamp(args.end, tz="UTC") if args.end else pd.Timestamp.now(tz="UTC")
    print(f"=== Donchian HYBRID-MTF [{w_start.date()}..{w_end.date()}) base={args.tf} "
          f"| {len(args.symbols)} symbols ===", flush=True)

    allrows = []
    for sym in args.symbols:
        try:
            rs = run_symbol(sym, args.tf, w_start, w_end)
            allrows += rs
            print(f"  {sym:<10} {len(rs):>4} resolved", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {sym}: {e}", flush=True)

    n_base = len(allrows)
    print(f"\n=== PANEL (base={args.tf}, {n_base} resolved base trades) ===")
    print(f"{'combo':<12} {'n':>5} {'%kept':>6} {'WR':>5} {'totR':>8} {'R/trade':>8}")
    print("-" * 50)
    for name, pred in COMBOS.items():
        sel = [r for r in allrows if pred(r)]
        n = len(sel)
        if not n:
            print(f"{name:<12} {0:>5}")
            continue
        tot = sum(r["r"] for r in sel)
        wr = 100 * sum(1 for r in sel if r["win"]) / n
        print(f"{name:<12} {n:>5} {100*n/n_base:>5.0f}% {wr:>4.0f}% {tot:>+8.1f} {tot/n:>+8.3f}")


if __name__ == "__main__":
    main()
