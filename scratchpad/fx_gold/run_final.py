"""Canonical config: VWAP-trend pullback, slope_n=60, init-stop 1.5*ATR(15m), ATR-trail 3.5x,
intraday-only, 8h max-hold, cost $0.50 round-trip. Full stats + equity + trade diagnostics."""
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
n = len(df)

side, stop, _ = S.vwap_trend(df, slope_n=60, atr_mult=1.5, atr=ATR15)
target = np.full(n, np.nan)
cfg = Cfg(cost_rt=0.50, max_hold_min=480, trail_mult=3.5)
tr = backtest(df, side, stop, target, cfg, atr=atr)
tr.to_csv(HERE / "canonical_trades.csv", index=False)

sp = split_stats(tr, cfg)
print("=== CANONICAL: VWAP-trend pullback (sn60 / stop1.5ATR / trail3.5ATR / 8h cap / $0.50 rt) ===")
for k in ["all", "is", "oos", "long", "short"]:
    s = sp[k]
    print(f"  {s['label']:14s} n={s['n']:4d} totR={s['totR']:7.1f} wr={s['wr']:.2f} avgR={s['avgR']:+.3f} "
          f"pf={s['pf']:.2f} ddR={s['maxddR']:6.1f} ret={s['ret_pct']:+6.1f}% maxdd%={s['maxdd_pct']:+.1f} sharpe={s['sharpe']:+.2f}")
print("  monthly R:", {k: round(v,1) for k,v in sp["monthly"].items()})

# trade diagnostics
print("\n=== diagnostics ===")
print("exit reason:", tr["reason"].value_counts().to_dict())
print(f"avg win R = {tr.loc[tr.r>0,'r'].mean():+.2f}  avg loss R = {tr.loc[tr.r<0,'r'].mean():+.2f}  "
      f"expectancy = {tr['r'].mean():+.3f}R")
print(f"avg hold = {tr['hold_min'].mean():.0f} min (median {tr['hold_min'].median():.0f})  "
      f"trades/day ~ {len(tr)/ (df.open_mkt.sum()/1440):.1f}")
print(f"best trade {tr['r'].max():+.1f}R  worst {tr['r'].min():+.1f}R")
# how much of total R comes from the single best 5% of trades?
rr = tr['r'].sort_values(ascending=False).to_numpy()
top5 = rr[:max(1,len(rr)//20)].sum()
print(f"top-5% trades contribute {top5:.1f}R of {rr.sum():.1f}R ({top5/rr.sum()*100:.0f}%)")

# equity curve (R) sampled
eq = tr.set_index("exit_time")["r"].cumsum()
print("\nequity (R) by month-end:")
print(eq.resample("M").last().round(1).to_string())
