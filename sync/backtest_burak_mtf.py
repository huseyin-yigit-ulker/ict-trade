"""Backtest the 'Eth Burak' set with MULTI-TIMEFRAME confirmation (4h -> 1h -> 15m).

Same dual-arm resolution as sync/backtest_burak.py (½TP@EQ+BE vs plain full TP),
CSV-preview ONLY. Signals fire at 15m bar closes (ltf_minutes=15 on the 1m resolver).

Usage:
  python sync/backtest_burak_mtf.py --symbols BTCUSDT ETHUSDT XAUUSDT --year 2026
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import pandas as pd

import trade_sync_common as tsc           # adds backtest/ to sys.path
from ict import config as C               # noqa: E402
from ict.data import fetch_klines         # noqa: E402

from burak_mtf import generate_signals_mtf    # noqa: E402

VERSION = "burak-mtf"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "XAUUSDT"]
WARMUP_HOURS = 1800                       # 90 x 4h range window + pivots + ATR

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)


def _simulate_both(symbol, s, df1m):
    prev = C.PARTIAL_TP_ENABLED
    try:
        C.PARTIAL_TP_ENABLED = True
        part = tsc.simulate(symbol, s.timestamp, s.direction, s.entry, s.stop_loss,
                            s.take_profit_1, df1m=df1m, ltf_minutes=15,
                            expiry_minutes=s.expiry_minutes)
        C.PARTIAL_TP_ENABLED = False
        full = tsc.simulate(symbol, s.timestamp, s.direction, s.entry, s.stop_loss,
                            s.take_profit_1, df1m=df1m, ltf_minutes=15,
                            expiry_minutes=s.expiry_minutes)
    finally:
        C.PARTIAL_TP_ENABLED = prev
    return part, full


def run_symbol(symbol: str, win_start: pd.Timestamp, win_end: pd.Timestamp,
               range_on: str = "4h"):
    end = pd.Timestamp.now(tz="UTC")
    warm = win_start - pd.Timedelta(hours=WARMUP_HOURS)
    df4h = fetch_klines(symbol, "4h", int(warm.timestamp() * 1000), int(end.timestamp() * 1000))
    df1h = tsc.fetch_1h(symbol, warm, end)
    df15 = tsc.fetch_15m(symbol, win_start - pd.Timedelta(days=5), min(win_end, end))
    if df4h.empty or df1h.empty or df15.empty:
        print(f"  {symbol:<10} SKIP (no data)")
        return []
    signals = [s for s in generate_signals_mtf(df4h, df1h, df15, range_on=range_on)
               if win_start <= s.timestamp < win_end]
    df1m = tsc.fetch_1m(symbol, win_start - pd.Timedelta(hours=2), min(win_end, end))

    rows, status_counts = [], {}
    for s in signals:
        part, full = _simulate_both(symbol, s, df1m)
        status_counts[part["status"]] = status_counts.get(part["status"], 0) + 1
        row = tsc.build_row(symbol, s.timestamp, s.direction, s.entry, s.stop_loss,
                            s.take_profit_1, part, strategy=s.strategy,
                            quality=s.quality, confluence_score=s.confluence_score)
        row["version"] = VERSION
        row["pnl_r_full"] = full["pnl_r"]
        row["status_full"] = full["status"]
        row["expiry_minutes"] = s.expiry_minutes
        rows.append(row)
    print(f"  {symbol:<10} 4h={len(df4h)} 1h={len(df1h)} 15m={len(df15)} "
          f"-> {len(signals)} signals {status_counts}")
    return rows


def report(rows: list[dict]):
    res = [r for r in rows if r["status"] in ("closed_tp", "closed_sl")]
    res_full = [r for r in rows if r["status_full"] in ("closed_tp", "closed_sl")]

    def line(rs, key="pnl_r"):
        vals = [r[key] for r in rs if r[key] is not None]
        w = sum(1 for v in vals if v > 0)
        tot = sum(vals); n = len(vals)
        return (f"dolan={n:<3} W/L={w}/{n - w} WR={w / n * 100 if n else 0:4.0f}% "
                f"ortR={tot / n if n else 0:+5.2f} topR={tot:+7.2f}")

    print(f"\n{'=' * 86}")
    for sym in sorted({r['symbol'] for r in rows}):
        sr = [r for r in rows if r['symbol'] == sym]
        print(f"\n{sym}  sinyal={len(sr)} iptal={sum(1 for r in sr if r['status'] == 'cancelled')}")
        print(f"  MTF ½TP@EQ+BE     : {line([r for r in sr if r in res])}")
        print(f"  MTF tam TP        : {line([r for r in sr if r in res_full], 'pnl_r_full')}")
        for st in sorted({r['strategy'] for r in sr}):
            rs = [r for r in sr if r['strategy'] == st and r in res]
            ns = sum(1 for r in sr if r['strategy'] == st)
            print(f"    {st:<14} sinyal={ns:<3} {line(rs)}")
    print(f"\n{'=' * 86}\nTOPLAM MTF (½TP modeli) : {line(res)}")
    print(f"TOPLAM MTF (tam TP)     : {line(res_full, 'pnl_r_full')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="*", default=SYMBOLS)
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--start", type=str, default=None)
    ap.add_argument("--end", type=str, default=None)
    ap.add_argument("--range-tf", choices=["4h", "1h"], default="4h",
                    help="'1h' = hybrid: range/deviation on 1h, only the trigger on 15m")
    args = ap.parse_args()

    now = pd.Timestamp.now(tz="UTC")
    win_start = pd.Timestamp(args.start, tz="UTC") if args.start else pd.Timestamp(f"{args.year}-01-01", tz="UTC")
    win_end = pd.Timestamp(args.end, tz="UTC") if args.end else min(pd.Timestamp(f"{args.year + 1}-01-01", tz="UTC"), now)

    prefix = "burakmtf" if args.range_tf == "4h" else "burakhyb"
    print(f"=== BURAK MTF backtest | range_tf={args.range_tf} -> 1h -> 15m | "
          f"{win_start.date()}..{win_end.date()} | symbols={args.symbols} | CSV-only, no DB ===")

    all_rows = []
    for sym in args.symbols:
        rows = run_symbol(sym, win_start, win_end, range_on=args.range_tf)
        all_rows.extend(rows)
        if rows:
            fp = OUT / f"{prefix}_preview_{args.year}_{sym}.csv"
            with open(fp, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader(); w.writerows(rows)

    if all_rows:
        report(all_rows)
    print(f"\npreviews: {OUT}/{prefix}_preview_{args.year}_*.csv")


if __name__ == "__main__":
    main()
