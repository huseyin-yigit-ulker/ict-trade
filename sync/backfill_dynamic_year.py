"""Backtest the DYNAMIC Volume-Radar strategy for a calendar year -> trading_signals
with version='v1-dyn' (kept SEPARATE from the static-17 backtest, version='v1').

Reconstructs, hour-by-hour, the SAME volume-anomaly picks the live engine makes
(dag.py pick_volume_anomaly_symbols): of a liquid USDT-perp pool, rank by trailing-24h
quote-volume -> top CANDIDATE_CAP, keep those whose last closed 1h bar quote-volume
spiked >= SPIKE_RATIO vs their own 24-bar median -> top MAX_PICKS. Everything uses only
data up to each bar (no look-ahead). Then it runs the production ICT engine on each
ever-picked symbol, keeps only signals fired on a bar where that symbol was picked,
resolves outcomes on 1m, and upserts with version='v1-dyn'.

CAVEATS (documented, intentional):
  - The candidate POOL is built from CURRENT liquidity (Binance now), so symbols delisted
    before now are missing (mild survivorship in the pool). The per-hour RANKING within
    the pool is trailing-24h and look-ahead-free. This mirrors live as closely as history
    allows (live has no historical ticker either).
  - Dynamic picks are unvetted symbols — experimental, not part of the curated 17.

Safety: never deletes in --dry-run; a real run needs --wipe-scope {year|all|none}.
  wipe touches ONLY version='v1-dyn' rows, so the static-17 'v1' backtest is untouched.

Usage:
  # fast validation (small pool, short window, no DB):
  python sync/backfill_dynamic_year.py --pool-size 25 --start 2026-05-01 --end 2026-06-06 --dry-run
  # full year, real run:
  python sync/backfill_dynamic_year.py --year 2026 --wipe-scope year
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import pandas as pd
import requests

import trade_sync_common as tsc           # adds backtest/ to sys.path
from engine import run_engine             # noqa: E402
from ict.strategies import strategy_b, strategy_c, strategy_d, strategy_e  # noqa: E402

DAG_STRATS = [strategy_b, strategy_c, strategy_d, strategy_e]
DYN_VERSION = "v1-dyn"

# Live picker params — mirror dag.py exactly.
CANDIDATE_CAP   = 50
MAX_PICKS       = 5
BASELINE_BARS   = 24
SPIKE_RATIO     = 3.0
MIN_BASELINE_QV = 50_000.0

# Static 17 (excluded from the dynamic pool) — mirrors dag.py SYMBOLS.
STATIC_17 = {
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT",
    "1000PEPEUSDT", "WIFUSDT", "SUIUSDT", "NEARUSDT", "FETUSDT",
    "ADAUSDT", "SUSDT", "ARBUSDT", "ORDIUSDT", "ONDOUSDT", "XAUUSDT", "XAGUSDT",
}
BASE_BLOCKLIST = {
    "USDC", "FDUSD", "TUSD", "BUSD", "DAI", "USDP", "UST", "USTC", "PAX", "SUSD",
    "USDE", "USDD", "AEUR", "BFUSD", "EUR", "GBP", "TRY", "BRL", "AUD", "JPY",
    "ARS", "PLN", "ZAR", "MXN", "RUB", "UAH",
    "WBTC", "WETH", "WBETH", "BETH", "STETH", "WSTETH",
}
EXINFO_URL = "https://fapi.binance.com/fapi/v1/exchangeInfo"
TICKER_URL = "https://fapi.binance.com/fapi/v1/ticker/24hr"
WARMUP_HOURS = 6000

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)


def fetch_pool(pool_size: int) -> list[str]:
    """Top `pool_size` USDT-perps by current 24h quoteVolume (excl. the 17 + stables)."""
    perps = set()
    try:
        syms = requests.get(EXINFO_URL, timeout=30).json().get("symbols", [])
        perps = {s["symbol"] for s in syms
                 if s.get("contractType") == "PERPETUAL"
                 and s.get("status") == "TRADING" and s.get("quoteAsset") == "USDT"}
    except Exception as e:
        print(f"  exchangeInfo failed: {e}; suffix filter only")
    rows = []
    for t in requests.get(TICKER_URL, timeout=30).json():
        sym = t.get("symbol", "")
        if not sym.endswith("USDT") or sym in STATIC_17:
            continue
        if perps and sym not in perps:
            continue
        if "_" in sym or sym.endswith(("UPUSDT", "DOWNUSDT", "BULLUSDT", "BEARUSDT")):
            continue
        if sym[:-4] in BASE_BLOCKLIST:
            continue
        try:
            qv = float(t.get("quoteVolume", 0.0))
        except (TypeError, ValueError):
            continue
        if qv > 0:
            rows.append((sym, qv))
    rows.sort(key=lambda x: x[1], reverse=True)
    return [s for s, _ in rows[:pool_size]]


def build_pick_map(win_start: pd.Timestamp, win_end: pd.Timestamp,
                   pool: list[str]) -> tuple[dict, list]:
    """For every bar in [win_start, win_end], reconstruct the live picks. Returns
    (pick_map: {symbol -> set(bar Timestamp)}, log: [(ts, symbol, ratio)])."""
    tsum, ratio, med = {}, {}, {}
    lb_start = win_start - pd.Timedelta(hours=BASELINE_BARS + 4)
    for i, sym in enumerate(pool):
        df = tsc.fetch_1h(sym, lb_start, win_end)
        if df.empty or len(df) < BASELINE_BARS + 2:
            continue
        qv = (df["volume"] * df["close"]).astype(float)
        tsum[sym] = qv.rolling(BASELINE_BARS).sum()
        med[sym] = qv.shift(1).rolling(BASELINE_BARS).median()
        ratio[sym] = qv / med[sym]
        if (i + 1) % 20 == 0:
            print(f"  pool klines {i + 1}/{len(pool)}")
    if not tsum:
        return {}, []
    T = pd.concat(tsum, axis=1)
    R = pd.concat(ratio, axis=1)
    M = pd.concat(med, axis=1)
    window = T.index[(T.index >= win_start) & (T.index <= win_end)]

    pick_map: dict = defaultdict(set)
    log: list = []
    for ts in window:
        trow = T.loc[ts].dropna()
        if trow.empty:
            continue
        shortlist = trow.nlargest(CANDIDATE_CAP).index           # top liquidity (no look-ahead)
        rrow = R.loc[ts, shortlist]
        mrow = M.loc[ts, shortlist]
        elig = rrow[(rrow >= SPIKE_RATIO) & (mrow >= MIN_BASELINE_QV)].dropna()
        if elig.empty:
            continue
        for sym in elig.nlargest(MAX_PICKS).index:
            pick_map[sym].add(ts)
            log.append((ts, sym, float(elig[sym])))
    return pick_map, log


def build_dynamic_rows(pick_map: dict, win_start: pd.Timestamp,
                       win_end: pd.Timestamp) -> tuple[list, dict]:
    """Run the ICT engine on each ever-picked symbol; keep signals fired on a bar
    where the symbol was picked; resolve on 1m; tag version='v1-dyn'."""
    end = pd.Timestamp.now(tz="UTC")
    m1_end = min(win_end, end)
    rows, status = [], {}
    syms = sorted(pick_map, key=lambda s: -len(pick_map[s]))
    for j, sym in enumerate(syms):
        pick_ts = pick_map[sym]
        df = tsc.fetch_1h(sym, win_start - pd.Timedelta(hours=WARMUP_HOURS), end)
        if df.empty:
            continue
        signals = run_engine(sym, df, strategies=DAG_STRATS)
        kept = [s for s in signals
                if (win_start <= s.timestamp <= win_end) and (s.timestamp in pick_ts)]
        print(f"  [{j + 1}/{len(syms)}] {sym:<14} picked@{len(pick_ts)} bars -> {len(kept)} signals")
        if not kept:
            continue
        df1m = tsc.fetch_1m(sym, win_start - pd.Timedelta(hours=2), m1_end)
        for s in kept:
            outcome = tsc.simulate(sym, s.timestamp, s.direction, s.entry,
                                   s.stop_loss, s.take_profit_1, df1m=df1m)
            status[outcome["status"]] = status.get(outcome["status"], 0) + 1
            row = tsc.build_row(sym, s.timestamp, s.direction, s.entry, s.stop_loss,
                                s.take_profit_1, outcome, strategy=s.strategy,
                                quality=s.quality, confluence_score=s.confluence_score)
            row["version"] = DYN_VERSION
            rows.append(row)
    return rows, status


def wipe_dyn(conn, scope: str, win_start: pd.Timestamp, win_end: pd.Timestamp) -> int:
    cur = conn.cursor()
    if scope == "all":
        cur.execute(f"DELETE FROM {tsc.TABLE} WHERE version = %s", (DYN_VERSION,))
    elif scope == "year":
        cur.execute(
            f"DELETE FROM {tsc.TABLE} WHERE version = %s AND signal_time >= %s AND signal_time < %s",
            (DYN_VERSION, win_start.to_pydatetime(), win_end.to_pydatetime()))
    n = cur.rowcount
    conn.commit()
    cur.close()
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--start", type=str, default=None, help="ISO date override (UTC)")
    ap.add_argument("--end", type=str, default=None, help="ISO date override (UTC)")
    ap.add_argument("--pool-size", type=int, default=120)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--wipe-scope", choices=["none", "year", "all"], default=None)
    args = ap.parse_args()

    if not args.dry_run and args.wipe_scope is None:
        raise SystemExit("Real run requires --wipe-scope {none|year|all} (or use --dry-run).")

    now = pd.Timestamp.now(tz="UTC")
    win_start = pd.Timestamp(args.start, tz="UTC") if args.start else pd.Timestamp(f"{args.year}-01-01", tz="UTC")
    win_end = pd.Timestamp(args.end, tz="UTC") if args.end else min(pd.Timestamp(f"{args.year + 1}-01-01", tz="UTC"), now)

    print(f"=== dynamic Volume-Radar backtest | {win_start.date()}..{win_end.date()} | "
          f"pool={args.pool_size} | dry_run={args.dry_run} | wipe={args.wipe_scope} ===")

    pool = fetch_pool(args.pool_size)
    print(f"pool: {len(pool)} symbols (top {args.pool_size} liquid USDT-perps outside the 17)")
    if not pool:
        raise SystemExit("empty pool — Binance unreachable?")

    pick_map, log = build_pick_map(win_start, win_end, pool)
    n_pick_events = len(log)
    n_syms = len(pick_map)
    print(f"\npick-map: {n_syms} distinct symbols ever picked, {n_pick_events} pick-events")
    if log:
        top = sorted(log, key=lambda x: -x[2])[:8]
        print("  biggest spikes: " + ", ".join(f"{s}({r:.0f}x @{ts:%m-%d %H:%M})" for ts, s, r in top))

    rows, status = build_dynamic_rows(pick_map, win_start, win_end)
    print(f"\nTOTAL v1-dyn rows={len(rows)} status={status}")

    if args.dry_run:
        if rows:
            fp = OUT / f"dyn_backtest_preview_{win_start.date()}_{win_end.date()}.csv"
            with open(fp, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader(); w.writerows(rows)
            print(f"[dry-run] preview -> {fp}")
        print("[dry-run] no DB writes.")
        return

    conn = tsc.backtest_conn()
    if args.wipe_scope in ("year", "all"):
        deleted = wipe_dyn(conn, args.wipe_scope, win_start, win_end)
        print(f"wiped {deleted} existing v1-dyn rows (scope={args.wipe_scope})")
    n = tsc.upsert_rows(conn, rows)
    conn.close()
    print(f"upserted {n} v1-dyn rows into {tsc.TABLE}")


if __name__ == "__main__":
    main()
