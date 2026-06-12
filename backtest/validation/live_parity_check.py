"""Live-vs-backtest signal parity check for the NEW engine (deployed 2026-06-10).

Two directions, per symbol, over every closed 1h bar since the new engine's
first live scan (bar open >= DEPLOY_TS, scanned by the 16:01 UTC cron):

  forward : every live row (ict_trade.signals, mode='live') must be reproduced
            by the BACKTEST engine (backtest/engine.py + ict strategies) at the
            same bar — direction + entry/SL/TP within REL_TOL.
  reverse : every signal the backtest engine produces in the window must exist
            in the live table (no missed, no extra emissions).

The backtest side re-fetches the same 6000h Binance window the DAG uses and runs
the production strategy set (B/C/D/E), so this cross-validates the two engine
implementations AND the live emission path end-to-end.

Bars whose cron run hasn't had time to fire+write yet (open + 1h + GRACE > now)
are excluded to avoid race false-positives.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))          # backtest/  (engine, ict)
sys.path.insert(0, str(HERE.parent))              # validation/ (db)

from db import live_conn                           # noqa: E402
from ict.data import fetch_klines                  # noqa: E402
from ict import config as C                        # noqa: E402
from ict.strategies import (                       # noqa: E402
    strategy_b, strategy_c, strategy_d, strategy_e,
)
from engine import run_engine                      # noqa: E402

DAG_STRATS = [strategy_b, strategy_c, strategy_d, strategy_e]
DEPLOY_TS = pd.Timestamp("2026-06-10 15:00:00", tz="UTC")  # first new-engine bar
REL_TOL = 1e-4
GRACE_MIN = 6        # cron fires at HH:01; allow until HH:06 before expecting a row
WARMUP_HOURS = 6000  # mirrors dag.py

# Production set — mirrors dag/dag.py SYMBOLS (post 2026-06-10 cut).
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
    "1000PEPEUSDT", "WIFUSDT", "SUIUSDT",
    "NEARUSDT", "FETUSDT", "ADAUSDT", "SUSDT",
    "ARBUSDT", "ORDIUSDT", "ONDOUSDT",
    "XAUUSDT", "XAGUSDT",
    "NVDAUSDT", "METAUSDT",
    "AMZNUSDT", "COINUSDT", "MSTRUSDT",
    # 2026-06-12 tokenized-equity expansion (PLTR/TSLA re-added by user decision,
    # reversing the 2026-06-10 cut). Listings span 2026-01-28 .. 2026-06-08.
    "CRCLUSDT", "PLTRUSDT", "TSLAUSDT", "INTCUSDT", "HOODUSDT",
    "MSFTUSDT", "AVGOUSDT", "BABAUSDT", "BXUSDT", "HPEUSDT",
    "AMATUSDT", "CRWDUSDT", "CRDOUSDT", "AAOIUSDT", "IWMUSDT",
]


def trim_open_bar(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or len(df) < 2:
        return df
    bm = float((df.index[1] - df.index[0]).total_seconds()) / 60.0
    if pd.Timestamp.now(tz="UTC") < df.index[-1] + pd.Timedelta(minutes=bm):
        return df.iloc[:-1]
    return df


def rel_eq(a, b) -> bool:
    if a is None or b is None:
        return a is b
    a, b = float(a), float(b)
    return abs(a - b) <= REL_TOL * max(abs(a), abs(b), 1e-12)


def fetch_live_rows():
    conn = live_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT symbol, signal_time, direction, entry, sl, tp
        FROM ict_trade.signals
        WHERE mode = 'live' AND signal_time >= %s
        ORDER BY symbol, signal_time
    """, (DEPLOY_TS.to_pydatetime(),))
    rows = [
        {"symbol": r[0],
         "ts": pd.Timestamp(r[1]).tz_convert("UTC") if pd.Timestamp(r[1]).tzinfo else pd.Timestamp(r[1], tz="UTC"),
         "direction": r[2].lower(),
         "entry": float(r[3]), "sl": float(r[4]), "tp": float(r[5])}
        for r in cur.fetchall()
    ]
    cur.close()
    conn.close()
    return rows


