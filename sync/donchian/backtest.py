"""Donchian strategy — BACKTEST submodule.

Backfills historical Donchian(55) breakout signals and their fixed SL+TP outcomes into
the backtest results DB under version='donchian'. Signals are generated on 1h klines and
resolved intrabar on 1m (tsc.simulate), exactly like the other backtest streams
(backfill_range.py is the sibling pattern).

    python sync/donchian/backtest.py --dry-run                       # per-symbol R, no write
    python sync/donchian/backtest.py --dry-run --symbols BTCUSDT XAUUSDT
    python sync/donchian/backtest.py --apply                         # wipe version='donchian', write
    python sync/donchian/backtest.py --apply --start 2025-06-16 --end 2026-06-16
"""
from __future__ import annotations

import os
import sys
import pickle
import argparse
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))   # sync/        -> trade_sync_common
sys.path.insert(0, str(_HERE.parent))        # sync/donchian -> strategy
import trade_sync_common as tsc              # noqa: E402
import strategy as strat                     # noqa: E402
from ict import config as C                  # noqa: E402  (path added by tsc)

DEFAULT_START = pd.Timestamp("2025-06-16", tz="UTC")
WARMUP = pd.Timedelta(hours=2200)            # enough 1h history for the 55-bar channel + ER
CACHE = Path(os.environ.get("DONCHIAN_1M_CACHE", "/tmp/donchian1m_cache"))  # per-window override


def _load_1m(sym: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    cf = CACHE / f"{sym}.pkl"
    if cf.exists():
        return pickle.loads(cf.read_bytes())
    df = tsc.fetch_1m(sym, start - pd.Timedelta(hours=2), end)
    if df is not None and not df.empty:
        CACHE.mkdir(exist_ok=True)
        cf.write_bytes(pickle.dumps(df))
    return df


def run_symbol(sym: str, w_start: pd.Timestamp, w_end: pd.Timestamp):
    """Return (rows, resolved_n, total_r) for one symbol — full-TP exit model."""
    df = tsc.fetch_1h(sym, w_start - WARMUP, w_end)
    if df is None or df.empty:
        print(f"  {sym:<10} SKIP (no 1h)", flush=True)
        return [], 0, 0.0
    sigs = [s for s in strat.generate_signals(df, sym) if w_start <= s.timestamp < w_end]
    if not sigs:
        print(f"  {sym:<10} 0 breakouts", flush=True)
        return [], 0, 0.0
    df1m = _load_1m(sym, w_start, w_end)
    if df1m is None or df1m.empty:
        print(f"  {sym:<10} SKIP (no 1m)", flush=True)
        return [], 0, 0.0

    prev = C.PARTIAL_TP_ENABLED
    C.PARTIAL_TP_ENABLED = False              # full-TP stream
    rows, resolved, tot = [], 0, 0.0
    try:
        for s in sigs:
            res = tsc.simulate(sym, s.timestamp, s.direction, s.entry, s.stop_loss,
                               s.take_profit_1, df1m=df1m, expiry_minutes=s.expiry_minutes)
            row = tsc.build_row(sym, s.timestamp, s.direction, s.entry, s.stop_loss,
                                s.take_profit_1, res, strategy=s.strategy,
                                quality=s.quality, confluence_score=s.confluence_score)
            row["version"] = strat.VERSION
            rows.append(row)
            if res["status"] in ("closed_tp", "closed_sl") and res["pnl_r"] is not None:
                resolved += 1
                tot += float(res["pnl_r"])
    finally:
        C.PARTIAL_TP_ENABLED = prev
    wr = 100 * sum(1 for r in rows
                   if r["status"] == "closed_tp") / resolved if resolved else 0
    print(f"  {sym:<10} {len(sigs):>3} breakouts -> resolved {resolved:>3} "
          f"WR={wr:>3.0f}%  totR={tot:+6.1f}", flush=True)
    return rows, resolved, tot


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    ap.add_argument("--symbols", nargs="*", default=strat.SYMBOLS)
    ap.add_argument("--start", default=None, help="YYYY-MM-DD (default 2025-06-16)")
    ap.add_argument("--end", default=None, help="YYYY-MM-DD (default now)")
    args = ap.parse_args()

    w_start = pd.Timestamp(args.start, tz="UTC") if args.start else DEFAULT_START
    w_end = pd.Timestamp(args.end, tz="UTC") if args.end else pd.Timestamp.now(tz="UTC")
    print(f"=== Donchian backtest [{w_start.date()} .. {w_end.date()}) "
          f"| {len(args.symbols)} symbols | version='{strat.VERSION}' ===", flush=True)

    all_rows, tot_n, tot_r = [], 0, 0.0
    for sym in args.symbols:
        try:
            rows, n, r = run_symbol(sym, w_start, w_end)
            all_rows += rows
            tot_n += n
            tot_r += r
        except Exception as e:  # noqa: BLE001
            print(f"  ! {sym}: {e}", flush=True)

    wr = 100 * sum(1 for r in all_rows if r["status"] == "closed_tp") / tot_n if tot_n else 0
    print(f"\n=== TOTAL resolved={tot_n}  WR={wr:.0f}%  totR={tot_r:+.1f} ===")

    if args.dry_run:
        print("[dry-run] no DB write.")
        return

    conn = tsc.backtest_conn()
    cur = conn.cursor()
    cur.execute(f"DELETE FROM {tsc.TABLE} WHERE version=%s", (strat.VERSION,))
    print(f"  wiped {cur.rowcount} existing '{strat.VERSION}' rows")
    conn.commit()
    cur.close()
    n = tsc.upsert_rows(conn, all_rows)
    conn.close()
    print(f"  upserted {n} '{strat.VERSION}' rows into {tsc.TABLE}")


if __name__ == "__main__":
    main()
