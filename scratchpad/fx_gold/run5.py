"""Iteration 5: the research's mandatory robustness gates.
  A) liquid-hours (Neely-Weller): where does R come from by hour; does it survive London-NY overlap only?
  B) concentration: remove best day / best trade / news-window days -> still positive?
  C) synthetic-price guard: recompute ATR on OPEN bars only; confirm result stable.
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
n = len(df)
CFG = Cfg(cost_rt=0.50, max_hold_min=480, trail_mult=3.5)

side, stop, _ = S.vwap_trend(df, slope_n=60, atr_mult=1.5, atr=ATR15)
target = np.full(n, np.nan)
tr = backtest(df, side, stop, target, CFG, atr=atr)
tr["utc_hour"] = tr["entry_time"].dt.hour
tr["day"] = tr["entry_time"].dt.date

print(f"BASE: totR={tr.r.sum():.1f}  n={len(tr)}")

print("\n=== A) R by ENTRY UTC hour (liquid overlap = 13:00-17:00 UTC) ===")
byh = tr.groupby("utc_hour")["r"].agg(["sum", "count", "mean"]).round(2)
print(byh.to_string())
overlap = tr[(tr.utc_hour >= 13) & (tr.utc_hour < 17)]
london = tr[(tr.utc_hour >= 7) & (tr.utc_hour < 17)]   # London + overlap
asia = tr[(tr.utc_hour >= 22) | (tr.utc_hour < 7)]
for lbl, g in [("overlap 13-17 UTC", overlap), ("London+overlap 7-17", london), ("Asia/thin 22-07", asia)]:
    if len(g):
        s = stats(g, CFG); print(f"  {lbl:22s} n={s['n']:4d} totR={s['totR']:+6.1f} pf={s['pf']:.2f} avgR={s['avgR']:+.3f}")

print("\n  -> RE-RUN strategy with entries RESTRICTED to liquid hours only (signal masked):")
et_hour = df.index.tz_convert("America/New_York").hour.to_numpy()
utc_hour = df.index.hour.to_numpy()
for lbl, mask_keep in [("overlap 13-17 UTC", (utc_hour >= 13) & (utc_hour < 17)),
                        ("London+NY 7-21 UTC", (utc_hour >= 7) & (utc_hour < 21))]:
    s2 = side.copy(); s2[~mask_keep] = 0
    tr2 = backtest(df, s2, stop, target, CFG, atr=atr)
    sp = split_stats(tr2, CFG)
    a, i, o = sp["all"], sp["is"], sp["oos"]
    print(f"  {lbl:20s} n={a['n']:4d} totR={a['totR']:+6.1f} pf={a['pf']:.2f} | IS={i['totR']:+.1f} OOS={o['totR']:+.1f}")

print("\n=== B) Concentration / drop-the-best robustness ===")
day_r = tr.groupby("day")["r"].sum().sort_values(ascending=False)
print("  top-5 days by R:", [(str(d), round(v,1)) for d, v in day_r.head(5).items()])
print(f"  drop single best TRADE ({tr.r.max():.1f}R): totR={tr.r.sum()-tr.r.max():.1f}")
print(f"  drop best 3 trades: totR={tr.r.sum()-tr.r.nlargest(3).sum():.1f}")
print(f"  drop best DAY ({day_r.index[0]}, {day_r.iloc[0]:.1f}R): totR={tr.r.sum()-day_r.iloc[0]:.1f}")
print(f"  drop best 3 DAYS: totR={tr.r.sum()-day_r.head(3).sum():.1f}")
print(f"  drop best 5%% of trades: totR={tr.r.sum()-tr.r.nlargest(max(1,len(tr)//20)).sum():.1f}  (remaining 95%%)")
# crude bootstrap on per-day R
rng = np.random.default_rng(7)
days = day_r.values
boot = np.array([rng.choice(days, size=len(days), replace=True).sum() for _ in range(2000)])
print(f"  per-day bootstrap totR: mean={boot.mean():.1f} 5th={np.percentile(boot,5):.1f} 95th={np.percentile(boot,95):.1f} P(>0)={(boot>0).mean():.3f}")

print("\n=== C) Synthetic-price guard: ATR & VWAP from OPEN bars only ===")
# recompute ATR15 using only open-market bars (closed/frozen bars dropped before resample)
dfo = df[df.open_mkt].copy()
atr_open = S.atr_tf(dfo, "15min", 14).reindex(df.index, method="ffill").to_numpy()
side_o, stop_o, _ = S.vwap_trend(df, slope_n=60, atr_mult=1.5, atr=pd.Series(atr_open, index=df.index))
tr_o = backtest(df, side_o, stop_o, target, CFG, atr=atr_open)
sp = split_stats(tr_o, CFG); a = sp["all"]
print(f"  ATR-on-open-bars: n={a['n']} totR={a['totR']:+.1f} pf={a['pf']:.2f} | IS={sp['is']['totR']:+.1f} OOS={sp['oos']['totR']:+.1f}  (vs base +115)")
