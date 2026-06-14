"""Backfill the RANGE stream — Burak's RANGE_DEV (range-deviation fade) only.

Adapted to the 6-detector regime ENSEMBLE (sync/regime_ensemble.py, port of
src/utils/regimeDetectors.js) instead of the old single-ER gate. The 2026 by-verdict
study found RANGE_DEV's edge lives under the ensemble's TREND verdict: trend +60.7R
(avg +0.32), transition ~flat (−1R), ensemble-RANGE LOSES (−20R). Counterintuitive but
mechanistic — a deviation-fade needs FOLLOW-THROUGH to the opposite boundary, which the
trend verdict (directional persistence) supplies; in the choppy/anti-persistent "range"
verdict the fade just whipsaws. So the RANGE stream =

  • technique : RANGE_DEV only (backtest/burak_strategy.generate_signals), dropping
                OB_PULLBACK / IC / FVG_TREND (those were net-negative at scale).
  • exit      : FULL TP (½TP+BE sinks RANGE_DEV's total R: +37R -> −11R) — so NO ½TP.
  • gate      : keep only signals fired while the causal 6-detector ensemble verdict
                is TREND (score >= 0.15). GATE_VERDICTS below.
  • resolve   : 1m bars via tsc.simulate (fees in), like every other stream.
  • version   : 'range' in ict_trade.trading_signals (backtest stream; no live scanner
                yet — emission would need a dedicated DAG job).

Safety: real run needs --wipe-scope {year|all|none} (wipes ONLY version='range').
Usage:
  python sync/backfill_range.py --year 2026 --dry-run
  python sync/backfill_range.py --year 2026 --wipe-scope year
"""
from __future__ import annotations

import argparse

import pandas as pd

import json
import time
import urllib.request

import trade_sync_common as tsc           # adds backtest/ to sys.path
from ict import config as C               # noqa: E402
import regime_ensemble as RE              # noqa: E402  6-detector ensemble (port of regimeDetectors.js)
from burak_strategy import generate_signals   # noqa: E402

VERSION = "range"
WARMUP_HOURS = 1500
# GATE: keep RANGE_DEV only where the 6-detector regime ensemble verdict is TREND.
# The 2026 by-verdict study found the deviation-fade earns its edge under the
# ensemble's TREND verdict (+60.7R, avg +0.32 — the deviation gets follow-through to
# the opposite boundary), is flat in transition (−1R) and LOSES in the ensemble's
# RANGE/choppy verdict (−20R, the fade whipsaws). So the gate is ensemble == trend.
GATE_VERDICTS = {"trend"}                 # production gate (overridable via --gate)
GATE_MAP = {                              # --gate choice -> the verdict set kept
    "trend": {"trend"}, "range": {"range"}, "transition": {"transition"},
    "not-trend": {"range", "transition"}, "all": {"trend", "transition", "range"},
}
ENSEMBLE_WARMUP_DAYS = 60                 # 4h-kline warmup so the 150-bar window is full at y-start
HOUR_MS = 3_600_000                       # signal fires at bar close = open + 1h (ltf 1h)

# Universe = where RANGE_DEV actually range-fades. The 2026 run showed +41.6R over
# these 29, but XRP/DOGE/LINK/AVAX were −35R (they dump/trend, don't fade — and were
# already net-negative for the core strategies), so they're EXCLUDED. In-sample
# universe choice — validate forward.
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "1000PEPEUSDT", "WIFUSDT", "SUIUSDT",
    "NEARUSDT", "FETUSDT", "ADAUSDT", "SUSDT", "ARBUSDT", "ORDIUSDT", "ONDOUSDT",
    "XAUUSDT", "XAGUSDT",
    "NVDAUSDT", "METAUSDT", "AMZNUSDT", "COINUSDT", "MSTRUSDT", "CRCLUSDT", "PLTRUSDT",
    "TSLAUSDT", "INTCUSDT", "HOODUSDT", "MSFTUSDT", "AVGOUSDT", "BABAUSDT",
]


def fetch_4h(symbol, start_ms):
    """Raw 4h Binance klines from start_ms → now (paginated), for the ensemble."""
    b = "".join(ch for ch in symbol if ch.isalnum())
    now = int(time.time() * 1000)
    out, frm = [], int(start_ms)
    for _ in range(12):
        url = f"https://fapi.binance.com/fapi/v1/klines?symbol={b}&interval=4h&startTime={frm}&limit=1500"
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                d = json.load(r)
        except Exception:
            break
        if not isinstance(d, list) or not d:
            break
        for k in d:
            if not out or int(k[0]) > int(out[-1][0]):
                out.append(k)
        last = int(d[-1][0])
        if len(d) < 1500 or last >= now - RE.FOURH_MS:
            break
        frm = last + 1
    return out


