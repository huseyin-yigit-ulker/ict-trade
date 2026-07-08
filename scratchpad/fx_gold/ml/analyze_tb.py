"""Deep-dive on the one positive standalone result: TB-LGBM (triple-barrier LightGBM, 15m XAU).
Threshold plateau, monthly/side/exit breakdown, MIDAS-book overlap, feature importance.
Run: .venv/bin/python scratchpad/fx_gold/ml/analyze_tb.py"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
FXG = HERE.parent
sys.path.insert(0, str(HERE))
import ml_signal_xau as S                     # noqa: E402  (sets up strategy/engine paths)
from ml_signal_xau import (build_15m, add_features, tb_label, mirror, walk_forward,  # noqa: E402
                           make_model, FEATS, SL_K, TP_K, HOLD_BARS, E)
from meta_midas import DATASET, book_stats, show   # noqa: E402

QGRID = (0.90, 0.93, 0.95, 0.97, 0.98, 0.99)
S.TAUS = QGRID                                # walk_forward stores a tau column per quantile

d = add_features(build_15m())
yL = tb_label(d, +1); yS = tb_label(d, -1)
X = d[FEATS].copy(); Xm = mirror(X)
pL, pS, aucs = walk_forward(d, X, Xm, yL, yS, "TB-LGBM")

a = d["atr"].to_numpy(); c = d["close"].to_numpy()


def run(tau_arr):
    side = np.zeros(len(d))
    side[(pL >= tau_arr) & np.isfinite(pL)] = 1
    side[(pS >= tau_arr) & np.isfinite(pS) & (side == 0)] = -1
    stop = np.where(side != 0, c - side * SL_K * a, np.nan)
    target = np.where(side != 0, c + side * TP_K * a, np.nan)
    cfg = E.Cfg(cost_rt=0.50, max_hold_min=HOLD_BARS)
    tr = E.backtest(d, side, stop, target, cfg)
    if len(tr):
        tr["r_taker"] = (tr["gross"] - 1e-3 * tr["entry"]) / tr["stop_dist"]
    return tr


print("=== threshold plateau (train-prob quantile -> OOS Mar-Jul economics)")
rows = []
best = None
for q in QGRID:
    tau = d[f"_tau{q}_TB-LGBM"].to_numpy()
    tr = run(tau)
    rows.append(dict(book_stats(tr["r"].to_numpy(), f"q{int(q*100)}"),
                     takerR=round(float(tr["r_taker"].sum()), 1)))
    if q == 0.97:
        best = tr
show(rows, "plateau")

print("\n=== q97 breakdowns")
best["month"] = best["entry_time"].dt.to_period("M").astype(str)
print(best.groupby("month").agg(n=("r", "size"), totR=("r", "sum"), taker=("r_taker", "sum"),
                                wr=("r", lambda x: (x > 0).mean())).round(2).to_string())
print("\nby side:")
print(best.groupby("side").agg(n=("r", "size"), totR=("r", "sum"), wr=("r", lambda x: (x > 0).mean()),
                               taker=("r_taker", "sum")).round(2).to_string())
print("\nby exit reason:")
print(best.groupby("reason").agg(n=("r", "size"), totR=("r", "sum")).round(1).to_string())
print(f"\nmedian hold: {best['hold_min'].median()*15:.0f} min (15m bars)")

# --- overlap with the MIDAS book
ds = pd.read_pickle(DATASET)
mid = ds[ds["source"] == "xau26"]
mid_iv = pd.IntervalIndex.from_arrays(mid["entry_time"], mid["exit_time"], closed="both")
ov = 0
same_dir = 0
for _, t in best.iterrows():
    hits = mid_iv.overlaps(pd.Interval(t["entry_time"], t["exit_time"], closed="both"))
    if hits.any():
        ov += 1
        if (mid.loc[hits, "side"] == t["side"]).any():
            same_dir += 1
print(f"\nMIDAS overlap: {ov}/{len(best)} ML trades overlap an open MIDAS trade "
      f"({same_dir} same-direction)")
mar = pd.Timestamp("2026-03-01", tz="UTC")
mmar = mid[mid["entry_time"] >= mar]
print(f"MIDAS Mar-Jul book: {len(mmar)}tr {mmar['r'].sum():+.1f}R | ML q97: {len(best)}tr "
      f"{best['r'].sum():+.1f}R | combined (independent add): {mmar['r'].sum()+best['r'].sum():+.1f}R")
# daily-R correlation
dm = mmar.set_index("entry_time")["r"].resample("D").sum()
dl = best.set_index("entry_time")["r"].resample("D").sum()
both = pd.concat([dm, dl], axis=1, keys=["midas", "ml"]).fillna(0)
print(f"daily-R corr(MIDAS, ML) = {both['midas'].corr(both['ml']):+.3f}")

# --- feature importance (final-fit on all data, gain)
mdl = make_model("TB-LGBM")
tr_mask = ~np.isnan(yL)
Xtr = pd.concat([X.loc[tr_mask], Xm.loc[~np.isnan(yS)]], ignore_index=True)
ytr = np.concatenate([yL[tr_mask], yS[~np.isnan(yS)]])
mdl.fit(Xtr, ytr)
gain = pd.Series(mdl.booster_.feature_importance("gain"), index=FEATS)
print("\ntop features (gain, full fit):")
print((gain / gain.sum()).sort_values(ascending=False).head(10).round(3).to_string())
