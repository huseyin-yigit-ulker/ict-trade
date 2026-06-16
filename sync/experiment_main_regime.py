"""EXPERIMENT (backtest-only, no DB write): how does MAIN change in 2026 on crypto
if we keep only the signals fired while the regime MAP (6-detector ensemble) verdict
is TREND?

"main = OPUS running at all times" = the MAIN signal set (strategies B/C/D/E, full-TP),
WITHOUT OPUS's per-symbol NY-session gate — i.e. the plain v1 engine, every hour. We
then re-gate it by the causal 6-detector ensemble verdict (sync/regime_ensemble.py,
the same regime map the RANGE stream gates on) and split the R by verdict.

Crypto universe only (drops metals XAU/XAG and the tokenized-equity perps). Full-TP
exit, fees in (tsc.simulate). Causal, no look-ahead: the verdict used for a signal is
the ensemble score of the last 4h bar CLOSED before the signal fires (open + 1h).

Usage:
  python sync/experiment_main_regime.py            # full crypto universe, 2026
  python sync/experiment_main_regime.py --symbols BTCUSDT ETHUSDT
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request

import pandas as pd

import trade_sync_common as tsc           # adds backtest/ to sys.path
from ict import config as C               # noqa: E402
import regime_ensemble as RE              # noqa: E402  6-detector ensemble (port of regimeDetectors.js)

from engine import run_engine                                              # noqa: E402
from ict.strategies import strategy_b, strategy_c, strategy_d, strategy_e  # noqa: E402

DAG_STRATS = [strategy_b, strategy_c, strategy_d, strategy_e]   # MAIN set (= what OPUS runs)
WARMUP_HOURS = 6000                       # ~250d engine/detector warmup (matches backfill_year)
ENSEMBLE_WARMUP_DAYS = 60                 # 4h-kline warmup so the 150-bar window is full at y-start
HOUR_MS = 3_600_000                       # signal fires at bar close = open + 1h (ltf 1h)

# Crypto-only production universe (backfill_year.SYMBOLS minus metals + stock perps).
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
    "1000PEPEUSDT", "WIFUSDT", "SUIUSDT",
    "NEARUSDT", "FETUSDT", "ADAUSDT", "SUSDT",
    "ARBUSDT", "ORDIUSDT", "ONDOUSDT",
    "XRPUSDT", "DOGEUSDT", "LINKUSDT", "AVAXUSDT",
]


def fetch_4h(symbol, start_ms):
    """Raw 4h Binance klines from start_ms -> now (paginated), for the ensemble."""
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


def run_symbol(symbol, w_start, w_end):
    end = pd.Timestamp.now(tz="UTC")
    df = tsc.fetch_1h(symbol, w_start - pd.Timedelta(hours=WARMUP_HOURS), end)
    if df is None or df.empty:
        print(f"  {symbol:<12} SKIP (no 1h data)", flush=True)
        return []
    signals = [s for s in run_engine(symbol, df, strategies=DAG_STRATS)
               if w_start <= s.timestamp < w_end]
    if not signals:
        print(f"  {symbol:<12} 0 MAIN signals in window", flush=True)
        return []

    # causal regime ensemble
    ens_start = int((w_start - pd.Timedelta(days=ENSEMBLE_WARMUP_DAYS)).timestamp() * 1000)
    kl = fetch_4h(symbol, ens_start)
    roll = RE.build_rolling(kl) if len(kl) >= 80 else None

    df1m = tsc.fetch_1m(symbol, w_start - pd.Timedelta(hours=2), min(w_end, end))
    rows = []
    prev = C.PARTIAL_TP_ENABLED
    try:
        C.PARTIAL_TP_ENABLED = False                       # FULL TP only (= MAIN/OPUS exit)
        for s in signals:
            fire_ms = int(s.timestamp.timestamp() * 1000) + HOUR_MS
            sc = RE.score_at(roll, fire_ms) if roll else float("nan")
            v = RE.verdict(sc)
            res = tsc.simulate(symbol, s.timestamp, s.direction, s.entry, s.stop_loss,
                               s.take_profit_1, df1m=df1m)
            rows.append({"symbol": symbol, "ts": s.timestamp, "verdict": v,
                         "status": res["status"], "pnl_r": res["pnl_r"]})
    finally:
        C.PARTIAL_TP_ENABLED = prev
    resolved = [r for r in rows if r["status"] in ("closed_tp", "closed_sl") and r["pnl_r"] is not None]
    by = {k: 0 for k in ("trend", "transition", "range")}
    for r in resolved:
        by[r["verdict"]] = by.get(r["verdict"], 0) + 1
    tot = sum(r["pnl_r"] for r in resolved)
    print(f"  {symbol:<12} {len(signals)} sig -> {len(resolved)} resolved  totR={tot:+.1f}  "
          f"verdict_n={by}", flush=True)
    return rows


def stat(rows):
    res = [r for r in rows if r["status"] in ("closed_tp", "closed_sl") and r["pnl_r"] is not None]
    n = len(res)
    if not n:
        return (0, 0.0, 0.0, 0.0)
    w = sum(1 for r in res if r["pnl_r"] > 0)
    tot = sum(r["pnl_r"] for r in res)
    return (n, w / n * 100, tot, tot / n)


def line(label, rows):
    n, wr, tot, avg = stat(rows)
    return f"{label:<22}{n:>6}{wr:>7.0f}%{tot:>10.1f}{avg:>+9.3f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--symbols", nargs="*", default=SYMBOLS)
    args = ap.parse_args()

    now = pd.Timestamp.now(tz="UTC")
    w_start = pd.Timestamp(f"{args.year}-01-01", tz="UTC")
    w_end = min(pd.Timestamp(f"{args.year + 1}-01-01", tz="UTC"), now)
    print(f"=== MAIN x regime-map(ensemble) | crypto | {w_start.date()}..{w_end.date()} | "
          f"{len(args.symbols)} symbols | full-TP ===", flush=True)

    all_rows = []
    for sym in args.symbols:
        try:
            all_rows += run_symbol(sym, w_start, w_end)
        except Exception as e:
            print(f"  ! {sym}: {e}", flush=True)

    trend = [r for r in all_rows if r["verdict"] == "trend"]
    trans = [r for r in all_rows if r["verdict"] == "transition"]
    rng = [r for r in all_rows if r["verdict"] == "range"]

    print("\n" + "=" * 60)
    print(f"{'bucket':<22}{'n':>6}{'WR':>8}{'totR':>10}{'avgR':>9}")
    print("-" * 60)
    print(line("MAIN all (baseline)", all_rows))
    print(line("  regime=TREND", trend))
    print(line("  regime=transition", trans))
    print(line("  regime=RANGE", rng))
    print("-" * 60)
    bn, _, btot, _ = stat(all_rows)
    tn, _, ttot, _ = stat(trend)
    print(f"GATE to TREND only: keep {tn}/{bn} trades, "
          f"totR {btot:+.1f} -> {ttot:+.1f} ({ttot - btot:+.1f} R), "
          f"drop {bn - tn} trades worth {btot - ttot:+.1f} R")

    # per-symbol trend-only table (which symbols carry the trend-gated stream)
    print("\n--- per-symbol, regime=TREND only ---")
    print(f"{'symbol':<14}{'n':>5}{'WR':>7}{'totR':>9}{'avgR':>8}")
    syms = sorted({r["symbol"] for r in trend})
    for s in syms:
        n, wr, tot, avg = stat([r for r in trend if r["symbol"] == s])
        print(f"{s:<14}{n:>5}{wr:>6.0f}%{tot:>9.1f}{avg:>+8.2f}")


if __name__ == "__main__":
    main()
