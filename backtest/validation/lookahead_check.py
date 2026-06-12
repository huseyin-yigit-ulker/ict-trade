"""No-lookahead (future-data) check for the signal engine, via stepped truncation.

Premise: if signal generation at bar i uses ONLY bars <= i, then running the engine
on a dataframe truncated at any cut bar t must reproduce EXACTLY the full-history
run's signals with bar_index <= t — same bars, directions, strategies and prices.

  - a signal present in the full run but MISSING from the truncated run means the
    emission needed future bars (classic look-ahead);
  - a signal present in the truncated run but ABSENT from the full one means future
    bars SUPPRESS emissions (e.g. filtering on a `mitigated` flag without checking
    when the mitigation happened) — equally a look-ahead bug.

Both runs share the same fetch (bar indices align) and the same config, so any
diff is future-data influence by construction. Covers v1 AND v2 signal paths
(v2 = same engine, subtractive config; v3/v4 reuse v1/v2 signals verbatim — their
½TP exit resolution walks FORWARD from the signal close on 1m bars, which is the
simulation itself, not look-ahead).

Usage:
  python backtest/validation/lookahead_check.py                 # BTC/ETH/XAU, 2026
  python backtest/validation/lookahead_check.py --symbols BTCUSDT --year 2026
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))          # backtest/  (engine, ict)

from ict.data import fetch_klines                  # noqa: E402
from ict.strategies import (                       # noqa: E402
    strategy_b, strategy_c, strategy_d, strategy_e,
)
from engine import run_engine                      # noqa: E402

DAG_STRATS = [strategy_b, strategy_c, strategy_d, strategy_e]   # v1 superset (v2 ⊂ v1)
WARMUP_HOURS = 6000
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "XAUUSDT"]


def sig_key(s) -> tuple:
    return (s.timestamp.isoformat(), s.direction, s.strategy,
            f"{s.entry:.8g}", f"{s.stop_loss:.8g}", f"{s.take_profit_1:.8g}")


def month_end_cuts(df: pd.DataFrame, win_start: pd.Timestamp) -> list[int]:
    """Bar index of the last bar before each month boundary inside the window."""
    cuts = []
    m = pd.Timestamp(win_start.year, win_start.month, 1, tz="UTC") + pd.offsets.MonthBegin(1)
    while m < df.index[-1]:
        pos = int(df.index.searchsorted(m)) - 1
        if pos > 0 and df.index[pos] >= win_start:
            cuts.append(pos)
        m += pd.offsets.MonthBegin(1)
    return cuts


def check_symbol(symbol: str, win_start: pd.Timestamp) -> int:
    end = pd.Timestamp.now(tz="UTC")
    start = win_start - pd.Timedelta(hours=WARMUP_HOURS)
    df = fetch_klines(symbol, "1h", int(start.timestamp() * 1000), int(end.timestamp() * 1000))
    if df.empty:
        print(f"  {symbol:<10} SKIP (no data)")
        return 0
    full = run_engine(symbol, df, strategies=DAG_STRATS)
    full_keys = {sig_key(s): s.bar_index for s in full}
    cuts = month_end_cuts(df, win_start)
    print(f"  {symbol:<10} bars={len(df)} full_signals={len(full)} cuts={len(cuts)}", flush=True)

    bad = 0
    for t in cuts:
        trunc = run_engine(symbol, df.iloc[:t + 1], strategies=DAG_STRATS)
        tk = {sig_key(s) for s in trunc}
        fk = {k for k, bi in full_keys.items() if bi <= t}
        missing = fk - tk          # full emitted, truncated can't -> needs future bars
        extra = tk - fk            # truncated emits, full suppressed -> future bars veto
        status = "OK" if not missing and not extra else "FAIL"
        print(f"    cut@{df.index[t]:%Y-%m-%d %H:%M} (bar {t}): "
              f"full≤t={len(fk)} trunc={len(tk)} missing={len(missing)} extra={len(extra)} {status}",
              flush=True)
        for k in sorted(missing)[:5]:
            print(f"      MISSING (lookahead-emit): {k}")
        for k in sorted(extra)[:5]:
            print(f"      EXTRA (lookahead-veto) : {k}")
        bad += len(missing) + len(extra)
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="*", default=DEFAULT_SYMBOLS)
    ap.add_argument("--year", type=int, default=2026)
    args = ap.parse_args()

    win_start = pd.Timestamp(f"{args.year}-01-01", tz="UTC")
    print(f"=== NO-LOOKAHEAD stepped-truncation check | window {args.year} | "
          f"strats=B/C/D/E | {args.symbols} ===", flush=True)
    total_bad = 0
    for sym in args.symbols:
        total_bad += check_symbol(sym, win_start)

    print("\nRESULT:", "PASS — sinyal üretimi gelecek veri görmüyor" if total_bad == 0
          else f"FAIL — {total_bad} fark (yukarıda)")
    sys.exit(0 if total_bad == 0 else 1)


if __name__ == "__main__":
    main()
