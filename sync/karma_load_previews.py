"""Load the KARMA preview CSVs (sync/out/karma_preview_<year>_*.csv) into
trading_signals as version='karma' — without re-running the ~70min backtest.

The previews are the authoritative per-symbol winning-cell rows already produced
by backtest_karma.py (CSV-only mode); their pnl_r/status hold the CHOSEN cell's
outcome. This script just type-coerces and upserts them, so the dashboard's KARMA
Backtest view gets the full-year history. Identical end-state to
`backtest_karma.py --year <Y> --wipe-scope year`, minus the recompute/refetch.

Safety: mirrors the backfills — a real run needs --wipe-scope {none|year|all};
wipe touches ONLY version='karma'. --dry-run previews counts with no DB writes.

Usage:
  python sync/karma_load_previews.py --year 2026 --dry-run
  python sync/karma_load_previews.py --year 2026 --wipe-scope year
"""
from __future__ import annotations

import argparse
import glob
import math
from pathlib import Path

import pandas as pd

import trade_sync_common as tsc

OUT = Path(__file__).resolve().parent / "out"

# trading_signals numeric / nullable columns needing explicit coercion.
_FLOAT_COLS = ("signal_price", "entry_price", "sl_price", "tp_price",
               "exit_price", "pnl_r")
_TS_COLS = ("signal_time", "real_entry_time", "exit_time")


def _clean(v):
    """NaN / '' -> None; leave everything else as-is."""
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, str) and v.strip() == "":
        return None
    return v


def rows_from_csv(path: str) -> list[dict]:
    df = pd.read_csv(path)
    rows = []
    for rec in df.to_dict("records"):
        row = {c: _clean(rec.get(c)) for c in tsc._COLS}
        # type discipline so psycopg2 adapts to the right column types
        for c in _FLOAT_COLS:
            row[c] = None if row[c] is None else float(row[c])
        for c in _TS_COLS:
            row[c] = None if row[c] is None else str(row[c])
        row["confluence_score"] = None if row["confluence_score"] is None else int(float(row["confluence_score"]))
        row["version"] = "karma"          # enforce, never trust the CSV cell
        rows.append(row)
    return rows


def wipe(conn, scope: str, win_start: pd.Timestamp, win_end: pd.Timestamp) -> int:
    cur = conn.cursor()
    if scope == "all":
        cur.execute(f"DELETE FROM {tsc.TABLE} WHERE version = 'karma'")
    elif scope == "year":
        cur.execute(
            f"DELETE FROM {tsc.TABLE} WHERE version = 'karma' "
            f"AND signal_time >= %s AND signal_time < %s",
            (win_start.to_pydatetime(), win_end.to_pydatetime()))
    n = cur.rowcount
    conn.commit()
    cur.close()
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--wipe-scope", choices=["none", "year", "all"], default=None)
    args = ap.parse_args()

    if not args.dry_run and args.wipe_scope is None:
        raise SystemExit("Real run requires --wipe-scope {none|year|all} (or --dry-run).")

    paths = sorted(glob.glob(str(OUT / f"karma_preview_{args.year}_*.csv")))
    if not paths:
        raise SystemExit(f"No karma previews in {OUT} for {args.year}.")

    all_rows, per_sym = [], {}
    for p in paths:
        rows = rows_from_csv(p)
        sym = Path(p).stem.replace(f"karma_preview_{args.year}_", "")
        per_sym[sym] = len(rows)
        all_rows.extend(rows)

    resolved = sum(1 for r in all_rows if r["status"] in ("closed_tp", "closed_sl"))
    print(f"=== KARMA preview load | {args.year} | {len(paths)} dosya | "
          f"{len(all_rows)} satır ({resolved} dolan) | dry_run={args.dry_run} ===")
    for sym in sorted(per_sym):
        print(f"  {sym:<13} {per_sym[sym]}")

    win_start = pd.Timestamp(f"{args.year}-01-01", tz="UTC")
    win_end = pd.Timestamp(f"{args.year + 1}-01-01", tz="UTC")

    if args.dry_run:
        print(f"\n[dry-run] {len(all_rows)} satır upsert edilecekti — DB'ye yazılmadı.")
        return

    conn = tsc.backtest_conn()
    if args.wipe_scope in ("year", "all"):
        deleted = wipe(conn, args.wipe_scope, win_start, win_end)
        print(f"wiped {deleted} mevcut karma satırı (scope={args.wipe_scope})")
    n = tsc.upsert_rows(conn, all_rows)
    cur = conn.cursor()
    cur.execute(f"SELECT count(*) FROM {tsc.TABLE} WHERE version='karma'")
    total = cur.fetchone()[0]
    cur.close()
    conn.close()
    print(f"upserted {n} karma satırı -> {tsc.TABLE} | DB'deki toplam karma: {total}")


if __name__ == "__main__":
    main()
