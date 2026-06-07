"""One-time (re-runnable) GEOMETRY backfill for the backtest table.

Populates ``trading_signals.context -> 'geometry'`` for existing rows (v1 + v1-dyn)
so the chart can draw the FVG / Order-Block / swept-liquidity / BOS that framed each
entry. NON-DESTRUCTIVE: entry/sl/tp/status/pnl_r are never touched — only ``context``.

How it stays correct: re-runs the SAME deterministic engine (build_geometry is purely
additive, so signals reproduce identically) and matches each regenerated signal to its
DB row by (symbol, signal_time, trade_type, version), then merges the geometry into the
row's ``context`` JSONB. Rows with no matching engine signal simply keep NULL geometry.

Also ensures the ``context`` JSONB column exists on BOTH the backtest table and the live
``ict_trade.signals`` table (ADD COLUMN IF NOT EXISTS) so the live DAG can write geometry.

Usage:
  python sync/backfill_geometry.py --dry-run                # no writes; report match rates
  python sync/backfill_geometry.py --versions v1            # ALTER + populate v1 only
  python sync/backfill_geometry.py                          # ALTER + populate v1 and v1-dyn
  python sync/backfill_geometry.py --symbols BTCUSDT ETHUSDT
"""
from __future__ import annotations

import argparse
from datetime import timezone

import pandas as pd
from psycopg2.extras import Json

import trade_sync_common as tsc           # adds backtest/ to sys.path
from engine import run_engine             # noqa: E402
from ict.strategies import strategy_b, strategy_c, strategy_d, strategy_e  # noqa: E402

DAG_STRATS = [strategy_b, strategy_c, strategy_d, strategy_e]
VERSIONS = ["v1", "v1-dyn"]
WARMUP_HOURS = 6000                       # ~250d detector warmup (mirrors backfill_year)
HISTORY_START = pd.Timestamp("2025-01-01", tz="UTC")


def _epoch(dt) -> int:
    """Bar timestamp -> unix seconds, tolerant of naive (assume UTC) vs aware datetimes."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _trade_type(direction: str) -> str:
    return "BUY" if direction.upper() in ("LONG", "BUY") else "SELL"


def ensure_columns():
    """ADD COLUMN IF NOT EXISTS context JSONB on both DBs (idempotent)."""
    for conn_fn, table in ((tsc.backtest_conn, tsc.TABLE), (tsc.live_conn, "ict_trade.signals")):
        conn = conn_fn()
        cur = conn.cursor()
        cur.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS context JSONB")
        conn.commit()
        cur.close()
        conn.close()
        print(f"  ensured context JSONB column on {table}")


def symbols_for_version(conn, version, only=None):
    cur = conn.cursor()
    cur.execute(f"SELECT DISTINCT symbol FROM {tsc.TABLE} WHERE version = %s", (version,))
    syms = sorted(r[0] for r in cur.fetchall())
    cur.close()
    return [s for s in syms if (only is None or s in only)]


def geometry_for_symbol(symbol):
    """Re-run the engine over full history; return {(epoch, trade_type): geometry_dict}."""
    end = pd.Timestamp.now(tz="UTC")
    df = tsc.fetch_1h(symbol, HISTORY_START - pd.Timedelta(hours=WARMUP_HOURS), end)
    if df.empty:
        return {}
    out = {}
    for s in run_engine(symbol, df, strategies=DAG_STRATS):
        geo = (s.context or {}).get("geometry")
        if geo:
            out[(_epoch(s.timestamp.to_pydatetime()), _trade_type(s.direction))] = geo
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--versions", nargs="*", default=VERSIONS)
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    only = set(args.symbols) if args.symbols else None

    print(f"=== geometry backfill | versions={args.versions} | "
          f"dry_run={args.dry_run} ===")
    if not args.dry_run:
        ensure_columns()

    conn = tsc.backtest_conn()
    grand_rows = grand_matched = 0
    for version in args.versions:
        syms = symbols_for_version(conn, version, only)
        print(f"\n--- version={version} | symbols={len(syms)} ---")
        for sym in syms:
            cur = conn.cursor()
            cur.execute(
                f"SELECT signal_time, trade_type FROM {tsc.TABLE} "
                f"WHERE version = %s AND symbol = %s", (version, sym))
            db_rows = cur.fetchall()
            cur.close()

            geo_map = geometry_for_symbol(sym)
            updates = []
            for (st, tt) in db_rows:
                geo = geo_map.get((_epoch(st), tt))
                if geo is not None:
                    updates.append((Json({"geometry": geo}), sym, st, tt, version))

            grand_rows += len(db_rows)
            grand_matched += len(updates)
            print(f"  {sym:<12} db={len(db_rows):<4} engine={len(geo_map):<4} "
                  f"matched={len(updates)}")

            if updates and not args.dry_run:
                ucur = conn.cursor()
                ucur.executemany(
                    f"UPDATE {tsc.TABLE} "
                    f"SET context = coalesce(context, '{{}}'::jsonb) || %s "
                    f"WHERE symbol = %s AND signal_time = %s AND trade_type = %s "
                    f"AND version = %s",
                    updates)
                conn.commit()
                ucur.close()
    conn.close()

    rate = (grand_matched / grand_rows * 100) if grand_rows else 0
    print(f"\nTOTAL db_rows={grand_rows} matched={grand_matched} ({rate:.1f}%) "
          f"{'[DRY-RUN, no writes]' if args.dry_run else '[updated]'}")


if __name__ == "__main__":
    main()
