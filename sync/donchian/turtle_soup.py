"""Turtle Soup (false-breakout fade) — complement to dch30_4h. EXPERIMENT, no DB write.

dch30_4h ENTERS on 30m Donchian(55) breakouts and bleeds in market-wide failed-breakout
regimes (choppy / sharp-reversal months). Turtle Soup is the mathematical inverse: it FADES
a failed breakout — a single 30m bar that SWEEPS the 55-bar extreme (wick beyond the prior
channel) but CLOSES back inside → enter against the break (a liquidity-sweep / swing-failure
reversal), targeting the mean. So it should EARN exactly when dch30_4h loses. The decisive
metric is not its standalone R but its MONTHLY-R correlation with dch30_4h (crypto+metal):
negative/low correlation = a genuine diversifier that flattens the combined curve.

Signal (single bar i, fully causal — channel excludes the current bar via shift(1)):
  LONG  : low[i]  < channel_lo[i]  AND close[i] > channel_lo[i]   (swept the low, reclaimed)
  SHORT : high[i] > channel_hi[i]  AND close[i] < channel_hi[i]   (swept the high, reclaimed)
  entry = close[i]; stop = sweep extreme -/+ buffer*ATR; tp = entry +/- RR*risk.

    python sync/donchian/turtle_soup.py --start 2026-01-01            # short backtest + corr
    python sync/donchian/turtle_soup.py --start 2025-01-01 --end 2026-01-01   # OOS
"""
from __future__ import annotations

import os
import sys
import pickle
import argparse
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))
sys.path.insert(0, str(_HERE.parent))
import trade_sync_common as tsc              # noqa: E402
import strategy as strat                     # noqa: E402
from ict import config as C                  # noqa: E402

CACHE = Path(os.environ.get("DONCHIAN_1M_CACHE", "/tmp/donchian1m_cache"))
STOCK = {'NVDAUSDT','METAUSDT','AMZNUSDT','COINUSDT','MSTRUSDT','CRCLUSDT','PLTRUSDT','TSLAUSDT',
         'INTCUSDT','HOODUSDT','MSFTUSDT','AVGOUSDT','BABAUSDT','BXUSDT','HPEUSDT','AMATUSDT',
         'CRWDUSDT','CRDOUSDT','AAOIUSDT','IWMUSDT'}
CRYPTO_METAL = [s for s in strat.SYMBOLS if s not in STOCK]
N = strat.N_ENTRY
BUFFER = 0.10          # stop = sweep extreme -/+ BUFFER*ATR
EXPIRY = 180


def _warmup(): return pd.Timedelta(minutes=30 * (N + strat.ER_N) * 6)


def _load_1m(sym, start, end):
    cf = CACHE / f"{sym}.pkl"
    if cf.exists():
        return pickle.loads(cf.read_bytes())
    df = tsc.fetch_1m(sym, start - pd.Timedelta(hours=2), end)
    if df is not None and not df.empty:
        CACHE.mkdir(exist_ok=True); cf.write_bytes(pickle.dumps(df))
    return df


def signals(df, rr):
    """List of (ts, direction, entry, stop, tp) Turtle-Soup fades on 30m bars."""
    a = strat.atr(df)
    hi = df["high"].rolling(N).max().shift(1)
    lo = df["low"].rolling(N).min().shift(1)
    H, L, Cl = df["high"].values, df["low"].values, df["close"].values
    idx = df.index
    out = []
    for i in range(N + strat.ER_N, len(df)):
        atr_i = a.iloc[i]
        if not (atr_i > 0):
            continue
        loi, hii = lo.iloc[i], hi.iloc[i]
        if loi == loi and L[i] < loi and Cl[i] > loi:          # swept low, closed back above
            entry = Cl[i]; stop = L[i] - BUFFER * atr_i; risk = entry - stop
            if risk > 0:
                out.append((idx[i], "long", entry, stop, entry + rr * risk))
        elif hii == hii and H[i] > hii and Cl[i] < hii:        # swept high, closed back below
            entry = Cl[i]; stop = H[i] + BUFFER * atr_i; risk = stop - entry
            if risk > 0:
                out.append((idx[i], "short", entry, stop, entry - rr * risk))
    return out


