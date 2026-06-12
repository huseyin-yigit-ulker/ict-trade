"""Backtest the MAIN v2 strategy set for a calendar year -> trading_signals with
version='v2' (kept SEPARATE from the v1 main backtest).

main v2 is a refinement of main (v1), derived from the 2026 Jan-Jun v1 audit:

  v1 set : strategy B/C/D/E on 1h, static-17 universe, D excluded on {NVDA,NEAR,AMZN,ORDI}.

  v2 changes (subtractive — same engine, same universe, same 1h TF):
    1. DROP strategy E  — produced ZERO signals across all of 2026 (pure dead weight).
    2. EXTEND D's symbol exclusion with {ADAUSDT, XAUUSDT, ETHUSDT} — the silver-bullet
       engine (D) was structurally net-negative on these in 2026:
         ADA -25.9R (negative EVERY month, 6.7% win / 30 trades)
         XAU -14.5R (negative 4/6 months — gold doesn't fit the SB FVG model)
         ETH  -7.9R (negative 4/6 months)
       SOL (-3.9R) and SUI (-0.4R) were mixed/breakeven noise -> intentionally KEPT
       (excluding them would be curve-fitting). C/B on the excluded symbols stay live,
       so only D's drag is removed (~ -48R), not the symbols' positive C/B edge.

  Everything else — detectors, confluence, dedup, RR gates, TP/SL on 1m — is identical
  to backfill_year.py, so v1 vs v2 is a clean A/B on the strategy set + D scope.

  VALIDATED (controlled in-memory ablation, identical engine+data+sim for both arms,
  2026 Jan-Jun, resolved trades only — see experiment_v2.py):
        v1 [B,C,D,E] base           : 609 trd, 19.4% win, 0.140 R/trd, +85.4 R
        v2 (drop E + D-excl 3 syms) : 532 trd, 20.5% win, 0.229 R/trd, +121.9 R
    => +36.5 R (+43%), +1.1pt win rate, +64% avg R/trade. Dropping E is a verified
       no-op (identical output); the D symbol-exclusion is the sole performance lever.
    NB: the *accumulated* DB 'v1' rows (~149 R) are NOT method-matched to this — they mix
       older-engine + daily-sync live signals — so compare v2 to the ablation v1, not the
       dashboard 'v1' total.

The D exclusion is applied PROCESS-LOCALLY (mutating ict.config.D_EXCLUDE_SYMBOLS before
the engine runs); it never touches the live DAG or the v1 backfill, which run in their
own processes off the unmodified config.

Safety: never deletes in --dry-run; a real run needs --wipe-scope {year|all|none}.
  wipe touches ONLY version='v2' rows, so 'v1'/'v1-dyn'/'v1-15m' are untouched.

Usage:
  # fast validation (few symbols, short window, no DB):
  python sync/backfill_v2_year.py --symbols BTCUSDT ADAUSDT XAUUSDT \
    --start 2026-05-01 --end 2026-06-06 --dry-run
  # full year, real run:
  python sync/backfill_v2_year.py --year 2026 --wipe-scope year
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import pandas as pd

import trade_sync_common as tsc           # adds backtest/ to sys.path
from ict import config as C               # noqa: E402

# --- v2 strategy-set + scope changes (process-local; v1/live unaffected) ---------------
V2_VERSION = "v2"
V2_EXTRA_D_EXCLUDE = {"ADAUSDT", "XAUUSDT", "ETHUSDT"}   # D net-negative on these in 2026
C.D_EXCLUDE_SYMBOLS = set(C.D_EXCLUDE_SYMBOLS) | V2_EXTRA_D_EXCLUDE

from engine import run_engine                                      # noqa: E402
from ict.strategies import strategy_b, strategy_c, strategy_d      # noqa: E402  (E dropped)

DAG_STRATS = [strategy_b, strategy_c, strategy_d]                  # v1 was [b, c, d, e]

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
    # 2026-06-12 tokenized-equity expansion. Listings span 2026-02-02 .. 2026-06-08.
    "CRCLUSDT", "INTCUSDT", "HOODUSDT", "MSFTUSDT", "AVGOUSDT",
    "BABAUSDT", "BXUSDT", "HPEUSDT", "AMATUSDT", "CRWDUSDT",
    "CRDOUSDT", "AAOIUSDT", "IWMUSDT",
]

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)


def build_symbol_rows(symbol: str, win_start: pd.Timestamp,
                      win_end: pd.Timestamp) -> tuple[list[dict], dict]:
    """Returns (rows, info). info carries diagnostics for the run report."""
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
        row["version"] = V2_VERSION
        rows.append(row)
    return rows, {"symbol": symbol, "bars": len(df), "signals": len(rows),
                  "skipped": False, "status": status_counts}


def wipe(conn, scope: str, win_start: pd.Timestamp, win_end: pd.Timestamp) -> int:
    cur = conn.cursor()
    if scope == "all":
        cur.execute(f"DELETE FROM {tsc.TABLE} WHERE version = %s", (V2_VERSION,))
    elif scope == "year":
        cur.execute(
            f"DELETE FROM {tsc.TABLE} WHERE version = %s AND signal_time >= %s AND signal_time < %s",
            (V2_VERSION, win_start.to_pydatetime(), win_end.to_pydatetime()))
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

    print(f"=== {args.year} MAIN v2 backfill | {win_start.date()}..{win_end.date()} | "
          f"symbols={len(args.symbols)} | strats={[f.__name__ for f in DAG_STRATS]} | "
          f"D_excl={sorted(C.D_EXCLUDE_SYMBOLS)} | dry_run={args.dry_run} | wipe={args.wipe_scope} ===")

    all_rows, infos = [], []
    for sym in args.symbols:
        rows, info = build_symbol_rows(sym, win_start, win_end)
        infos.append(info)
        all_rows.extend(rows)
        tag = "SKIP (no data)" if info["skipped"] else f"{info['signals']} signals {info.get('status', {})}"
        print(f"  {sym:<12} bars={info['bars']:<6} -> {tag}")
        if args.dry_run and rows:
            fp = OUT / f"v2_preview_{args.year}_{sym}.csv"
            with open(fp, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader(); w.writerows(rows)

    agg = {}
    for r in all_rows:
        agg[r["status"]] = agg.get(r["status"], 0) + 1
    skipped = [i["symbol"] for i in infos if i["skipped"]]
    print(f"\nTOTAL v2 rows={len(all_rows)} status={agg}")
    if skipped:
        print(f"SKIPPED symbols (no Binance data): {skipped}")

    if args.dry_run:
        print(f"\n[dry-run] previews in {OUT}/  — no DB writes.")
        return

    conn = tsc.backtest_conn()
    if args.wipe_scope in ("year", "all"):
        deleted = wipe(conn, args.wipe_scope, win_start, win_end)
        print(f"wiped {deleted} existing v2 rows (scope={args.wipe_scope}, "
              f"window={win_start.date()}..{win_end.date()})")
    n = tsc.upsert_rows(conn, all_rows)
    conn.close()
    print(f"upserted {n} v2 rows into {tsc.TABLE}")


if __name__ == "__main__":
    main()
