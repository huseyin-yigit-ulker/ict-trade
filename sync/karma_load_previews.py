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


def rows_from_csv(path: str, version: str) -> list[dict]:
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
        row["version"] = version          # enforce, never trust the CSV cell
        rows.append(row)
    return rows


# preview file prefix -> trading_signals version tag
SOURCES = [("karma_preview", "karma"), ("karma_half_preview", "karma_half")]


def wipe(conn, scope: str, win_start: pd.Timestamp, win_end: pd.Timestamp, version: str) -> int:
    cur = conn.cursor()
    if scope == "all":
        cur.execute(f"DELETE FROM {tsc.TABLE} WHERE version = %s", (version,))
    elif scope == "year":
        cur.execute(
            f"DELETE FROM {tsc.TABLE} WHERE version = %s "
            f"AND signal_time >= %s AND signal_time < %s",
            (version, win_start.to_pydatetime(), win_end.to_pydatetime()))
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

    win_start = pd.Timestamp(f"{args.year}-01-01", tz="UTC")
    win_end = pd.Timestamp(f"{args.year + 1}-01-01", tz="UTC")

    # collect rows per version from the matching preview files
    by_version = {}
    for prefix, version in SOURCES:
        paths = sorted(glob.glob(str(OUT / f"{prefix}_{args.year}_*.csv")))
        rows = [r for p in paths for r in rows_from_csv(p, version)]
        if rows:
            by_version[version] = rows
        resolved = sum(1 for r in rows if r["status"] in ("closed_tp", "closed_sl"))
        print(f"  {version:<11} {len(paths)} dosya · {len(rows)} satır ({resolved} dolan)")
    if not by_version:
        raise SystemExit(f"No karma previews in {OUT} for {args.year}.")

    all_rows = [r for rows in by_version.values() for r in rows]
    print(f"=== KARMA preview load | {args.year} | toplam {len(all_rows)} satır | dry_run={args.dry_run} ===")

    if args.dry_run:
        print(f"[dry-run] {len(all_rows)} satır upsert edilecekti — DB'ye yazılmadı.")
        return

    conn = tsc.backtest_conn()
    for version in by_version:
        if args.wipe_scope in ("year", "all"):
            deleted = wipe(conn, args.wipe_scope, win_start, win_end, version)
            print(f"wiped {deleted} mevcut {version} satırı (scope={args.wipe_scope})")
    n = tsc.upsert_rows(conn, all_rows)
    cur = conn.cursor()
    cur.execute(f"SELECT version, count(*) FROM {tsc.TABLE} WHERE version = ANY(%s) GROUP BY version",
                (list(by_version.keys()),))
    totals = {v: c for v, c in cur.fetchall()}
    cur.close()
    conn.close()
    print(f"upserted {n} satır -> {tsc.TABLE} | DB toplam: {totals}")


if __name__ == "__main__":
    main()
