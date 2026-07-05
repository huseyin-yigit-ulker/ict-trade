"""Iteration 2: trend-capture (trailing-stop + EOD exit), HTF-trend-filtered momentum, and a
time-of-day drift analysis. 2026-H1 XAUUSDT 1m, market-open only, cost=$0.50 round-trip."""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import data as D
import fxstrat as S
from engine import Cfg, backtest, stats, split_stats

pd.set_option("display.width", 220); pd.set_option("display.max_columns", 30)
import warnings; warnings.filterwarnings("ignore")

df = D.add_market_open(D.load_1m())
ATR15 = S.atr_tf(df, "15min", 14)
atr = ATR15.to_numpy()
C = df["close"]; openmkt = df["open_mkt"].to_numpy(bool)
n = len(df)


def show(name, side, stop, target, trail_mult=0.0, max_hold=0, cost=0.50):
    cfg = Cfg(cost_rt=cost, max_hold_min=max_hold, trail_mult=trail_mult)
    tr = backtest(df, side, stop, target, cfg, atr=atr)
    if tr.empty or len(tr) < 20:
        print(f"{name:34s} n={len(tr)} (too few)"); return None, tr
    sp = split_stats(tr, cfg)
    a, i, oo = sp["all"], sp["is"], sp["oos"]
    print(f"{name:34s} n={a['n']:4d} totR={a['totR']:7.1f} wr={a['wr']:.2f} avgR={a['avgR']:+.3f} pf={a['pf']:.2f} "
          f"dd={a['maxddR']:6.1f} | IS={i['totR']:+6.1f}(pf{i['pf']:.2f}) OOS={oo['totR']:+6.1f}(pf{oo['pf']:.2f}) "
          f"L={sp['long']['totR']:+.0f}/S={sp['short']['totR']:+.0f}")
    return sp, tr


# ---------------- A) ORB with trailing stop + EOD exit (no fixed target) ----------------
print("=== A) ORB + ATR-trail, EOD/session exit (target=none) ===")
best = None
for sess, lbl in [((8, 0), "NY"), ((3, 0), "LDN")]:
    for orm in (15, 30, 60):
        for am in (1.0, 1.5):
            for tm in (2.0, 3.0):
                side, stop, _ = S.orb(df, sess, or_min=orm, entry_window=300, rr=1.0,
                                      stop_mode="atr", atr_mult=am, atr=atr)
                target = np.full(n, np.nan)
                sp, tr = show(f"ORB_{lbl}_or{orm}_atr{am}_trail{tm}", side, stop, target, trail_mult=tm)


# ---------------- B) HTF-trend-filtered intraday momentum + trailing ----------------
print("\n=== B) Trend-continuation: break of prior K-min extreme, HTF-EMA filtered, ATR-trail+EOD ===")
def trend_cont(K=60, ema_span=1440, init_atr=1.5):
    side = np.zeros(n); stop = np.full(n, np.nan); target = np.full(n, np.nan)
    hh = df["high"].shift(1).rolling(K).max().to_numpy()
    ll = df["low"].shift(1).rolling(K).min().to_numpy()
    ema = C.ewm(span=ema_span, adjust=False).mean().to_numpy()
    c = C.to_numpy()
    for k in range(n):
        if not openmkt[k] or not np.isfinite(hh[k]) or not np.isfinite(atr[k]) or atr[k] <= 0:
            continue
        if c[k] > hh[k] and c[k] > ema[k]:
            side[k] = 1; stop[k] = c[k] - init_atr * atr[k]
        elif c[k] < ll[k] and c[k] < ema[k]:
            side[k] = -1; stop[k] = c[k] + init_atr * atr[k]
    return side, stop, target

for K in (30, 60, 120):
    for span, slbl in [(720, "12h"), (1440, "24h")]:
        for tm in (2.0, 3.0):
            side, stop, target = trend_cont(K=K, ema_span=span, init_atr=1.5)
            show(f"TC_K{K}_ema{slbl}_trail{tm}", side, stop, target, trail_mult=tm)


# ---------------- C) VWAP-trend with trailing (vs fixed RR baseline) ----------------
print("\n=== C) VWAP-trend pullback + trailing ===")
for tm in (0.0, 2.0, 3.0):
    side, stop, target = S.vwap_trend(df, rr=2.0, atr_mult=1.5, atr=ATR15)
    if tm > 0:
        target = np.full(n, np.nan)
    show(f"VWAPtrend_trail{tm}", side, stop, target, trail_mult=tm)


# ---------------- D) Time-of-day drift analysis ----------------
print("\n=== D) Time-of-day: mean 60-min forward return ($) by ET hour, market-open bars ===")
o = df[df.open_mkt].copy()
o["fwd60"] = o["close"].shift(-60) - o["close"]
o["ethr"] = o.index.tz_convert("America/New_York").hour
g = o.groupby("ethr")["fwd60"].agg(["mean", "std", "count"])
g["t"] = g["mean"] / (g["std"] / np.sqrt(g["count"]))
print(g.round(3).to_string())
