"""NO-LOOKAHEAD audit for the meta-labeling feature pipeline (truncation test).

Definition of clean: a feature at signal bar i must be computable from bars [0..i] only —
the same information set signals() uses (decision at bar i CLOSE). Mechanical proof: recompute
the ENTIRE feature frame on df truncated at bar i (inclusive) and compare row i with the
full-sample computation. Any dependence on future bars would change the value.

Also audits the sequence features (prev_r_day / cum_r_today): every referenced prior trade must
have exit_time <= the signal bar's close time.

Run: .venv/bin/python scratchpad/fx_gold/ml/lookahead_check_ml.py
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
FXG = HERE.parent
REPO = FXG.parents[1]
sys.path.insert(0, str(REPO / "sync" / "midas"))
sys.path.insert(0, str(HERE))
import strategy as M          # noqa: E402
import features as F          # noqa: E402

RNG = np.random.default_rng(7)
N_SAMPLES = 30


def prep(df):
    df = M.add_market_open(df)
    df["fx_day"] = M._fx_day(df)
    atr = M.atr_tf(df)
    vwap = M.anchored_vwap(df)
    return df, atr, vwap


def full_and_truncated(df):
    df, atr, vwap = prep(df)
    side, stop = M.signals(df, atr)
    sig_idx = np.flatnonzero(side != 0)
    feat_full = F.feature_frame(df, atr, vwap)
    picks = RNG.choice(sig_idx, size=min(N_SAMPLES, len(sig_idx)), replace=False)
    worst = 0.0; worst_info = None
    for i in sorted(picks):
        sub = df.iloc[: i + 1][["open", "high", "low", "close", "volume"]].copy()
        sub_df, sub_atr, sub_vwap = prep(sub)
        feat_sub = F.feature_frame(sub_df, sub_atr, sub_vwap)
        a = feat_full.iloc[i].astype(float)
        b = feat_sub.iloc[-1].astype(float)
        diff = (a - b).abs()
        diff = diff[~(a.isna() & b.isna())].fillna(np.inf)  # NaN-pattern mismatch = failure
        d = float(diff.max()) if len(diff) else 0.0
        if d > worst:
            worst = d; worst_info = (df.index[i], diff.idxmax(), a[diff.idxmax()], b[diff.idxmax()])
    return len(picks), worst, worst_info


def check_sequence(df):
    """prev-trade features must only reference trades fully closed BEFORE the signal bar close."""
    df, atr, vwap = prep(df)
    side, stop = M.signals(df, atr)
    trades = M.walk(df, side, stop, atr.to_numpy())
    bar = pd.Timedelta(minutes=1)
    bad = 0
    for k in range(1, len(trades)):
        sig_close = trades[k].signal_time + bar
        if trades[k - 1].exit_time + bar > sig_close:   # exit bar must complete before signal close
            bad += 1
    return len(trades), bad


if __name__ == "__main__":
    xau = pd.read_pickle(FXG / "xauusdt_1m_2026h1.pkl")[["open", "high", "low", "close", "volume"]]
    ok = True
    for label, d in (("xau26 (Jan-Mar slice)", xau.loc[:"2026-03-31"]),
                     ("xau26 (Apr-Jun slice)", xau.loc["2026-04-01":])):
        n, worst, info = full_and_truncated(d)
        status = "PASS" if worst < 1e-9 else "FAIL"
        ok &= worst < 1e-9
        print(f"[truncation] {label}: {n} signals sampled, max |full-truncated| = {worst:.2e}  {status}")
        if info and worst >= 1e-9:
            print(f"    worst at {info[0]} feature={info[1]} full={info[2]} trunc={info[3]}")
    n, bad = check_sequence(xau)
    status = "PASS" if bad == 0 else "FAIL"
    ok &= bad == 0
    print(f"[sequence]  {n} trades, prev-trade refs closing after signal close: {bad}  {status}")
    print("\nRESULT:", "ALL PASS — no lookahead in the ML feature pipeline" if ok else "LOOKAHEAD DETECTED")
