"""Iteration 4: anti-overfit + null tests for the VWAP-trend winner.
  1) parameter plateau (is it a ridge or a lucky spike?)
  2) HONEST protocol: pick params by IS(Jan-Apr) ONLY, freeze, report true OOS(May-Jun)
  3) random-entry null (does the VWAP signal beat random entries with the same trail+EOD machinery?)
"""
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
OOS = pd.Timestamp("2026-05-01", tz="UTC")
TARGET = np.full(n, np.nan)


def runcfg(side, stop, trail=3.0, cost=0.50, hold=480):
    cfg = Cfg(cost_rt=cost, max_hold_min=hold, trail_mult=trail)
    tr = backtest(df, side, stop, TARGET, cfg, atr=atr)
    return tr, cfg


print("=== 1) PLATEAU: totR (and min(IS,OOS)) over slope_n x trail_mult, am=1.5, cost$0.50 ===")
print(f"{'slope_n':>8} " + " ".join(f"tr{t:>4}" for t in (1.5, 2.0, 2.5, 3.0, 3.5)))
for sn in (20, 30, 45, 60, 90):
    cells = []
    for tm in (1.5, 2.0, 2.5, 3.0, 3.5):
        side, stop, _ = S.vwap_trend(df, slope_n=sn, atr_mult=1.5, atr=ATR15)
        tr, cfg = runcfg(side, stop, trail=tm)
        sp = split_stats(tr, cfg)
        cells.append(f"{sp['all']['totR']:+5.0f}/{min(sp['is']['totR'],sp['oos']['totR']):+4.0f}")
    print(f"{sn:>8} " + " ".join(cells))
print("  (each cell = ALL totR / worst-half totR; a broad positive region = robust, not overfit)")

print("\n=== 2) HONEST OOS: select params on IS(Jan-Apr) only, freeze, measure OOS(May-Jun) ===")
grid = [(sn, am, tm) for sn in (20,30,45,60,90) for am in (1.0,1.5,2.0) for tm in (1.5,2.0,2.5,3.0,3.5)]
scored = []
for sn, am, tm in grid:
    side, stop, _ = S.vwap_trend(df, slope_n=sn, atr_mult=am, atr=ATR15)
    tr, cfg = runcfg(side, stop, trail=tm)
    is_tr = tr[tr.entry_time < OOS]; oos_tr = tr[tr.entry_time >= OOS]
    if len(is_tr) < 80:
        continue
    scored.append({"sn":sn,"am":am,"tm":tm,
                   "IS_R":stats(is_tr,cfg)["totR"],"IS_pf":stats(is_tr,cfg)["pf"],
                   "OOS_R":stats(oos_tr,cfg)["totR"],"OOS_pf":stats(oos_tr,cfg)["pf"],"OOS_n":len(oos_tr)})
sdf = pd.DataFrame(scored).sort_values("IS_R", ascending=False)
print("Top-5 configs BY IN-SAMPLE rank, with their frozen OOS result:")
print(sdf.head(5).to_string(index=False))
print(f"\nMean frozen-OOS R of the IS-top-5: {sdf.head(5)['OOS_R'].mean():.1f} "
      f"| of IS-top-10: {sdf.head(10)['OOS_R'].mean():.1f}  (positive => the IS edge carries OOS)")

print("\n=== 3) RANDOM-ENTRY NULL (same count, same long/short mix, same trail+EOD machinery) ===")
side, stop, _ = S.vwap_trend(df, slope_n=60, atr_mult=1.5, atr=ATR15)
tr_real, cfg = runcfg(side, stop, trail=3.0)
real_R = stats(tr_real, cfg)["totR"]
n_long = int((tr_real.side > 0).sum()); n_short = int((tr_real.side < 0).sum())
elig = np.where(openmkt & np.isfinite(atr) & (atr > 0))[0]
elig = elig[elig < n - 500]
close = df["close"].to_numpy()
rng = np.random.default_rng(42)
null = []
for seed in range(200):
    rs = np.zeros(n)
    pick = rng.choice(elig, size=min(n_long + n_short, elig.size), replace=False)
    longs = pick[: n_long]; shorts = pick[n_long:]
    rstop = np.full(n, np.nan)
    for p in longs:
        rs[p] = 1; rstop[p] = close[p] - 1.5 * atr[p]
    for p in shorts:
        rs[p] = -1; rstop[p] = close[p] + 1.5 * atr[p]
    trn, _ = runcfg(rs, rstop, trail=3.0)
    null.append(stats(trn, cfg)["totR"])
null = np.array(null)
pct = (null >= real_R).mean()
print(f"Real VWAP-trend totR = {real_R:.1f}")
print(f"Random-entry null: mean={null.mean():.1f}  std={null.std():.1f}  p95={np.percentile(null,95):.1f}  max={null.max():.1f}")
print(f"Fraction of random runs >= real: {pct:.3f}  (low => VWAP entry timing adds real edge beyond trail+drift)")
