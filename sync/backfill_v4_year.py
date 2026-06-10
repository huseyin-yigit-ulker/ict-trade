"""Backtest the SQUEEZE v4 stream for a calendar year -> trading_signals with
version='v4' (kept SEPARATE from v1/v2/v3/v1-dyn/v1-15m).

SQUEEZE v4 is the judge panel's runner-up candidate (2026-06-10), built after the
v3 compression-breakout FAILED its gates:

  strategy G "Funding-Extreme Squeeze Fade" (backtest/ict/strategies.py):
    - 1h bars, same static universe as main, but the SIGNAL is derivative
      positioning, not price geometry: settled Binance perp funding, normalized
      per-event to an 8h-equivalent (4h-settled symbols would otherwise look
      half as crowded).
    - LONG when funding is extremely NEGATIVE (crowded shorts paying longs):
      |rate_8h| >= 0.05%/8h AND beyond the 5th pctl of the trailing 30d of PRIOR
      events, on a squeeze-ignition bar (close >= 0.25*ATR24 in the fade
      direction — no naked knife-catching). SHORT mirrored on positive extremes.
    - Entry = retrace LIMIT 0.35*ATR24 inside the ignition close (the engine
      only accepts retrace-limit entries); SL = 2.0*ATR24; TP = 2R fixed;
      12h fill window (expiry_minutes=720); 48h raw-trigger re-fire cooldown.
    - Structurally the LOWEST-correlation stream vs A-E (fade into zones) and
      F (join breakouts): G's input series doesn't exist in either. Funding
      accrual is NOT credited — the fade direction RECEIVES funding, so the
      reported R is conservative.

Everything else — data fetch, 1m outcome resolution, fees, upsert — is identical
to backfill_v3_year.py, so v4 is method-matched to the v1/v2/v3 backfills.

Safety: never deletes in --dry-run; a real run needs --wipe-scope {year|all|none}.
  wipe touches ONLY version='v4' rows.

RESULT 2026-06-10 (Jan-Jun 2026, 21 symbols): 127 signals, 116 closed, 24.1% win,
-52.3R total (LONG -35.3R / SHORT -16.9R) — FAILED the acceptance gates (needed
totR>0, expectancy>=+0.1R, win>=30%). Losses concentrate in Mar (-17R) / Apr
(-32R) and in the metals + stock-backed perps (XAG -18R, AMZN -11R, XAU -10R,
NVDA -9R): in this regime extreme funding marked positioning that was RIGHT
about the trend, so fading it got run over; crypto fades were ~flat (FET +4.8,
ONDO +3.0 vs WIF -3.3). sync/experiment_squeeze.py ablation: NONE of 17 one-knob
variants flips the sign (best: abs floor 0.03% -> -36.4R; TP 2.5R/3R make it
WORSE at 15%/12% win) => the edge itself is absent, not an entry-mechanics
artifact. Live stream stays disabled (dag.py SQUEEZE_ENABLED=0).

Usage:
  # fast validation (few symbols, short window, no DB):
  python sync/backfill_v4_year.py --symbols FETUSDT WIFUSDT \
    --start 2026-03-01 --end 2026-06-10 --dry-run
  # full year, real run:
  python sync/backfill_v4_year.py --year 2026 --wipe-scope year
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import pandas as pd

import trade_sync_common as tsc            # adds backtest/ to sys.path
from ict import config as C                # noqa: E402

V4_VERSION = "v4"
SQUEEZE_EXPIRY_MIN = C.SQUEEZE_ENTRY_EXPIRY_BARS * 60   # 720 = 12h fill window on 1m
FUNDING_WARMUP_DAYS = 45    # > SQUEEZE_PCTL_WINDOW (30d) + slack for the shift(1)

from engine import run_engine               # noqa: E402
from ict.data import fetch_funding          # noqa: E402
from ict.strategies import strategy_g, set_funding   # noqa: E402

DAG_STRATS = [strategy_g]

# Production set — mirrors backfill_year.py SYMBOLS / sync_daily.py STATIC_SYMBOLS.
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
    warmup_start = win_start - pd.Timedelta(hours=6000)   # method-matched to v1/v2/v3

    df = tsc.fetch_1h(symbol, warmup_start, end)
    if df.empty:
        return [], {"symbol": symbol, "bars": 0, "signals": 0, "skipped": True}

    fdf = fetch_funding(symbol,
                        int((warmup_start - pd.Timedelta(days=FUNDING_WARMUP_DAYS)).timestamp() * 1000),
                        int(end.timestamp() * 1000))
    set_funding(symbol, fdf)
    if fdf.empty:
        # spot-only / no perp funding -> G stays silent; report it honestly.
        return [], {"symbol": symbol, "bars": len(df), "signals": 0,
                    "skipped": False, "status": {}, "no_funding": True}

    signals = run_engine(symbol, df, strategies=DAG_STRATS)
    m1_end = min(win_end, end)
    df1m = tsc.fetch_1m(symbol, win_start - pd.Timedelta(hours=2), m1_end)
    rows, status_counts = [], {}
    for s in signals:
        if not (win_start <= s.timestamp < win_end):
            continue
        outcome = tsc.simulate(symbol, s.timestamp, s.direction, s.entry,
                               s.stop_loss, s.take_profit_1, df1m=df1m,
                               expiry_minutes=SQUEEZE_EXPIRY_MIN)
        status_counts[outcome["status"]] = status_counts.get(outcome["status"], 0) + 1
        row = tsc.build_row(
            symbol, s.timestamp, s.direction, s.entry, s.stop_loss, s.take_profit_1,
            outcome, strategy=s.strategy, quality=s.quality,
            confluence_score=s.confluence_score)
        row["version"] = V4_VERSION
        rows.append(row)
    return rows, {"symbol": symbol, "bars": len(df), "signals": len(rows),
                  "skipped": False, "status": status_counts}


def wipe(conn, scope: str, win_start: pd.Timestamp, win_end: pd.Timestamp) -> int:
    cur = conn.cursor()
    if scope == "all":
        cur.execute(f"DELETE FROM {tsc.TABLE} WHERE version = %s", (V4_VERSION,))
    elif scope == "year":
        cur.execute(
            f"DELETE FROM {tsc.TABLE} WHERE version = %s AND signal_time >= %s AND signal_time < %s",
            (V4_VERSION, win_start.to_pydatetime(), win_end.to_pydatetime()))
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

    print(f"=== {args.year} SQUEEZE v4 backfill | {win_start.date()}..{win_end.date()} | "
          f"symbols={len(args.symbols)} | strats={[f.__name__ for f in DAG_STRATS]} | "
          f"expiry_min={SQUEEZE_EXPIRY_MIN} | dry_run={args.dry_run} | wipe={args.wipe_scope} ===")

    all_rows, infos = [], []
    for sym in args.symbols:
        rows, info = build_symbol_rows(sym, win_start, win_end)
        infos.append(info)
        all_rows.extend(rows)
        if info["skipped"]:
            tag = "SKIP (no data)"
        elif info.get("no_funding"):
            tag = "SKIP (no funding history — spot-only?)"
        else:
            tag = f"{info['signals']} signals {info.get('status', {})}"
        print(f"  {sym:<12} bars={info['bars']:<6} -> {tag}")
        if args.dry_run and rows:
            fp = OUT / f"v4_preview_{args.year}_{sym}.csv"
            with open(fp, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader(); w.writerows(rows)

    agg = {}
    for r in all_rows:
        agg[r["status"]] = agg.get(r["status"], 0) + 1
    skipped = [i["symbol"] for i in infos if i["skipped"] or i.get("no_funding")]
    print(f"\nTOTAL v4 rows={len(all_rows)} status={agg}")
    if skipped:
        print(f"SKIPPED symbols (no data / no funding): {skipped}")

    if args.dry_run:
        print(f"\n[dry-run] previews in {OUT}/  — no DB writes.")
        return

    conn = tsc.backtest_conn()
    if args.wipe_scope in ("year", "all"):
        deleted = wipe(conn, args.wipe_scope, win_start, win_end)
        print(f"wiped {deleted} existing v4 rows (scope={args.wipe_scope}, "
              f"window={win_start.date()}..{win_end.date()})")
    n = tsc.upsert_rows(conn, all_rows)
    conn.close()
    print(f"upserted {n} v4 rows into {tsc.TABLE}")


if __name__ == "__main__":
    main()
