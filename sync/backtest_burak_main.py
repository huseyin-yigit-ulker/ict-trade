"""Run BOTH Burak arms (single-TF 1h + hybrid 1h-range/15m-trigger) over the MAIN
production symbol list for a year — fetching each symbol's data ONCE.

Per symbol: fetch 1h/4h/15m/1m once, generate signals with burak_strategy (single-TF)
and burak_mtf range_on='1h' (hybrid), resolve every signal under both exit models
(½TP@EQ+BE and plain full TP) on 1m bars. CSV previews only — no DB writes:
  out/burak_preview_<year>_<SYM>.csv     (single-TF)
  out/burakhyb_preview_<year>_<SYM>.csv  (hybrid)

Usage:
  python sync/backtest_burak_main.py --year 2026
  python sync/backtest_burak_main.py --symbols BTCUSDT XAGUSDT --year 2026
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import pandas as pd

import trade_sync_common as tsc           # adds backtest/ to sys.path
from ict import config as C               # noqa: E402
from ict.data import fetch_klines         # noqa: E402

from burak_strategy import generate_signals       # noqa: E402
from burak_mtf import generate_signals_mtf        # noqa: E402

from backfill_year import SYMBOLS         # MAIN production list (36 symbols)

WARMUP_HOURS = 1800
OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)


def _simulate_both(symbol, s, df1m, ltf_minutes):
    prev = C.PARTIAL_TP_ENABLED
    try:
        C.PARTIAL_TP_ENABLED = True
        part = tsc.simulate(symbol, s.timestamp, s.direction, s.entry, s.stop_loss,
                            s.take_profit_1, df1m=df1m, ltf_minutes=ltf_minutes,
                            expiry_minutes=s.expiry_minutes)
        C.PARTIAL_TP_ENABLED = False
        full = tsc.simulate(symbol, s.timestamp, s.direction, s.entry, s.stop_loss,
                            s.take_profit_1, df1m=df1m, ltf_minutes=ltf_minutes,
                            expiry_minutes=s.expiry_minutes)
    finally:
        C.PARTIAL_TP_ENABLED = prev
    return part, full


def _rows_for(symbol, signals, df1m, ltf_minutes, version):
    rows, counts = [], {}
    for s in signals:
        part, full = _simulate_both(symbol, s, df1m, ltf_minutes)
        counts[part["status"]] = counts.get(part["status"], 0) + 1
        row = tsc.build_row(symbol, s.timestamp, s.direction, s.entry, s.stop_loss,
                            s.take_profit_1, part, strategy=s.strategy,
                            quality=s.quality, confluence_score=s.confluence_score)
        row["version"] = version
        row["pnl_r_full"] = full["pnl_r"]
        row["status_full"] = full["status"]
        row["expiry_minutes"] = s.expiry_minutes
        rows.append(row)
    return rows, counts


def _write(prefix, year, symbol, rows):
    if not rows:
        return
    fp = OUT / f"{prefix}_preview_{year}_{symbol}.csv"
    with open(fp, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)


def run_symbol(symbol, win_start, win_end, year):
    end = pd.Timestamp.now(tz="UTC")
    warm = win_start - pd.Timedelta(hours=WARMUP_HOURS)
    df1h = tsc.fetch_1h(symbol, warm, end)
    if df1h.empty:
        print(f"  {symbol:<13} SKIP (no data)", flush=True)
        return [], []
    df4h = fetch_klines(symbol, "4h", int(warm.timestamp() * 1000), int(end.timestamp() * 1000))
    df15 = tsc.fetch_15m(symbol, win_start - pd.Timedelta(days=5), min(win_end, end))
    df1m = tsc.fetch_1m(symbol, win_start - pd.Timedelta(hours=2), min(win_end, end))

    sigs_1tf = [s for s in generate_signals(df1h) if win_start <= s.timestamp < win_end]
    sigs_hyb = []
    if not df4h.empty and not df15.empty:
        sigs_hyb = [s for s in generate_signals_mtf(df4h, df1h, df15, range_on="1h")
                    if win_start <= s.timestamp < win_end]

    rows_1tf, c1 = _rows_for(symbol, sigs_1tf, df1m, 60, "burak")
    rows_hyb, c2 = _rows_for(symbol, sigs_hyb, df1m, 15, "burak-hyb")
    _write("burak", year, symbol, rows_1tf)
    _write("burakhyb", year, symbol, rows_hyb)
    print(f"  {symbol:<13} 1h={len(df1h):<6} tekTF: {len(sigs_1tf):>3} sinyal {c1} | "
          f"hibrit: {len(sigs_hyb):>3} sinyal {c2}", flush=True)
    return rows_1tf, rows_hyb


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

    print(f"=== BURAK MAIN-list backtest (tekTF + hibrit) | {win_start.date()}..{win_end.date()} "
          f"| {len(args.symbols)} sembol | CSV-only, no DB ===", flush=True)

    tot1, toth = [], []
    for sym in args.symbols:
        r1, rh = run_symbol(sym, win_start, win_end, args.year)
        tot1.extend(r1); toth.extend(rh)

    def summ(rows, key="pnl_r", skey="status"):
        res = [r for r in rows if r[skey] in ("closed_tp", "closed_sl") and r[key] is not None]
        w = sum(1 for r in res if r[key] > 0)
        tot = sum(r[key] for r in res)
        n = len(res)
        return (f"sinyal={len(rows)} dolan={n} W/L={w}/{n - w} "
                f"WR={w / n * 100 if n else 0:.0f}% ortR={tot / n if n else 0:+.2f} topR={tot:+.2f}")

    print(f"\nTOPLAM tekTF  ½TP  : {summ(tot1)}")
    print(f"TOPLAM tekTF  tamTP: {summ(tot1, 'pnl_r_full', 'status_full')}")
    print(f"TOPLAM hibrit ½TP  : {summ(toth)}")
    print(f"TOPLAM hibrit tamTP: {summ(toth, 'pnl_r_full', 'status_full')}")
    print(f"\npreviews: {OUT}/burak_preview_{args.year}_*.csv + burakhyb_preview_{args.year}_*.csv")


if __name__ == "__main__":
    main()
