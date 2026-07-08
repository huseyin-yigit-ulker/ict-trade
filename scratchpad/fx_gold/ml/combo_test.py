"""Follow-up: does the meta-model add value ON TOP of the shipped AFTER-LOSS gate, or at
matched trade count? Train 24+25 -> test 26 (the deployable direction)."""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import lightgbm as lgb

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from meta_midas import FEATURES, LGB_PARAMS, DATASET, book_stats, show  # noqa: E402

ds = pd.read_pickle(DATASET)
y = ds["y"].to_numpy()
tr = ds["source"].isin(["paxg24", "paxg25"])
te = ds["source"] == "xau26"
mdl = lgb.LGBMClassifier(**LGB_PARAMS).fit(ds.loc[tr, FEATURES], y[tr])
t26 = ds.loc[te].reset_index(drop=True)
p = mdl.predict_proba(t26[FEATURES])[:, 1]
al = ((t26["had_prev"] == 1) & (t26["prev_r_day"] < 0)).to_numpy()

def row(mask, label):
    d = t26.loc[mask]
    return dict(book_stats(d["r"].to_numpy(), label), takerR=round(float(d["r_taker"].sum()), 1))

rows = [row(np.ones(len(t26), bool), "ALL"), row(al, "AFTER-LOSS (shipped)")]
# meta at matched n: top-203 by probability (same count as AFTER-LOSS)
k = int(al.sum())
topk = p >= np.sort(p)[-k]
rows.append(row(topk, f"meta top-{k} (matched n)"))
# combo: AFTER-LOSS AND meta above tau
for tau in (0.40, 0.45, 0.50):
    rows.append(row(al & (p >= tau), f"AFTER-LOSS & p>={tau:.2f}"))
# meta OR: after-loss OR very-high-prob (recover skipped good first-of-day trades)
for tau in (0.55, 0.60):
    rows.append(row(al | (p >= tau), f"AFTER-LOSS | p>={tau:.2f}"))
show(rows, "2026 test — combos vs shipped gate")

# rank information: mean r by OOF-prob quintile on the 2026 test
q = pd.qcut(p, 5, labels=False, duplicates="drop")
print("\nmean r / n by prob quintile (2026):")
print(t26.groupby(q).agg(n=("r", "size"), avg_r=("r", "mean"), tot_r=("r", "sum"),
                         avg_taker=("r_taker", "mean")).round(3).to_string())

# does p add info WITHIN the after-loss subset? quintiles inside AL
pal = p[al]
qal = pd.qcut(pal, 3, labels=False, duplicates="drop")
print("\nwithin AFTER-LOSS subset, r by prob tercile (2026):")
print(t26.loc[al].groupby(qal).agg(n=("r", "size"), avg_r=("r", "mean"), tot_r=("r", "sum"),
                                   avg_taker=("r_taker", "mean")).round(3).to_string())
