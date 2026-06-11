"""Backtest MAIN under the PARTIAL-TP + BREAKEVEN exit model -> trading_signals with
version='v3' (the dashboard's "MAIN ½TP" stream).

SAME signals as the v1 main backfill (strategy set B/C/D/E, same static universe, same
base D-exclusion) — the ONLY difference is the exit model: ict/config.PARTIAL_TP_ENABLED
is flipped on process-locally, so backtester.simulate_signal scales out
PARTIAL_TP_CLOSE_FRAC of each filled trade at PARTIAL_TP_TRIGGER_FRAC of the distance
entry->TP1 and pulls the stop to breakeven; the remainder rides to TP1. So v1 vs v3 is a
clean A/B on the exit model alone (entry/SL/TP geometry is identical).

The flag is set BEFORE importing the engine and only mutates this process's config; the
live DAG and the v1/v2 backfills run in their own processes off the unmodified config.

2026-06-11 A/B (sync/experiment_partial.py, same signals, resolved trades): the partial
model RAISES win rate (~+9pt) but LOWERS total R (~-49R on the 2026 Jan-Jun set) — the
edge lives in the big runners, which the 3R cap + breakeven stop give back. Surfaced as
its own dashboard stream so the tradeoff is visible; NOT the production default.

Safety: never deletes in --dry-run; a real run needs --wipe-scope {year|all|none}.
  wipe touches ONLY version='v3' rows, so v1/v2/v1-dyn/v1-15m are untouched.

Usage:
  python sync/backfill_v3_year.py --symbols BTCUSDT --start 2026-05-01 --end 2026-06-06 --dry-run
  python sync/backfill_v3_year.py --year 2026 --wipe-scope year
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import pandas as pd

import trade_sync_common as tsc           # adds backtest/ to sys.path
from ict import config as C               # noqa: E402

# --- exit-model change (process-local; v1/live unaffected) ---------------------
V3_VERSION = "v3"
C.PARTIAL_TP_ENABLED = True               # scale out half at half-distance + breakeven

from engine import run_engine                                              # noqa: E402
from ict.strategies import strategy_b, strategy_c, strategy_d, strategy_e  # noqa: E402

DAG_STRATS = [strategy_b, strategy_c, strategy_d, strategy_e]   # same set as v1 main

# Production set — mirrors backfill_year.py SYMBOLS and the dashboard allow-list.
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
    "1000PEPEUSDT", "WIFUSDT", "SUIUSDT",
    "NEARUSDT", "FETUSDT", "ADAUSDT", "SUSDT",
    "ARBUSDT", "ORDIUSDT", "ONDOUSDT",
    "XAUUSDT", "XAGUSDT",
    "NVDAUSDT", "METAUSDT",
    "AMZNUSDT", "COINUSDT", "MSTRUSDT",
]

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)


def build_symbol_rows(symbol: str, win_start: pd.Timestamp,
                      win_end: pd.Timestamp) -> tuple[list[dict], dict]:
    """Returns (rows, info). Identical to backfill_year.build_symbol_rows except the
    rows are tagged version='v3' and resolved under the partial-TP exit model."""
    end = pd.Timestamp.now(tz="UTC")
    warmup_start = win_start - pd.Timedelta(hours=6000)   # ~250d detector warmup

    df = tsc.fetch_1h(symbol, warmup_start, end)
    if df.empty:
        return [], {"symbol": symbol, "bars": 0, "signals": 0, "skipped": True}

    signals = run_engine(symbol, df, strategies=DAG_STRATS)
    m1_end = min(win_end, end)
    df1m = tsc.fetch_1m(symbol, win_start - pd.Timedelta(hours=2), m1_end)
    rows, status_counts = [], {}
    for s in signals:
        if not (win_start <= s.timestamp < win_end):
            continue
        outcome = tsc.simulate(symbol, s.timestamp, s.direction, s.entry,
                               s.stop_loss, s.take_profit_1, df1m=df1m)
        status_counts[outcome["status"]] = status_counts.get(outcome["status"], 0) + 1
        row = tsc.build_row(
            symbol, s.timestamp, s.direction, s.entry, s.stop_loss, s.take_profit_1,
            outcome, strategy=s.strategy, quality=s.quality,
            confluence_score=s.confluence_score)
        row["version"] = V3_VERSION
        rows.append(row)
    return rows, {"symbol": symbol, "bars": len(df), "signals": len(rows),
                  "skipped": False, "status": status_counts}


def wipe(conn, scope: str, win_start: pd.Timestamp, win_end: pd.Timestamp) -> int:
    cur = conn.cursor()
    if scope == "all":
        cur.execute(f"DELETE FROM {tsc.TABLE} WHERE version = %s", (V3_VERSION,))
    elif scope == "year":
        cur.execute(
            f"DELETE FROM {tsc.TABLE} WHERE version = %s AND signal_time >= %s AND signal_time < %s",
            (V3_VERSION, win_start.to_pydatetime(), win_end.to_pydatetime()))
    n = cur.rowcount
    conn.commit()
    cur.close()
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="*", default=SYMBOLS)
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--start", type=str, default=None, help="ISO date override (UTC)")
    ap.add_argument("--end", type=str, default=None, help="ISO date override (UTC)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--wipe-scope", choices=["none", "year", "all"], default=None)
    args = ap.parse_args()

    if not args.dry_run and args.wipe_scope is None:
        raise SystemExit("Real run requires --wipe-scope {none|year|all} "
                         "(use --dry-run to preview without DB writes).")

    now = pd.Timestamp.now(tz="UTC")
    win_start = pd.Timestamp(args.start, tz="UTC") if args.start else pd.Timestamp(f"{args.year}-01-01", tz="UTC")
    win_end = pd.Timestamp(args.end, tz="UTC") if args.end else min(pd.Timestamp(f"{args.year + 1}-01-01", tz="UTC"), now)

    print(f"=== {args.year} MAIN ½TP backfill (v3, partial-TP+BE) | {win_start.date()}..{win_end.date()} | "
          f"symbols={len(args.symbols)} | strats={[f.__name__ for f in DAG_STRATS]} | "
          f"dry_run={args.dry_run} | wipe={args.wipe_scope} ===")

    all_rows, infos = [], []
    for sym in args.symbols:
        rows, info = build_symbol_rows(sym, win_start, win_end)
        infos.append(info)
        all_rows.extend(rows)
        tag = "SKIP (no data)" if info["skipped"] else f"{info['signals']} signals {info.get('status', {})}"
        print(f"  {sym:<12} bars={info['bars']:<6} -> {tag}")
        if args.dry_run and rows:
            fp = OUT / f"v3_preview_{args.year}_{sym}.csv"
            with open(fp, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader(); w.writerows(rows)

    agg = {}
    for r in all_rows:
        agg[r["status"]] = agg.get(r["status"], 0) + 1
    skipped = [i["symbol"] for i in infos if i["skipped"]]
    print(f"\nTOTAL v3 rows={len(all_rows)} status={agg}")
    if skipped:
        print(f"SKIPPED symbols (no Binance data): {skipped}")

    if args.dry_run:
        print(f"\n[dry-run] previews in {OUT}/  — no DB writes.")
        return

    conn = tsc.backtest_conn()
    if args.wipe_scope in ("year", "all"):
        deleted = wipe(conn, args.wipe_scope, win_start, win_end)
        print(f"wiped {deleted} existing v3 rows (scope={args.wipe_scope}, "
              f"window={win_start.date()}..{win_end.date()})")
    n = tsc.upsert_rows(conn, all_rows)
    conn.close()
    print(f"upserted {n} v3 rows into {tsc.TABLE}")


if __name__ == "__main__":
    main()
