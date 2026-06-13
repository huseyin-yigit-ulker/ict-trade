"""Backfill the RANGE stream — Burak's RANGE_DEV (range-deviation fade) only.

The 2026 regime audit (the RANGE_DEV-by-band study) found this range-fade earns its
edge OUTSIDE deep chop: light +25R, mid +15R, strong ~flat, but deep-chop (4h ER<0.20)
LOSES (−5R) because the range just whipsaws there. So the RANGE stream =

  • technique : RANGE_DEV only (backtest/burak_strategy.generate_signals), dropping
                OB_PULLBACK / IC / FVG_TREND (those were net-negative at scale).
  • exit      : FULL TP (½TP+BE sinks RANGE_DEV's total R: +37R -> −11R) — so NO ½TP.
  • gate      : keep only signals fired with 4h ER >= 0.20 (skip the deep-chop band
                where the fade whipsaws). regime.is_choppy() == the dropped band.
  • resolve   : 1m bars via tsc.simulate (fees in), like every other stream.
  • version   : 'range' in ict_trade.trading_signals (backtest stream; no live scanner
                yet — emission would need a dedicated DAG job).

Safety: real run needs --wipe-scope {year|all|none} (wipes ONLY version='range').
Usage:
  python sync/backfill_range.py --year 2026 --dry-run
  python sync/backfill_range.py --year 2026 --wipe-scope year
"""
from __future__ import annotations

import argparse

import pandas as pd

import trade_sync_common as tsc           # adds backtest/ to sys.path
from ict import config as C               # noqa: E402
import regime                             # noqa: E402
from burak_strategy import generate_signals   # noqa: E402

VERSION = "range"
WARMUP_HOURS = 1500
ER_MIN_KEEP = regime.LIGHT_LO             # 0.20 — drop only the deep-chop band

# Universe = where RANGE_DEV actually range-fades. The 2026 run showed +41.6R over
# these 29, but XRP/DOGE/LINK/AVAX were −35R (they dump/trend, don't fade — and were
# already net-negative for the core strategies), so they're EXCLUDED. In-sample
# universe choice — validate forward.
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "1000PEPEUSDT", "WIFUSDT", "SUIUSDT",
    "NEARUSDT", "FETUSDT", "ADAUSDT", "SUSDT", "ARBUSDT", "ORDIUSDT", "ONDOUSDT",
    "XAUUSDT", "XAGUSDT",
    "NVDAUSDT", "METAUSDT", "AMZNUSDT", "COINUSDT", "MSTRUSDT", "CRCLUSDT", "PLTRUSDT",
    "TSLAUSDT", "INTCUSDT", "HOODUSDT", "MSFTUSDT", "AVGOUSDT", "BABAUSDT",
]


def run_symbol(symbol, w_start, w_end, er):
    end = pd.Timestamp.now(tz="UTC")
    df = tsc.fetch_1h(symbol, w_start - pd.Timedelta(hours=WARMUP_HOURS), end)
    if df is None or df.empty:
        print(f"  {symbol:<12} SKIP (no data)", flush=True)
        return []
    sigs = [s for s in generate_signals(df)
            if s.strategy == "RANGE_DEV" and w_start <= s.timestamp < w_end]
    # deep-chop gate: keep only ER >= 0.20 at the signal's 4h bar (missing -> keep)
    kept = []
    for s in sigs:
        v = regime._er_at(er, s.timestamp)
        if v is None or v >= ER_MIN_KEEP:
            kept.append(s)
    dropped = len(sigs) - len(kept)
    if not kept:
        print(f"  {symbol:<12} {len(sigs)} RANGE_DEV -> 0 kept (chop-dropped {dropped})", flush=True)
        return []
    df1m = tsc.fetch_1m(symbol, w_start - pd.Timedelta(hours=2), min(w_end, end))
    rows, sc = [], {}
    prev = C.PARTIAL_TP_ENABLED
    try:
        C.PARTIAL_TP_ENABLED = False                       # FULL TP only
        for s in kept:
            res = tsc.simulate(symbol, s.timestamp, s.direction, s.entry, s.stop_loss,
                               s.take_profit_1, df1m=df1m, expiry_minutes=s.expiry_minutes)
            sc[res["status"]] = sc.get(res["status"], 0) + 1
            row = tsc.build_row(symbol, s.timestamp, s.direction, s.entry, s.stop_loss,
                                s.take_profit_1, res, strategy=s.strategy,
                                quality=s.quality, confluence_score=s.confluence_score)
            row["version"] = VERSION
            rows.append(row)
    finally:
        C.PARTIAL_TP_ENABLED = prev
    print(f"  {symbol:<12} {len(sigs)} RANGE_DEV -> {len(kept)} kept (chop-dropped {dropped}) {sc}", flush=True)
    return rows


def tot(rows):
    res = [r for r in rows if r["status"] in ("closed_tp", "closed_sl") and r["pnl_r"] is not None]
    w = sum(1 for r in res if r["pnl_r"] > 0)
    return len(res), w, sum(float(r["pnl_r"]) for r in res)


def wipe(conn, scope, w_start, w_end):
    cur = conn.cursor()
    if scope == "all":
        cur.execute(f"DELETE FROM {tsc.TABLE} WHERE version=%s", (VERSION,))
    elif scope == "year":
        cur.execute(f"DELETE FROM {tsc.TABLE} WHERE version=%s AND signal_time>=%s AND signal_time<%s",
                    (VERSION, w_start.to_pydatetime(), w_end.to_pydatetime()))
    n = cur.rowcount
    conn.commit(); cur.close()
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--symbols", nargs="*", default=SYMBOLS)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--wipe-scope", choices=["none", "year", "all"], default=None)
    args = ap.parse_args()
    if not args.dry_run and args.wipe_scope is None:
        raise SystemExit("Real run requires --wipe-scope {none|year|all} (or --dry-run).")

    now = pd.Timestamp.now(tz="UTC")
    w_start = pd.Timestamp(f"{args.year}-01-01", tz="UTC")
    w_end = min(pd.Timestamp(f"{args.year + 1}-01-01", tz="UTC"), now)
    er_start = w_start - pd.Timedelta(days=30)
    print(f"=== RANGE backfill {args.year} | RANGE_DEV full-TP | ER>={ER_MIN_KEEP} "
          f"| {len(args.symbols)} symbols | dry_run={args.dry_run} ===", flush=True)

    all_rows = []
    for sym in args.symbols:
        try:
            er = regime.build_er(sym, er_start, now)
            all_rows += run_symbol(sym, w_start, w_end, er)
        except Exception as e:
            print(f"  ! {sym}: {e}", flush=True)

    n, w, r = tot(all_rows)
    print(f"\nRANGE total: resolved={n} WR={w/n*100 if n else 0:.0f}% topR={r:+.1f} "
          f"(rows={len(all_rows)})", flush=True)
    if args.dry_run:
        print(f"[dry-run] {len(all_rows)} 'range' rows would upsert — no DB write.")
        return
    conn = tsc.backtest_conn()
    if args.wipe_scope in ("year", "all"):
        print(f"wiped {wipe(conn, args.wipe_scope, w_start, w_end)} existing 'range' rows")
    up = tsc.upsert_rows(conn, all_rows)
    conn.close()
    print(f"upserted {up} 'range' rows into {tsc.TABLE}")


if __name__ == "__main__":
    main()
