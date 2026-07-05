"""Iteration 3: tune & stress-test the VWAP-trend-pullback + ATR-trailing winner."""
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
import warnings; warnings.filterwarnings("ignore")
pd.set_option("display.width", 240)

df = D.add_market_open(D.load_1m())
ATR15 = S.atr_tf(df, "15min", 14); atr = ATR15.to_numpy()
n = len(df); openmkt = df["open_mkt"].to_numpy(bool)
et_hour = df.index.tz_convert("America/New_York").hour.to_numpy()


def line(name, sp):
    a, i, oo = sp["all"], sp["is"], sp["oos"]
    print(f"{name:30s} n={a['n']:4d} totR={a['totR']:7.1f} wr={a['wr']:.2f} avgR={a['avgR']:+.3f} pf={a['pf']:.2f} "
          f"dd={a['maxddR']:6.1f} sh={a['sharpe']:+.2f} | IS={i['totR']:+6.1f}(pf{i['pf']:.2f}) OOS={oo['totR']:+6.1f}(pf{oo['pf']:.2f}) "
          f"L={sp['long']['totR']:+.0f}/S={sp['short']['totR']:+.0f}")


def run(side, stop, target, trail=2.0, cost=0.50, hold=0):
    cfg = Cfg(cost_rt=cost, max_hold_min=hold, trail_mult=trail)
    tr = backtest(df, side, stop, target, cfg, atr=atr)
    return split_stats(tr, cfg), tr


print("=== 1) Parameter sweep: slope_n x init-stop(atr_mult) x trail_mult (cost $0.50) ===")
best = (-1e9, None)
for slope_n in (15, 30, 60):
    for am in (1.0, 1.5, 2.0):
        for tm in (1.5, 2.0, 2.5, 3.0):
            side, stop, _ = S.vwap_trend(df, rr=2.0, slope_n=slope_n, atr_mult=am, atr=ATR15)
            target = np.full(n, np.nan)
            sp, tr = run(side, stop, target, trail=tm)
            score = min(sp["is"]["totR"], sp["oos"]["totR"])  # robustness = worst half
            if sp["all"]["n"] >= 100 and score > best[0]:
                best = (score, (slope_n, am, tm, sp))
            if am == 1.5 and slope_n == 30:  # print a representative slice
                line(f"sn{slope_n}_am{am}_tr{tm}", sp)
print(f"\nMOST ROBUST (max of min(IS,OOS) R): slope_n={best[1][0]} atr_mult={best[1][1]} trail={best[1][2]}")
line("  -> best", best[1][3])

slope_n, am, tm, _ = best[1]
side, stop, _ = S.vwap_trend(df, rr=2.0, slope_n=slope_n, atr_mult=am, atr=ATR15)
target = np.full(n, np.nan)

print("\n=== 2) Monthly R + cost sweep for the robust config ===")
for cost in (0.2, 0.3, 0.5, 0.8, 1.5):
    sp, tr = run(side, stop, target, trail=tm, cost=cost)
    a = sp["all"]
    print(f"cost=${cost:<4} n={a['n']} totR={a['totR']:7.1f} avgR={a['avgR']:+.3f} pf={a['pf']:.2f}  monthly={sp['monthly']}")
# Binance taker fee scenario (0.04% * price * 2 ~ $3.7 round-trip)
px = df.loc[df.open_mkt, "close"].median()
binance_rt = 0.0004 * px * 2
sp, _ = run(side, stop, target, trail=tm, cost=binance_rt)
print(f"Binance-taker (rt=${binance_rt:.2f}): totR={sp['all']['totR']} pf={sp['all']['pf']}")

print("\n=== 3) Time-of-day filter: drop the worst ET hours (validate it doesn't just curve-fit) ===")
# Build base signals once, then mask by ET hour. Worst hours from drift analysis: 5,8,9,21,22 (and 7,12)
BAD = {5, 7, 8, 9, 12, 21, 22}
for label, badset in [("none", set()), ("drop{5,8,9,21,22}", {5,8,9,21,22}), ("drop{5,7,8,9,12,21,22}", BAD),
                       ("keep-good{2,6,15,16,18,20}", None)]:
    s2 = side.copy()
    if badset is None:
        good = {2, 6, 15, 16, 18, 20}
        mask = ~np.isin(et_hour, list(good))
    else:
        mask = np.isin(et_hour, list(badset))
    s2[mask] = 0
    sp, tr = run(s2, stop, target, trail=tm)
    line(f"TOD_{label}", sp)

print("\n=== 4) Exit-variant check: fixed-RR vs pure-trail vs trail+time-cap ===")
for desc, kw in [("trail-only", dict(trail=tm, hold=0)),
                 ("trail+4h-cap", dict(trail=tm, hold=240)),
                 ("trail+8h-cap", dict(trail=tm, hold=480))]:
    sp, tr = run(side, stop, target, **kw)
    line(desc, sp)
