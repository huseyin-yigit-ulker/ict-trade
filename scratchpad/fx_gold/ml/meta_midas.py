"""Candidate A — MIDAS meta-labeling (LightGBM), the repo's first ML experiment.

Primary model = the SHIPPED MIDAS (signals()+walk(), unchanged, $0.50 FX cost). Meta-model =
LightGBM P(trade R>0) from signal-moment features only. Protocol:

  1. Canonical trade books: XAUUSDT 2026 (Jan-Jul pickles) + PAXGUSDT 2024, 2025 (paxg_cache) —
     same holiday-calendar extension as scratchpad/midas_oos_paxg.py.
  2. Purged chronological 5-fold CV (1-day embargo; labels resolve within 8h so 1 day >> horizon)
     -> out-of-fold probabilities, AUC, threshold economics.
  3. Cross-year transfer: train 2024+25 -> test 2026, and train 2026 -> test 2024+25.
  4. Baselines: ALL trades; the shipped AFTER-LOSS exec gate (prev same-fx-day trade < 0).
  5. Label-shuffle null: same pipeline, y permuted -> AUC must collapse to ~0.5.
  6. Feature importance: mean LightGBM gain across folds + permutation AUC on the transfer test.

Economics are reported under BOTH cost regimes: r (FX $0.50/oz, the MIDAS stream cost) and
r_taker (10 bps of entry — Binance taker, re-derived from each trade's own fills).

CAVEAT (same convention as the shipped AFTER-LOSS backtest): filtering the canonical book does
not re-run the walk, so a skipped trade does NOT free the engine to take an overlapping later
signal. Live exec behaves the same way (paper feed keeps trading everything; the gate is
exec-only), so the convention matches production.

Usage: .venv/bin/python scratchpad/fx_gold/ml/meta_midas.py [--rebuild]
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
import strategy as M            # noqa: E402
import features as F            # noqa: E402
import labels as L              # noqa: E402

import lightgbm as lgb          # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402

DATASET = HERE / "dataset.pkl"
RNG = np.random.default_rng(42)

# same 2024/2025 holiday extension as scratchpad/midas_oos_paxg.py
M.HOLIDAY_FULL_ET = M.HOLIDAY_FULL_ET + (
    "2024-01-01", "2024-03-29", "2024-12-25",
    "2025-01-01", "2025-04-18", "2025-12-25")
M.HOLIDAY_EARLY_ET = M.HOLIDAY_EARLY_ET + (
    "2024-01-15", "2024-02-19", "2024-05-27", "2024-06-19", "2024-07-03",
    "2024-09-02", "2024-11-28", "2024-11-29", "2024-12-24",
    "2025-01-20", "2025-02-17", "2025-05-26", "2025-06-19", "2025-07-03",
    "2025-09-01", "2025-11-27", "2025-11-28", "2025-12-24")

FEATURES = ["dist_vwap", "slope30", "slope60", "slope180", "body", "range_atr", "atr_bps",
            "atr_ratio", "day_ret", "pos_in_range", "day_er", "mins_in", "utc_hour", "dow",
            "vol_z", "touch_depth", "side", "prev_r_day", "had_prev", "n_today", "cum_r_today"]

# fixed, deliberately conservative — NO hyperparameter search (n=~1200, avoid protocol overfit)
LGB_PARAMS = dict(objective="binary", n_estimators=300, learning_rate=0.03, num_leaves=7,
                  min_child_samples=40, colsample_bytree=0.7, subsample=0.8, subsample_freq=1,
                  reg_lambda=5.0, random_state=42, verbose=-1)


# ---------------------------------------------------------------- dataset
def _build_period(label: str, df: pd.DataFrame, start: pd.Timestamp) -> pd.DataFrame:
    df = M.add_market_open(df)
    df["fx_day"] = M._fx_day(df)
    atr = M.atr_tf(df)
    side, stop = M.signals(df, atr)
    trades = [t for t in M.walk(df, side, stop, atr.to_numpy()) if t.entry_time >= start]
    print(f"  {label}: {len(trades)} trades, totR={sum(t.pnl_r for t in trades):+.1f}", flush=True)
    vwap = M.anchored_vwap(df)
    feat = F.feature_frame(df, atr, vwap, slope_n=M.SLOPE_N, touch_tol=M.TOUCH_TOL)
    idx = df.index.get_indexer(pd.DatetimeIndex([t.signal_time for t in trades]))
    assert (idx >= 0).all(), f"{label}: signal_time not found in df index"
    X = F.signal_features(feat, idx, np.array([t.side for t in trades]))
    meta = L.meta_frame(trades, df)
    out = pd.concat([meta, X.drop(columns=["side"])], axis=1)   # side already in meta
    out["source"] = label
    return out


def build_dataset() -> pd.DataFrame:
    print("building dataset ...", flush=True)
    # XAU 2026 (Jan..Jul-7)
    xa = pd.read_pickle(FXG / "xauusdt_1m_2026h1.pkl")
    xj = pd.read_pickle(FXG / "xau_jul2026.pkl")
    xau = pd.concat([xa, xj])
    xau = xau[~xau.index.duplicated()].sort_index()[["open", "high", "low", "close", "volume"]]
    parts = [_build_period("xau26", xau, pd.Timestamp("2026-01-01", tz="UTC"))]
    # PAXG 2024 / 2025 (cached by midas_oos_paxg.py)
    for label, fn, y0, y1 in (
            ("paxg24", "PAXGUSDT_2023-12-30_2025-01-01.pkl", "2024-01-01", "2025-01-01"),
            ("paxg25", "PAXGUSDT_2024-12-30_2026-01-01.pkl", "2025-01-01", "2026-01-01")):
        df = pd.read_pickle(REPO / "scratchpad" / "paxg_cache" / fn)
        df = df.loc[df.index < pd.Timestamp(y1, tz="UTC")]
        parts.append(_build_period(label, df, pd.Timestamp(y0, tz="UTC")))
    ds = pd.concat(parts, ignore_index=True).sort_values("entry_time").reset_index(drop=True)
    ds.to_pickle(DATASET)
    return ds


# ---------------------------------------------------------------- evaluation helpers
def book_stats(r: np.ndarray, label: str = "") -> dict:
    if len(r) == 0:
        return dict(label=label, n=0, totR=0.0, wr=0.0, avgR=0.0, pf=0.0, maxddR=0.0)
    eq = r.cumsum(); dd = float((eq - np.maximum.accumulate(eq)).min())
    wins = r[r > 0].sum(); losses = -r[r < 0].sum()
    return dict(label=label, n=len(r), totR=round(float(r.sum()), 1),
                wr=round(float((r > 0).mean()), 3), avgR=round(float(r.mean()), 3),
                pf=round(float(wins / losses) if losses > 0 else float("inf"), 2),
                maxddR=round(dd, 1))


def show(rows: list[dict], title: str):
    print(f"\n--- {title}")
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))


def purged_oof(ds: pd.DataFrame, y: np.ndarray, n_folds: int = 5,
               embargo: pd.Timedelta = pd.Timedelta(days=1)) -> np.ndarray:
    """Chronological contiguous folds; train drops anything within `embargo` of the test window."""
    t = ds["entry_time"].to_numpy()
    bounds = np.linspace(0, len(ds), n_folds + 1).astype(int)
    oof = np.full(len(ds), np.nan)
    for f in range(n_folds):
        lo, hi = bounds[f], bounds[f + 1]
        t0, t1 = t[lo], t[hi - 1]
        tr_mask = (t < t0 - embargo) | (t > t1 + embargo)
        mdl = lgb.LGBMClassifier(**LGB_PARAMS)
        mdl.fit(ds.loc[tr_mask, FEATURES], y[tr_mask])
        oof[lo:hi] = mdl.predict_proba(ds.iloc[lo:hi][FEATURES])[:, 1]
    return oof


def threshold_table(ds: pd.DataFrame, p: np.ndarray, taus) -> list[dict]:
    rows = [dict(book_stats(ds["r"].to_numpy(), "ALL (no filter)"),
                 takerR=round(float(ds["r_taker"].sum()), 1))]
    al = (ds["had_prev"] == 1) & (ds["prev_r_day"] < 0)
    rows.append(dict(book_stats(ds.loc[al, "r"].to_numpy(), "AFTER-LOSS gate"),
                     takerR=round(float(ds.loc[al, "r_taker"].sum()), 1)))
    for tau in taus:
        m = p >= tau
        rows.append(dict(book_stats(ds.loc[m, "r"].to_numpy(), f"meta p>={tau:.2f}"),
                         takerR=round(float(ds.loc[m, "r_taker"].sum()), 1)))
    return rows


# ---------------------------------------------------------------- main
def main(rebuild: bool = False):
    ds = build_dataset() if (rebuild or not DATASET.exists()) else pd.read_pickle(DATASET)
    y = ds["y"].to_numpy()
    print(f"\ndataset: {len(ds)} trades | win-rate {y.mean():.3f}")
    for src, g in ds.groupby("source"):
        print(f"  {src}: n={len(g)}  totR={g['r'].sum():+.1f}  takerR={g['r_taker'].sum():+.1f}"
              f"  WR={g['y'].mean():.3f}")

    taus = np.round(np.arange(0.40, 0.66, 0.05), 2)

    # 1) pooled purged CV
    oof = purged_oof(ds, y)
    print(f"\n[1] purged 5-fold CV (1-day embargo)  OOF AUC = {roc_auc_score(y, oof):.3f}")
    show(threshold_table(ds, oof, taus), "OOF threshold economics (whole pool)")
    for src, g in ds.groupby("source"):
        show(threshold_table(g, oof[g.index.to_numpy()], [0.50, 0.55]),
             f"OOF economics — {src} (AUC {roc_auc_score(g['y'], oof[g.index.to_numpy()]):.3f})")

    # 2) cross-year transfer
    for tr_srcs, te_srcs, name in ((["paxg24", "paxg25"], ["xau26"], "train 24+25 -> test 26"),
                                   (["xau26"], ["paxg24", "paxg25"], "train 26 -> test 24+25")):
        tr = ds["source"].isin(tr_srcs); te = ds["source"].isin(te_srcs)
        mdl = lgb.LGBMClassifier(**LGB_PARAMS)
        mdl.fit(ds.loc[tr, FEATURES], y[tr])
        p = mdl.predict_proba(ds.loc[te, FEATURES])[:, 1]
        auc = roc_auc_score(y[te], p)
        print(f"\n[2] TRANSFER {name}: test AUC = {auc:.3f}")
        show(threshold_table(ds.loc[te].reset_index(drop=True), p, taus), f"transfer economics — {name}")
        if te_srcs == ["xau26"]:
            perm_ref = (mdl, ds.loc[te, FEATURES].reset_index(drop=True), y[te])

    # 3) label-shuffle null
    y_sh = RNG.permutation(y)
    oof_sh = purged_oof(ds, y_sh)
    print(f"\n[3] NULL (label shuffle): OOF AUC = {roc_auc_score(y_sh, oof_sh):.3f}  (must be ~0.50)")

    # 4) importance — mean gain across CV folds + permutation AUC drop on the 26-transfer test
    mdl_all = lgb.LGBMClassifier(**LGB_PARAMS).fit(ds[FEATURES], y)
    gain = pd.Series(mdl_all.booster_.feature_importance("gain"), index=FEATURES)
    print("\n[4] feature importance (gain, full-pool fit):")
    print((gain / gain.sum()).sort_values(ascending=False).round(3).to_string())
    mdl, Xte, yte = perm_ref
    base = roc_auc_score(yte, mdl.predict_proba(Xte)[:, 1])
    drops = {}
    for col in FEATURES:
        Xp = Xte.copy(); Xp[col] = RNG.permutation(Xp[col].to_numpy())
        drops[col] = base - roc_auc_score(yte, mdl.predict_proba(Xp)[:, 1])
    print("\n    permutation AUC-drop on transfer test (24+25 -> 26), top 10:")
    print(pd.Series(drops).sort_values(ascending=False).head(10).round(4).to_string())


if __name__ == "__main__":
    main(rebuild="--rebuild" in sys.argv)