def engine_signals_for(symbol: str, now: pd.Timestamp):
    start = now - pd.Timedelta(hours=WARMUP_HOURS)
    df = fetch_klines(symbol, "1h", int(start.timestamp() * 1000), int(now.timestamp() * 1000))
    if df.empty:
        return None, "no data"
    df = trim_open_bar(df)
    if len(df) < 60:
        return None, f"only {len(df)} bars"
    sigs = run_engine(symbol, df, strategies=DAG_STRATS)
    # keep only bars in the check window whose cron emission moment has passed
    out = []
    for s in sigs:
        if s.timestamp < DEPLOY_TS:
            continue
        cron_due = s.timestamp + pd.Timedelta(hours=1, minutes=GRACE_MIN)
        if cron_due > now:
            continue
        out.append(s)
    return out, None


def main():
    # Make sure at least one new-engine cron emission window has fully passed.
    first_due = DEPLOY_TS + pd.Timedelta(hours=1, minutes=GRACE_MIN)  # 16:06 UTC
    while pd.Timestamp.now(tz="UTC") < first_due:
        wait_s = (first_due - pd.Timestamp.now(tz="UTC")).total_seconds()
        print(f"waiting {wait_s:.0f}s for the first new-engine cron window to close...",
              flush=True)
        time.sleep(min(60, max(5, wait_s)))

    now = pd.Timestamp.now(tz="UTC")
    live = fetch_live_rows()
    live_keys = {(r["symbol"], r["ts"], r["direction"]): r for r in live}
    print(f"window: {DEPLOY_TS} .. now={now:%Y-%m-%d %H:%M} UTC | "
          f"live rows in window: {len(live)}", flush=True)

    reproduced, mismatched, missing_in_live, errors = [], [], [], []
    checked_live_keys = set()

    for sym in SYMBOLS:
        sigs, err = engine_signals_for(sym, now)
        if err:
            errors.append((sym, err))
            print(f"  {sym:<13} ERROR: {err}", flush=True)
            continue
        sym_live = {k: v for k, v in live_keys.items() if k[0] == sym}
        for s in sigs:
            key = (sym, s.timestamp, s.direction)
            row = sym_live.get(key)
            if row is None:
                missing_in_live.append((sym, s.timestamp, s.direction, s.strategy))
                continue
            checked_live_keys.add(key)
            if rel_eq(row["entry"], s.entry) and rel_eq(row["sl"], s.stop_loss) \
               and rel_eq(row["tp"], s.take_profit_1):
                reproduced.append(key)
            else:
                mismatched.append((sym, s.timestamp, s.direction,
                                   (row["entry"], s.entry),
                                   (row["sl"], s.stop_loss),
                                   (row["tp"], s.take_profit_1)))
        n_bt = len(sigs)
        n_lv = len(sym_live)
        print(f"  {sym:<13} backtest={n_bt} live={n_lv}", flush=True)

    extra_in_live = [k for k in live_keys if k not in checked_live_keys
                     and not any(e[0] == k[0] for e in errors)]

    print("\n" + "=" * 64, flush=True)
    print(f"reproduced (live == backtest, fiyatlar {REL_TOL:g} tol): {len(reproduced)}")
    print(f"price MISMATCH: {len(mismatched)}")
    for m in mismatched[:10]:
        print(f"   {m[0]} {m[1]} {m[2]} entry(live,bt)={m[3]} sl={m[4]} tp={m[5]}")
    print(f"backtest produced but MISSING in live: {len(missing_in_live)}")
    for m in missing_in_live[:10]:
        print(f"   {m[0]} {m[1]} {m[2]} [{m[3]}]")
    print(f"live rows NOT produced by backtest (extra): {len(extra_in_live)}")
    for k in extra_in_live[:10]:
        print(f"   {k[0]} {k[1]} {k[2]}")
    if errors:
        print(f"symbols skipped on data errors: {errors}")

    ok = not mismatched and not missing_in_live and not extra_in_live
    print("\nRESULT:", "PASS — canlı ≡ backtest" if ok else "FAIL — yukarıdaki farklara bak")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