def run_symbol(symbol, w_start, w_end, roll):
    end = pd.Timestamp.now(tz="UTC")
    df = tsc.fetch_1h(symbol, w_start - pd.Timedelta(hours=WARMUP_HOURS), end)
    if df is None or df.empty:
        print(f"  {symbol:<12} SKIP (no data)", flush=True)
        return []
    sigs = [s for s in generate_signals(df)
            if s.strategy == "RANGE_DEV" and w_start <= s.timestamp < w_end]
    # ENSEMBLE gate: keep only signals fired while the causal 6-detector verdict is TREND.
    by_band = {"trend": 0, "transition": 0, "range": 0, "n/a": 0}
    kept = []
    for s in sigs:
        fire_ms = int(s.timestamp.timestamp() * 1000) + HOUR_MS
        v = RE.verdict(RE.score_at(roll, fire_ms)) if roll else "n/a"
        by_band[v if v in by_band else "n/a"] += 1
        if v in GATE_VERDICTS:
            kept.append(s)
    dropped = len(sigs) - len(kept)
    if not kept:
        print(f"  {symbol:<12} {len(sigs)} RANGE_DEV -> 0 kept  bands={by_band}", flush=True)
        return []
    df1m = tsc.fetch_1m(symbol, w_start - pd.Timedelta(hours=2), min(w_end, end))
    rows, sc = [], {}
    prev = C.PARTIAL_TP_ENABLED
    try:
        C.PARTIAL_TP_ENABLED = False                       # FULL TP only
        for s in kept:
            res = tsc.simulate(symbol, s.timestamp, s.direction, s.entry, s.stop_loss,
                               s.take_profit_1, df1m=df1m, expiry_minutes=s.expiry_minutes)
            sc[res["status"]] = sc.get(res["status"], 0) + 1
            row = tsc.build_row(symbol, s.timestamp, s.direction, s.entry, s.stop_loss,
                                s.take_profit_1, res, strategy=s.strategy,
                                quality=s.quality, confluence_score=s.confluence_score)
            row["version"] = VERSION
            rows.append(row)
    finally:
        C.PARTIAL_TP_ENABLED = prev
    print(f"  {symbol:<12} {len(sigs)} RANGE_DEV -> {len(kept)} kept (gate={sorted(GATE_VERDICTS)}, dropped {dropped}) "
          f"bands={by_band} {sc}", flush=True)
    return rows


def tot(rows):
    res = [r for r in rows if r["status"] in ("closed_tp", "closed_sl") and r["pnl_r"] is not None]
    w = sum(1 for r in res if r["pnl_r"] > 0)
    return len(res), w, sum(float(r["pnl_r"]) for r in res)


def wipe(conn, scope, w_start, w_end):
    cur = conn.cursor()
    if scope == "all":
        cur.execute(f"DELETE FROM {tsc.TABLE} WHERE version=%s", (VERSION,))
    elif scope == "year":
        cur.execute(f"DELETE FROM {tsc.TABLE} WHERE version=%s AND signal_time>=%s AND signal_time<%s",
                    (VERSION, w_start.to_pydatetime(), w_end.to_pydatetime()))
    n = cur.rowcount
    conn.commit(); cur.close()
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--symbols", nargs="*", default=SYMBOLS)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--gate", choices=list(GATE_MAP), default="trend",
                    help="which ensemble verdict(s) to keep (default trend = production)")
    ap.add_argument("--wipe-scope", choices=["none", "year", "all"], default=None)
    args = ap.parse_args()
    global GATE_VERDICTS
    GATE_VERDICTS = GATE_MAP[args.gate]
    if not args.dry_run and args.wipe_scope is None:
        raise SystemExit("Real run requires --wipe-scope {none|year|all} (or --dry-run).")

    now = pd.Timestamp.now(tz="UTC")
    w_start = pd.Timestamp(f"{args.year}-01-01", tz="UTC")
    w_end = min(pd.Timestamp(f"{args.year + 1}-01-01", tz="UTC"), now)
    ens_start = int((w_start - pd.Timedelta(days=ENSEMBLE_WARMUP_DAYS)).timestamp() * 1000)
    print(f"=== RANGE backfill {args.year} | RANGE_DEV full-TP | gate=ensemble{sorted(GATE_VERDICTS)} "
          f"| {len(args.symbols)} symbols | dry_run={args.dry_run} ===", flush=True)

    all_rows = []
    for sym in args.symbols:
        try:
            kl = fetch_4h(sym, ens_start)
            roll = RE.build_rolling(kl) if len(kl) >= 80 else None
            all_rows += run_symbol(sym, w_start, w_end, roll)
        except Exception as e:
            print(f"  ! {sym}: {e}", flush=True)

    n, w, r = tot(all_rows)
    print(f"\nRANGE total: resolved={n} WR={w/n*100 if n else 0:.0f}% topR={r:+.1f} "
          f"(rows={len(all_rows)})", flush=True)
    if args.dry_run:
        print(f"[dry-run] {len(all_rows)} 'range' rows would upsert — no DB write.")
        return
    conn = tsc.backtest_conn()
    if args.wipe_scope in ("year", "all"):
        print(f"wiped {wipe(conn, args.wipe_scope, w_start, w_end)} existing 'range' rows")
    up = tsc.upsert_rows(conn, all_rows)
    conn.close()
    print(f"upserted {up} 'range' rows into {tsc.TABLE}")


if __name__ == "__main__":
    main()
