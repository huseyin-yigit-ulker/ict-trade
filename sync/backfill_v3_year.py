"""Backtest the RADAR v3 stream for a calendar year -> trading_signals with
version='v3' (kept SEPARATE from v1/v2/v1-dyn/v1-15m).

RADAR v3 is a brand-new strategy — NOT the retired dynamic-symbols radar (v1-dyn):

  strategy F "Vol-Compression Donchian Breakout" (backtest/ict/strategies.py):
    - 1h bars, same static universe as main.
    - LONG when close breaks the prior-120-bar Donchian high (SHORT mirrored),
      only when the breakout emerges from below-average volatility
      (ATR24 < 0.85 x SMA240(ATR24)), with a volume surge (>1.5x 20-bar median)
      and on the EMA200 side (regime filter).
    - Entry = RETEST LIMIT at the broken channel level (the engine only accepts
      retrace-limit entries); anti-chase guard skips runaway bars (>1.2 ATR24).
    - SL = 2.5 x ATR24 (the MIN_SL_DIST floor never binds — no sub-spread stops);
      TP = 3R fixed; 24h fill window (expiry_minutes=1440, vs 180 elsewhere).
    - Re-fire cooldown on the raw trigger series + standard 24h zone dedup.

  Rationale: the ICT streams (v1/v2) FADE moves into zones; F JOINS breakouts out
  of compression — structurally opposite entries, low expected PnL correlation.

Everything else — data fetch, 1m outcome resolution, fees, upsert — is identical
to backfill_v2_year.py, so v3 is method-matched to the v1/v2 backfills.

Safety: never deletes in --dry-run; a real run needs --wipe-scope {year|all|none}.
  wipe touches ONLY version='v3' rows.

RESULT 2026-06-10 (Jan-Jun 2026, 21 symbols): 147 signals, 133 closed, 15% win,
-60R total — FAILED the acceptance gates (needed totR>0, expectancy>=+0.1R,
win>=30%). Only January (+14R, the clean trend month) was positive; Feb-Jun chop
made compression breakouts systematic traps. sync/experiment_v3.py ablation:
market-at-close entry -65R, 2R targets -48..-58R => the edge is absent in this
regime, not an entry-mechanics artifact. Live stream stays disabled.

Usage:
  # fast validation (few symbols, short window, no DB):
  python sync/backfill_v3_year.py --symbols BTCUSDT SOLUSDT \
    --start 2026-03-01 --end 2026-06-10 --dry-run
  # full year, real run:
  python sync/backfill_v3_year.py --year 2026 --wipe-scope year
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import pandas as pd

import trade_sync_common as tsc            # adds backtest/ to sys.path
from ict import config as C                # noqa: E402

V3_VERSION = "v3"
RADAR_EXPIRY_MIN = C.RADAR_ENTRY_EXPIRY_BARS * 60   # 1440 = 24h retest window on 1m

from engine import run_engine              # noqa: E402
from ict.strategies import strategy_f      # noqa: E402

DAG_STRATS = [strategy_f]

# Production set — mirrors backfill_year.py SYMBOLS / sync_daily.py STATIC_SYMBOLS
# (post-audit 21 names; the stale v2 list with DOGE/TSLA/GOOGL/PLTR is NOT used).
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
    "1000PEPEUSDT", "WIFUSDT", "SUIUSDT",
    "NEARUSDT", "FETUSDT", "ADAUSDT", "SUSDT",
    "ARBUSDT", "ORDIUSDT", "ONDOUSDT",
    "XAUUSDT", "XAGUSDT",
    # Stock-backed perps (underlying equities)
    "NVDAUSDT", "METAUSDT",
    "AMZNUSDT", "COINUSDT", "MSTRUSDT",
]

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)


def build_symbol_rows(symbol: str, win_start: pd.Timestamp,
                      win_end: pd.Timestamp) -> tuple[list[dict], dict]:
    """Returns (rows, info). info carries diagnostics for the run report."""
    end = pd.Timestamp.now(tz="UTC")
    warmup_start = win_start - pd.Timedelta(hours=6000)   # ~250d; F needs >=264 bars

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
                               s.stop_loss, s.take_profit_1, df1m=df1m,
                               expiry_minutes=RADAR_EXPIRY_MIN)
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

    print(f"=== {args.year} RADAR v3 backfill | {win_start.date()}..{win_end.date()} | "
          f"symbols={len(args.symbols)} | strats={[f.__name__ for f in DAG_STRATS]} | "
          f"expiry_min={RADAR_EXPIRY_MIN} | dry_run={args.dry_run} | wipe={args.wipe_scope} ===")

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