def run_symbol(sym, w_start, w_end, rr):
    df = tsc.fetch_klines(sym, "30m", int((w_start - _warmup()).timestamp() * 1000),
                          int(w_end.timestamp() * 1000))
    if df is None or df.empty:
        return []
    sigs = [s for s in signals(df, rr) if w_start <= s[0] < w_end]
    if not sigs:
        return []
    df1m = _load_1m(sym, w_start, w_end)
    if df1m is None or df1m.empty:
        return []
    prev = C.PARTIAL_TP_ENABLED; C.PARTIAL_TP_ENABLED = False
    out = []
    try:
        last_close = None
        for ts, d, entry, stop, tp in sigs:
            if last_close is not None and ts < last_close:     # no-overlap: one fade at a time
                continue
            res = tsc.simulate(sym, ts, d, entry, stop, tp, df1m=df1m, ltf_minutes=30,
                               expiry_minutes=EXPIRY)
            if res["status"] not in ("closed_tp", "closed_sl") or res["pnl_r"] is None:
                continue
            if res.get("exit_time") is not None:
                last_close = pd.Timestamp(res["exit_time"]).tz_convert("UTC")
            out.append({"month": f"{ts.year}-{ts.month:02d}", "r": float(res["pnl_r"]),
                        "win": res["status"] == "closed_tp"})
    finally:
        C.PARTIAL_TP_ENABLED = prev
    return out


def dch30_4h_monthly(w_start, w_end):
    """dch30_4h crypto+metal monthly R from the backtest DB (the complement target)."""
    c = tsc.backtest_conn(); cur = c.cursor()
    cur.execute("""SELECT symbol, signal_time, pnl_r FROM ict_trade.trading_signals
        WHERE version='dch30_4h' AND status IN ('closed_tp','closed_sl') AND pnl_r IS NOT NULL
          AND signal_time >= %s AND signal_time < %s""",
                (w_start.to_pydatetime(), w_end.to_pydatetime()))
    mo = defaultdict(float)
    for sym, ts, r in cur.fetchall():
        if sym in STOCK:
            continue
        mo[f"{ts.year}-{ts.month:02d}"] += float(r)
    c.close()
    return mo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-01-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--rr", nargs="*", type=float, default=[1.5, 2.0, 3.0])
    ap.add_argument("--symbols", nargs="*", default=CRYPTO_METAL)
    args = ap.parse_args()
    w_start = pd.Timestamp(args.start, tz="UTC")
    w_end = pd.Timestamp(args.end, tz="UTC") if args.end else pd.Timestamp.now(tz="UTC")
    print(f"=== Turtle Soup [{w_start.date()}..{w_end.date()}) | {len(args.symbols)} crypto+metal "
          f"| RR={args.rr} ===", flush=True)

    dch_mo = dch30_4h_monthly(w_start, w_end)
    months = sorted(dch_mo)
    dch_vec = np.array([dch_mo[m] for m in months])
    print(f"  dch30_4h crypto+metal monthly R (target): total {sum(dch_vec):+.0f}R over {len(months)} mo")

    for rr in args.rr:
        allrows = []
        for sym in args.symbols:
            try:
                allrows += run_symbol(sym, w_start, w_end, rr)
            except Exception as e:  # noqa: BLE001
                print(f"  ! {sym} (RR{rr}): {e}", flush=True)
        if not allrows:
            print(f"\n--- RR={rr}: no trades ---"); continue
        n = len(allrows); tot = sum(r["r"] for r in allrows)
        wr = 100 * sum(r["win"] for r in allrows) / n
        ts_mo = defaultdict(float)
        for r in allrows:
            ts_mo[r["month"]] += r["r"]
        ts_vec = np.array([ts_mo.get(m, 0.0) for m in months])
        corr = float(np.corrcoef(dch_vec, ts_vec)[0, 1]) if len(months) > 1 and ts_vec.std() > 0 else float("nan")
        # combined book = dch30_4h + turtle soup, monthly
        comb = dch_vec + ts_vec
        negc_d = sum(1 for v in dch_vec if v < 0)
        negc_c = sum(1 for v in comb if v < 0)
        print(f"\n--- RR={rr}: {n} trades  totR={tot:+.0f}  WR={wr:.0f}% ---")
        print(f"    monthly-R corr with dch30_4h = {corr:+.2f}   (negatif = iyi tamamlayıcı)")
        print(f"    negatif ay: dch30_4h {negc_d}/{len(months)}  ->  birleşik {negc_c}/{len(months)}")
        print(f"    en kötü ay: dch30_4h {min(dch_vec):+.0f}  ->  birleşik {min(comb):+.0f}")
        print("    ay     dch30_4h   turtle   birleşik")
        for m, dv, tv, cv in zip(months, dch_vec, ts_vec, comb):
            print(f"    {m}  {dv:>+8.0f} {tv:>+8.0f} {cv:>+8.0f}")


if __name__ == "__main__":
    main()
