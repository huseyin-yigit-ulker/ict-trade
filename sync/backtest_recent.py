"""Short-window backtest of ALL THREE strategies over the last 2-3 days, in one run.

This is the quick-iteration sibling of the full-year backfills. It reuses the exact
same engine + building blocks as the year scripts — no separate logic — but over a
trailing N-day window (default 3) instead of a whole calendar year, so a full sweep
finishes in minutes for fast validation or a same-day gap-fill.

Covers each live stream -> its own backtest version tag (kept fully separate):
  - main  : backfill_year.build_symbol_rows         -> version='v1'     (1h,  static-17, B/C/D/E)
  - radar : backfill_dynamic_year (pool->picks->run) -> version='v1-dyn' (1h,  dynamic vol picks)
  - pulse : backfill_15m_year.build_symbol_rows      -> version='v1-15m' (15m, static-17, C-only)

Window: [now - days, now]. Unlike sync_daily.py (which resolves LIVE-emitted signals
and stays "1 day behind"), this REGENERATES signals from the engine over history — so
signals near the window end may still be ACTIVE (unresolved). That's expected and
matches the year backfills; a later run re-resolves them via upsert.

Safety mirrors the year scripts: never deletes in --dry-run; a real (writing) run needs
an explicit --wipe-scope. Deletes are ALWAYS scoped to (version, window) so the three
streams never clobber each other, and rows outside the window are untouched.

Usage:
  # preview all 3 over the last 3 days, no DB writes (writes per-stream CSVs to sync/out/):
  python sync/backtest_recent.py --dry-run
  # just one stream, last 2 days, few symbols:
  python sync/backtest_recent.py --streams pulse --days 2 --symbols BTCUSDT ETHUSDT --dry-run
  # real run: refill only this window for all 3 versions (leaves the rest of history intact):
  python sync/backtest_recent.py --wipe-scope window
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import pandas as pd

import trade_sync_common as tsc          # adds backtest/ to sys.path
import backfill_year as bmain            # main  -> v1
import backfill_dynamic_year as bdyn     # radar -> v1-dyn
import backfill_15m_year as bpulse       # pulse -> v1-15m

STREAMS = ("main", "radar", "pulse")
OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)


def run_main(symbols, win_start, win_end) -> tuple[list[dict], dict]:
    """Static-17 1h backtest (B/C/D/E) -> version='v1'. Reuses backfill_year."""
    rows, agg = [], {}
    for sym in symbols:
        srows, info = bmain.build_symbol_rows(sym, win_start, win_end)
        rows.extend(srows)
        tag = "SKIP" if info["skipped"] else f"{info['signals']} {info.get('status', {})}"
        print(f"    {sym:<12} bars={info['bars']:<5} -> {tag}")
        for r in srows:
            agg[r["status"]] = agg.get(r["status"], 0) + 1
    return rows, agg


def run_pulse(symbols, win_start, win_end) -> tuple[list[dict], dict]:
    """Static-17 15m backtest (C-only) -> version='v1-15m'. Reuses backfill_15m_year."""
    rows, agg = [], {}
    for sym in symbols:
        srows, info = bpulse.build_symbol_rows(sym, win_start.year, win_start, win_end)
        rows.extend(srows)
        tag = "SKIP" if info["skipped"] else f"{info['signals']} {info.get('status', {})}"
        print(f"    {sym:<12} bars={info['bars']:<5} -> {tag}")
        for r in srows:
            agg[r["status"]] = agg.get(r["status"], 0) + 1
    return rows, agg


def run_radar(win_start, win_end, pool_size) -> tuple[list[dict], dict]:
    """Dynamic volume-radar 1h backtest -> version='v1-dyn'. Reuses backfill_dynamic_year."""
    pool = bdyn.fetch_pool(pool_size)
    print(f"    pool: {len(pool)} symbols (top {pool_size} liquid USDT-perps outside the 17)")
    if not pool:
        print("    empty pool — Binance unreachable? skipping radar.")
        return [], {}
    pick_map, log = bdyn.build_pick_map(win_start, win_end, pool)
    print(f"    pick-map: {len(pick_map)} symbols ever picked, {len(log)} pick-events")
    rows, agg = bdyn.build_dynamic_rows(pick_map, win_start, win_end)
    return rows, agg


def wipe_window(conn, version: str, win_start: pd.Timestamp, win_end: pd.Timestamp) -> int:
    """Delete only (version, window) rows — never touches other versions or dates."""
    cur = conn.cursor()
    cur.execute(
        f"DELETE FROM {tsc.TABLE} WHERE version = %s AND signal_time >= %s AND signal_time < %s",
        (version, win_start.to_pydatetime(), win_end.to_pydatetime()))
    n = cur.rowcount
    conn.commit()
    cur.close()
    return n


def dump_preview(name: str, rows: list[dict], win_start, win_end) -> None:
    if not rows:
        return
    fp = OUT / f"recent_{name}_{win_start.date()}_{win_end.date()}.csv"
    with open(fp, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"    [dry-run] preview -> {fp}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3, help="trailing days to backtest (2-3)")
    # Default is MAIN ONLY — radar & pulse streams disabled 2026-06-10 (see dag.py).
    # Pass --streams radar/pulse/all explicitly for a legacy-stream backtest.
    ap.add_argument("--streams", nargs="+", choices=list(STREAMS) + ["all"], default=["main"])
    ap.add_argument("--symbols", nargs="*", default=None,
                    help="override static-17 scope for main/pulse (radar is always dynamic)")
    ap.add_argument("--pool-size", type=int, default=60, help="radar candidate pool size")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--wipe-scope", choices=["none", "window"], default=None,
                    help="real run only: 'window' refills this (version, window); 'none' upserts")
    args = ap.parse_args()

    if not args.dry_run and args.wipe_scope is None:
        raise SystemExit("Real run requires --wipe-scope {none|window} "
                         "(use --dry-run to preview without DB writes).")

    now = pd.Timestamp.now(tz="UTC")
    win_start = now - pd.Timedelta(days=args.days)
    win_end = now
    names = list(STREAMS) if "all" in args.streams else args.streams
    sym_main = args.symbols if args.symbols is not None else bmain.SYMBOLS
    sym_pulse = args.symbols if args.symbols is not None else bpulse.SYMBOLS

    print(f"=== recent backtest | {win_start:%Y-%m-%d %H:%M}..{win_end:%Y-%m-%d %H:%M} UTC "
          f"({args.days}d) | streams={names} | dry_run={args.dry_run} | wipe={args.wipe_scope} ===")

    by_version: dict[str, list[dict]] = {}
    for name in names:
        print(f"  [{name}]")
        if name == "main":
            rows, agg = run_main(sym_main, win_start, win_end)
            ver = tsc.VERSION
        elif name == "pulse":
            rows, agg = run_pulse(sym_pulse, win_start, win_end)
            ver = bpulse.PULSE_VERSION
        else:  # radar
            rows, agg = run_radar(win_start, win_end, args.pool_size)
            ver = bdyn.DYN_VERSION
        print(f"  [{name}] TOTAL {len(rows)} rows version={ver} status={agg}")
        by_version.setdefault(ver, []).extend(rows)
        if args.dry_run:
            dump_preview(name, rows, win_start, win_end)

    all_rows = [r for rows in by_version.values() for r in rows]
    print(f"\nGRAND TOTAL {len(all_rows)} rows across {len(by_version)} versions: "
          f"{ {v: len(r) for v, r in by_version.items()} }")

    if args.dry_run:
        print(f"\n[dry-run] previews in {OUT}/  — no DB writes.")
        return

    conn = tsc.backtest_conn()
    if args.wipe_scope == "window":
        for ver in by_version:
            deleted = wipe_window(conn, ver, win_start, win_end)
            print(f"wiped {deleted} existing {ver} rows in window")
    n = tsc.upsert_rows(conn, all_rows)
    conn.close()
    print(f"upserted {n} rows into {tsc.TABLE}")


if __name__ == "__main__":
    main()
