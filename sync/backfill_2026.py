"""One-time backfill: regenerate the year-2026 backtest into ict_trade.trading_signals.

Runs the SAME engine the live DAG uses (production strategy set B/C/D/E) over each
symbol's 1h history, simulates every 2026 signal's TP/SL outcome, and upserts the
rows the dashboard reads.

Safety:
  - Never deletes in --dry-run.
  - A real (writing) run REQUIRES an explicit --wipe-scope:
      2026 : DELETE rows with signal_time in the target year, then refill it
      all  : DELETE every row, then load only the target year
      none : no delete (upsert only; old rows for the year remain — not recommended)
  - --dry-run writes a per-symbol preview CSV under sync/out/ and touches no DB.

Usage:
  python sync/backfill_2026.py --dry-run                 # validate, no DB
  python sync/backfill_2026.py --symbols BTCUSDT --dry-run
  python sync/backfill_2026.py --wipe-scope 2026         # real run, refill 2026
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
    df1m = tsc.fetch_1m(symbol, year_start - pd.Timedelta(hours=2), end)
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
    elif scope == "2026":
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
    ap.add_argument("--wipe-scope", choices=["none", "2026", "all"], default=None)
    args = ap.parse_args()

    if not args.dry_run and args.wipe_scope is None:
        raise SystemExit("Real run requires --wipe-scope {none|2026|all} "
                         "(use --dry-run to preview without DB writes).")

    print(f"=== 2026 backfill | symbols={len(args.symbols)} | "
          f"dry_run={args.dry_run} | wipe={args.wipe_scope} ===")

    all_rows, infos = [], []
    for sym in args.symbols:
        rows, info = build_symbol_rows(sym, args.year)
        infos.append(info)
        all_rows.extend(rows)
        tag = "SKIP (no data)" if info["skipped"] else f"{info['signals']} signals {info.get('status', {})}"
        print(f"  {sym:<12} bars={info['bars']:<6} -> {tag}")
        if args.dry_run and rows:
            fp = OUT / f"backfill_preview_{sym}.csv"
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
    if args.wipe_scope in ("2026", "all"):
        deleted = wipe(conn, args.wipe_scope, args.year)
        print(f"wiped {deleted} existing rows (scope={args.wipe_scope})")
    n = tsc.upsert_rows(conn, all_rows)
    conn.close()
    print(f"upserted {n} rows into {tsc.TABLE}")


if __name__ == "__main__":
    main()
