"""Backtest the experimental 'Eth Burak' price-action stream (backtest/burak_strategy.py).

CSV-preview ONLY — never touches the DB. Each signal is resolved twice on 1m bars:
  arm A (the faithful Burak model): partial-TP — 50% off at 50% of entry->TP (~EQ)
        + stop to breakeven (ict/config PARTIAL_TP_*, toggled per call);
  arm B (reference): same entries, plain full TP/SL — isolates how much of the result
        comes from his trade management vs the entries themselves.

Usage:
  python sync/backtest_burak.py --symbols BTCUSDT ETHUSDT XAUUSDT --year 2026
  python sync/backtest_burak.py --symbols BTCUSDT --start 2026-05-01 --end 2026-06-01
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import pandas as pd

import trade_sync_common as tsc           # adds backtest/ to sys.path
from ict import config as C               # noqa: E402

from burak_strategy import generate_signals   # noqa: E402

VERSION = "burak"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "XAUUSDT"]
WARMUP_HOURS = 1500                       # range window + pivots + ATR warmup

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)


def _simulate_both(symbol, s, df1m):
    """Resolve one signal under both exit models (partial flag is process-local)."""
    prev = C.PARTIAL_TP_ENABLED
    try:
        C.PARTIAL_TP_ENABLED = True
        part = tsc.simulate(symbol, s.timestamp, s.direction, s.entry, s.stop_loss,
                            s.take_profit_1, df1m=df1m, expiry_minutes=s.expiry_minutes)
        C.PARTIAL_TP_ENABLED = False
        full = tsc.simulate(symbol, s.timestamp, s.direction, s.entry, s.stop_loss,
                            s.take_profit_1, df1m=df1m, expiry_minutes=s.expiry_minutes)
    finally:
        C.PARTIAL_TP_ENABLED = prev
    return part, full


def run_symbol(symbol: str, win_start: pd.Timestamp, win_end: pd.Timestamp):
    end = pd.Timestamp.now(tz="UTC")
    df = tsc.fetch_1h(symbol, win_start - pd.Timedelta(hours=WARMUP_HOURS), end)
    if df.empty:
        print(f"  {symbol:<10} SKIP (no data)")
        return []
    signals = [s for s in generate_signals(df) if win_start <= s.timestamp < win_end]
    df1m = tsc.fetch_1m(symbol, win_start - pd.Timedelta(hours=2), min(win_end, end))

    rows, status_counts = [], {}
    for s in signals:
        part, full = _simulate_both(symbol, s, df1m)
        status_counts[part["status"]] = status_counts.get(part["status"], 0) + 1
        row = tsc.build_row(symbol, s.timestamp, s.direction, s.entry, s.stop_loss,
                            s.take_profit_1, part, strategy=s.strategy,
                            quality=s.quality, confluence_score=s.confluence_score)
        row["version"] = VERSION
        row["pnl_r_full"] = full["pnl_r"]         # reference arm (no partial/BE)
        row["status_full"] = full["status"]
        row["expiry_minutes"] = s.expiry_minutes
        rows.append(row)
    print(f"  {symbol:<10} bars={len(df):<6} -> {len(signals)} signals {status_counts}")
    return rows


def report(rows: list[dict]):
    res = [r for r in rows if r["status"] in ("closed_tp", "closed_sl")]
    res_full = [r for r in rows if r["status_full"] in ("closed_tp", "closed_sl")]

    def line(rs, key="pnl_r"):
        vals = [r[key] for r in rs if r[key] is not None]
        w = sum(1 for v in vals if v > 0)
        tot = sum(vals)
        n = len(vals)
        return (f"dolan={n:<3} W/L={w}/{n - w} WR={w / n * 100 if n else 0:4.0f}% "
                f"ortR={tot / n if n else 0:+5.2f} topR={tot:+7.2f}")

    print(f"\n{'=' * 86}")
    for sym in sorted({r['symbol'] for r in rows}):
        sr = [r for r in rows if r['symbol'] == sym]
        print(f"\n{sym}  sinyal={len(sr)} iptal={sum(1 for r in sr if r['status'] == 'cancelled')}")
        print(f"  BURAK (½TP@EQ+BE) : {line([r for r in sr if r in res])}")
        print(f"  referans (tam TP) : {line([r for r in sr if r in res_full], 'pnl_r_full')}")
        for st in sorted({r['strategy'] for r in sr}):
            rs = [r for r in sr if r['strategy'] == st and r in res]
            ns = sum(1 for r in sr if r['strategy'] == st)
            print(f"    {st:<14} sinyal={ns:<3} {line(rs)}")
    print(f"\n{'=' * 86}\nTOPLAM (BURAK ½TP modeli) : {line(res)}")
    print(f"TOPLAM (referans tam TP)  : {line(res_full, 'pnl_r_full')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="*", default=SYMBOLS)
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--start", type=str, default=None)
    ap.add_argument("--end", type=str, default=None)
    args = ap.parse_args()

    now = pd.Timestamp.now(tz="UTC")
    win_start = pd.Timestamp(args.start, tz="UTC") if args.start else pd.Timestamp(f"{args.year}-01-01", tz="UTC")
    win_end = pd.Timestamp(args.end, tz="UTC") if args.end else min(pd.Timestamp(f"{args.year + 1}-01-01", tz="UTC"), now)

    print(f"=== BURAK price-action backtest | {win_start.date()}..{win_end.date()} | "
          f"symbols={args.symbols} | CSV-only, no DB ===")

    all_rows = []
    for sym in args.symbols:
        rows = run_symbol(sym, win_start, win_end)
        all_rows.extend(rows)
        if rows:
            fp = OUT / f"burak_preview_{args.year}_{sym}.csv"
            with open(fp, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader(); w.writerows(rows)

    if all_rows:
        report(all_rows)
    print(f"\npreviews: {OUT}/burak_preview_{args.year}_*.csv")


if __name__ == "__main__":
    main()
