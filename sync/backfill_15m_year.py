"""Backfill a full calendar year of the high-frequency PULSE strategy into
ict_trade.trading_signals with version='v1-15m' (kept SEPARATE from the static-17
1h backtest version='v1' and the dynamic radar version='v1-dyn').

Same engine, same production strategy set (B/C/D/E), same static-17 symbol universe
as backfill_year.py — the ONLY difference is the primary timeframe: 15m instead of 1h.
~4x more bars -> ~3-4x more signals. The signal quality logic (FVG/OB/sweep/BOS, RR,
killzones) is unchanged. HTF bias is aggregated to 1h (a proportionate 4:1 step above
the 15m primary, mirroring 1h->4h on the default pipeline).

Outcome resolution stays on 1m bars with the same 180-minute entry-fill window
(EXPIRY_MINUTES is bar-agnostic). The signal fires at its 15m bar close, so the 1m
resolver starts at signal_time + 15 minutes (ltf_minutes=15).

Safety: never deletes in --dry-run; a real run needs --wipe-scope {year|all|none}.
  wipe touches ONLY version='v1-15m' rows, so 'v1' and 'v1-dyn' backtests are untouched.

Usage:
  # fast validation (few symbols, short window, no DB):
  python sync/backfill_15m_year.py --year 2026 --symbols BTCUSDT ETHUSDT \
    --start 2026-05-01 --end 2026-06-06 --dry-run
  # full year, real run:
  python sync/backfill_15m_year.py --year 2026 --wipe-scope year
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import pandas as pd

import trade_sync_common as tsc           # adds backtest/ to sys.path
from engine import run_engine             # noqa: E402
from ict.strategies import strategy_c  # noqa: E402

# v2: on 15m only Strategy C (FVG+OB confluence) showed a real edge (+703R, +0.61R/
# trade). B/D were net-flat-to-negative and D alone flooded ~79% of trades with no
# edge, so PULSE runs C-only. (No composites either — those need >=2 strats same bar.)
DAG_STRATS = [strategy_c]
PULSE_VERSION = "v1-15m"
HTF_RULE = "1h"                # HTF bias TF for the 15m primary (4:1 step)
LTF_MINUTES = 15              # 15m bar duration: signal fires at bar close + 15m
WARMUP_HOURS = 3000          # ~125d of 15m history for detector / HTF / liquidity warmup

# Production set — mirrors backfill_year.py SYMBOLS and the dashboard allow-list.
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


def build_symbol_rows(symbol: str, year: int, win_start: pd.Timestamp,
                      win_end: pd.Timestamp) -> tuple[list[dict], dict]:
    """Returns (rows, info). info carries diagnostics for the run report."""
    end = pd.Timestamp.now(tz="UTC")
    warmup_start = win_start - pd.Timedelta(hours=WARMUP_HOURS)

    df = tsc.fetch_15m(symbol, warmup_start, end)
    if df.empty:
        return [], {"symbol": symbol, "bars": 0, "signals": 0, "skipped": True}

    signals = run_engine(symbol, df, strategies=DAG_STRATS, htf_rule=HTF_RULE)
    # 1m klines (window onward) for intrabar-accurate TP/SL/entry-fill resolution.
    # Cap the 1m fetch at "now" so a future window doesn't request non-existent bars.
    m1_end = min(win_end, end)
    df1m = tsc.fetch_1m(symbol, win_start - pd.Timedelta(hours=2), m1_end)
    rows, status_counts = [], {}
    for s in signals:
        if not (win_start <= s.timestamp < win_end):
            continue
        outcome = tsc.simulate(symbol, s.timestamp, s.direction, s.entry,
                               s.stop_loss, s.take_profit_1, df1m=df1m,
                               ltf_minutes=LTF_MINUTES)
        status_counts[outcome["status"]] = status_counts.get(outcome["status"], 0) + 1
        row = tsc.build_row(
            symbol, s.timestamp, s.direction, s.entry, s.stop_loss, s.take_profit_1,
            outcome, strategy=s.strategy, quality=s.quality,
            confluence_score=s.confluence_score)
        row["version"] = PULSE_VERSION
        rows.append(row)
    return rows, {"symbol": symbol, "bars": len(df), "signals": len(rows),
                  "skipped": False, "status": status_counts}


def wipe(conn, scope: str, win_start: pd.Timestamp, win_end: pd.Timestamp) -> int:
    cur = conn.cursor()
    if scope == "all":
        cur.execute(f"DELETE FROM {tsc.TABLE} WHERE version = %s", (PULSE_VERSION,))
    elif scope == "year":
        cur.execute(
            f"DELETE FROM {tsc.TABLE} WHERE version = %s AND signal_time >= %s AND signal_time < %s",
            (PULSE_VERSION, win_start.to_pydatetime(), win_end.to_pydatetime()))
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

    print(f"=== {args.year} PULSE 15m backfill | {win_start.date()}..{win_end.date()} | "
          f"symbols={len(args.symbols)} | dry_run={args.dry_run} | wipe={args.wipe_scope} ===")

    all_rows, infos = [], []
    for sym in args.symbols:
        rows, info = build_symbol_rows(sym, args.year, win_start, win_end)
        infos.append(info)
        all_rows.extend(rows)
        tag = "SKIP (no data)" if info["skipped"] else f"{info['signals']} signals {info.get('status', {})}"
        print(f"  {sym:<12} bars={info['bars']:<6} -> {tag}")
        if args.dry_run and rows:
            fp = OUT / f"pulse15m_preview_{args.year}_{sym}.csv"
            with open(fp, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader(); w.writerows(rows)

    # aggregate report
    agg = {}
    for r in all_rows:
        agg[r["status"]] = agg.get(r["status"], 0) + 1
    skipped = [i["symbol"] for i in infos if i["skipped"]]
    print(f"\nTOTAL v1-15m rows={len(all_rows)} status={agg}")
    if skipped:
        print(f"SKIPPED symbols (no Binance data): {skipped}")

    if args.dry_run:
        print(f"\n[dry-run] previews in {OUT}/  — no DB writes.")
        return

    conn = tsc.backtest_conn()
    if args.wipe_scope in ("year", "all"):
        deleted = wipe(conn, args.wipe_scope, win_start, win_end)
        print(f"wiped {deleted} existing v1-15m rows (scope={args.wipe_scope})")
    n = tsc.upsert_rows(conn, all_rows)
    conn.close()
    print(f"upserted {n} v1-15m rows into {tsc.TABLE}")


if __name__ == "__main__":
    main()
