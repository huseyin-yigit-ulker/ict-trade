"""Backfill a full calendar year of backtest signals into ict_trade.trading_signals.

Runs the SAME engine the live DAG uses (production strategy set B/C/D/E) over each
symbol's 1h history, simulates every target-year signal's TP/SL outcome on 1m bars,
and upserts the rows the dashboard reads (version='v1').

Year-agnostic: pass --year (default current behaviour is 2026). Use it to add 2025,
2024, etc. The dashboard shows signal_time >= 2025-01-01, version='v1', so any backfilled
year from 2025 onward appears automatically.

Safety:
  - Never deletes in --dry-run.
  - A real (writing) run REQUIRES an explicit --wipe-scope:
      year : DELETE rows whose signal_time falls in --year, then refill that year
      all  : DELETE every row, then load only the target year
      none : no delete (upsert only; old rows for the year remain — not recommended)
  - --dry-run writes a per-symbol preview CSV under sync/out/ and touches no DB.
  - wipe-scope 'year' only touches the target year, so adding 2025 leaves 2026 intact.

Usage:
  python sync/backfill_year.py --year 2025 --dry-run               # validate, no DB
  python sync/backfill_year.py --year 2025 --symbols BTCUSDT --dry-run
  python sync/backfill_year.py --year 2025 --wipe-scope year       # real run, refill 2025
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import pandas as pd

import trade_sync_common as tsc           # adds backtest/ to sys.path
from engine import run_engine             # noqa: E402
from ict.strategies import strategy_b, strategy_c, strategy_d, strategy_e  # noqa: E402

DAG_STRATS = [strategy_b, strategy_c, strategy_d, strategy_e]

# Production set — mirrors dag/dag.py SYMBOLS and the dashboard allow-list.
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT",
    "1000PEPEUSDT", "WIFUSDT", "SUIUSDT",
    "NEARUSDT", "FETUSDT", "ADAUSDT", "SUSDT",
    "ARBUSDT", "ORDIUSDT", "ONDOUSDT",
    "XAUUSDT", "XAGUSDT",
    # Stock-backed perps (underlying equities)
    "TSLAUSDT", "NVDAUSDT", "METAUSDT", "GOOGLUSDT",
    "AMZNUSDT", "COINUSDT", "PLTRUSDT", "MSTRUSDT",
]

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)


def build_symbol_rows(symbol: str, year: int) -> tuple[list[dict], dict]:
    """Returns (rows, info). info carries diagnostics for the run report."""
    end = pd.Timestamp.now(tz="UTC")
    year_start = pd.Timestamp(f"{year}-01-01", tz="UTC")
    year_end = pd.Timestamp(f"{year + 1}-01-01", tz="UTC")
    warmup_start = year_start - pd.Timedelta(hours=6000)   # ~250d detector warmup

    df = tsc.fetch_1h(symbol, warmup_start, end)
    if df.empty:
        return [], {"symbol": symbol, "bars": 0, "signals": 0, "skipped": True}

    signals = run_engine(symbol, df, strategies=DAG_STRATS)
    # 1m klines (target year onward) for intrabar-accurate TP/SL/entry-fill resolution.
    # Cap the 1m fetch at "now" so a future year doesn't request non-existent bars.
    m1_end = min(year_end, end)
    df1m = tsc.fetch_1m(symbol, year_start - pd.Timedelta(hours=2), m1_end)
    rows, status_counts = [], {}
    for s in signals:
        if not (year_start <= s.timestamp < year_end):
            continue
        outcome = tsc.simulate(symbol, s.timestamp, s.direction, s.entry,
                               s.stop_loss, s.take_profit_1, df1m=df1m)
        status_counts[outcome["status"]] = status_counts.get(outcome["status"], 0) + 1
        rows.append(tsc.build_row(
            symbol, s.timestamp, s.direction, s.entry, s.stop_loss, s.take_profit_1,
            outcome, strategy=s.strategy, quality=s.quality,
            confluence_score=s.confluence_score))
    return rows, {"symbol": symbol, "bars": len(df), "signals": len(rows),
                  "skipped": False, "status": status_counts}


def wipe(conn, scope: str, year: int) -> int:
    cur = conn.cursor()
    if scope == "all":
        cur.execute(f"DELETE FROM {tsc.TABLE}")
    elif scope == "year":
        cur.execute(
            f"DELETE FROM {tsc.TABLE} WHERE signal_time >= %s AND signal_time < %s",
            (f"{year}-01-01", f"{year + 1}-01-01"))
    n = cur.rowcount
    conn.commit()
    cur.close()
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="*", default=SYMBOLS)
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--wipe-scope", choices=["none", "year", "all"], default=None)
    args = ap.parse_args()

    if not args.dry_run and args.wipe_scope is None:
        raise SystemExit("Real run requires --wipe-scope {none|year|all} "
                         "(use --dry-run to preview without DB writes).")

    print(f"=== {args.year} backfill | symbols={len(args.symbols)} | "
          f"dry_run={args.dry_run} | wipe={args.wipe_scope} ===")

    all_rows, infos = [], []
    for sym in args.symbols:
        rows, info = build_symbol_rows(sym, args.year)
        infos.append(info)
        all_rows.extend(rows)
        tag = "SKIP (no data)" if info["skipped"] else f"{info['signals']} signals {info.get('status', {})}"
        print(f"  {sym:<12} bars={info['bars']:<6} -> {tag}")
        if args.dry_run and rows:
            fp = OUT / f"backfill_preview_{args.year}_{sym}.csv"
            with open(fp, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader(); w.writerows(rows)

    # aggregate report
    agg = {}
    for r in all_rows:
        agg[r["status"]] = agg.get(r["status"], 0) + 1
    skipped = [i["symbol"] for i in infos if i["skipped"]]
    print(f"\nTOTAL rows={len(all_rows)} status={agg}")
    if skipped:
        print(f"SKIPPED symbols (no Binance data): {skipped}")

    if args.dry_run:
        print(f"\n[dry-run] previews in {OUT}/  — no DB writes.")
        return

    conn = tsc.backtest_conn()
    if args.wipe_scope in ("year", "all"):
        deleted = wipe(conn, args.wipe_scope, args.year)
        print(f"wiped {deleted} existing rows (scope={args.wipe_scope}, year={args.year})")
    n = tsc.upsert_rows(conn, all_rows)
    conn.close()
    print(f"upserted {n} rows into {tsc.TABLE}")


if __name__ == "__main__":
    main()
