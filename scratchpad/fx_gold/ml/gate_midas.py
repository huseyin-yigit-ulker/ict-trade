"""Higher-frequency REGIME GATE for MIDAS (2026, XAUUSDT) — can a larger-timeframe model decide
whether MIDAS should trade at all?

Two gate designs, both evaluated with a 3-model ENSEMBLE (logistic + random-forest + LightGBM,
probability mean) under purged chronological CV:

V1  FX-DAY GATE — one decision per fx-day at anchor-open + 120 min. MATURE_MIN=120 guarantees no
    MIDAS entry before that moment, so the day's first 2 hours (18:00-20:00 ET) are a leak-free
    information window. Features: first-2h behavior (ret/range/ER/VWAP-slope/vol) + previous-day
    price & MIDAS-book stats + 3-day context + DOW. Label: does the day's MIDAS trade sum end > 0?
    Gate keeps/skips the WHOLE day's trades.

V2  TRADE-TIME, HIGHER-TF-ONLY GATE — per signal, but features are ONLY multi-hour/day context
    (2h/6h/24h efficiency ratios, multi-hour returns and range in ATR, vol regime, session
    position, prior-day / day-so-far book R). No signal-bar micro features — isolates the
    "regime" question from the per-signal meta-labeling already tested (meta_midas.py).

Notes: 2026 only (user request). n is SMALL (≈130 traded days / 396 trades) — models are tiny and
fixed; no hyperparameter search. Oracle rows show the theoretical best a perfect gate could do.

Run: .venv/bin/python scratchpad/fx_gold/ml/gate_midas.py
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
import strategy as M                     # noqa: E402
from meta_midas import DATASET, book_stats, show   # noqa: E402

import lightgbm as lgb                   # noqa: E402
from sklearn.ensemble import RandomForestClassifier          # noqa: E402
from sklearn.impute import SimpleImputer                     # noqa: E402
from sklearn.linear_model import LogisticRegression          # noqa: E402
from sklearn.metrics import roc_auc_score                    # noqa: E402
from sklearn.pipeline import make_pipeline                   # noqa: E402
from sklearn.preprocessing import StandardScaler             # noqa: E402

RNG = np.random.default_rng(42)
DEC_MIN = M.MATURE_MIN   # decision offset into the fx-day = 120 min (first possible entry)


def make_models():
    return {
        "logit": make_pipeline(SimpleImputer(), StandardScaler(),
                               LogisticRegression(C=0.5, max_iter=2000)),
        "rf": make_pipeline(SimpleImputer(), RandomForestClassifier(
            n_estimators=300, max_depth=3, min_samples_leaf=10, random_state=42)),
        "lgbm": lgb.LGBMClassifier(objective="binary", n_estimators=200, learning_rate=0.05,
                                   num_leaves=5, min_child_samples=15, subsample=0.8,
                                   subsample_freq=1, colsample_bytree=0.8, reg_lambda=5.0,
                                   random_state=42, verbose=-1),
    }


def purged_oof_ensemble(X: pd.DataFrame, y: np.ndarray, times: np.ndarray,
                        n_folds=5, embargo=pd.Timedelta(days=2)):
    """Chronological purged CV; returns {model: oof} plus the ensemble mean."""
    bounds = np.linspace(0, len(X), n_folds + 1).astype(int)
    oofs = {name: np.full(len(X), np.nan) for name in make_models()}
    for f in range(n_folds):
        lo, hi = bounds[f], bounds[f + 1]
        t0, t1 = times[lo], times[hi - 1]
        tr = (times < t0 - embargo) | (times > t1 + embargo)
        for name, mdl in make_models().items():
            mdl.fit(X.loc[tr], y[tr])
            oofs[name][lo:hi] = mdl.predict_proba(X.iloc[lo:hi])[:, 1]
    oofs["ENSEMBLE"] = np.mean([oofs[k] for k in make_models()], axis=0)
    return oofs


# ---------------------------------------------------------------- data
def load_df():
    xa = pd.read_pickle(FXG / "xauusdt_1m_2026h1.pkl")
    xj = pd.read_pickle(FXG / "xau_jul2026.pkl")
    df = pd.concat([xa, xj])
    df = df[~df.index.duplicated()].sort_index()[["open", "high", "low", "close", "volume"]]
    df = M.add_market_open(df)
    df["fx_day"] = M._fx_day(df)
    return df


def _er(c: pd.Series, w: int) -> pd.Series:
    return (c - c.shift(w)).abs() / c.diff().abs().rolling(w).sum()


# ---------------------------------------------------------------- V1: fx-day gate
def day_dataset(df: pd.DataFrame, trades: pd.DataFrame):
    atr = M.atr_tf(df)
    vwap = M.anchored_vwap(df)
    trades = trades.copy()
    fx_of = pd.Series(df["fx_day"].to_numpy(), index=df.index)
    trades["fx_day"] = fx_of.loc[trades["signal_time"]].to_numpy()
    book = trades.groupby("fx_day").agg(day_r=("r", "sum"), day_taker=("r_taker", "sum"),
                                        n_tr=("r", "size"))
    rows = []
    hist: list[tuple] = []   # (fx_day, day_r) chronological, for prev-book features
    c_all = df["close"]
    for d, g in df.groupby("fx_day"):
        if len(g) <= DEC_MIN:      # day too short for the 2h window (holiday stub)
            continue
        w = g.iloc[:DEC_MIN]       # bars [0..119] — strictly before the first possible entry
        i_dec = df.index.get_loc(w.index[-1])
        a = atr.iloc[i_dec]
        if not np.isfinite(a) or a <= 0:
            continue
        prev_close = c_all.iloc[df.index.get_loc(g.index[0]) - 1] if df.index.get_loc(g.index[0]) > 0 else np.nan
        # previous fx-day price behavior
        pidx = df["fx_day"] < d
        pday = df.loc[pidx & (df["fx_day"] == df.loc[pidx, "fx_day"].max())] if pidx.any() else None
        if pday is not None and len(pday) > 60:
            pd_ret = (pday["close"].iloc[-1] - pday["open"].iloc[0]) / a
            pd_rng = (pday["high"].max() - pday["low"].min()) / a
            pd_er = abs(pday["close"].iloc[-1] - pday["open"].iloc[0]) / pday["close"].diff().abs().sum()
        else:
            pd_ret = pd_rng = pd_er = np.nan
        prev_rs = [r for _, r in hist]
        rows.append({
            "fx_day": d, "dec_time": w.index[-1],
            # first-2h window
            "w2_ret": (w["close"].iloc[-1] - w["open"].iloc[0]) / a,
            "w2_rng": (w["high"].max() - w["low"].min()) / a,
            "w2_er": abs(w["close"].iloc[-1] - w["open"].iloc[0]) / max(w["close"].diff().abs().sum(), 1e-9),
            "w2_vwap_dist": (w["close"].iloc[-1] - vwap.iloc[i_dec]) / a,
            "w2_slope": (vwap.iloc[i_dec] - vwap.iloc[max(i_dec - 60, 0)]) / a,
            "w2_volz": (w["volume"].iloc[-30:].mean() / max(w["volume"].mean(), 1e-9)),
            "gap": (w["open"].iloc[0] - prev_close) / a if np.isfinite(prev_close) else np.nan,
            "atr_ratio": a / atr.iloc[max(i_dec - 1440, 0):i_dec].mean(),
            # previous-day price + book
            "pd_ret": pd_ret, "pd_rng": pd_rng, "pd_er": pd_er,
            "prev_day_r": prev_rs[-1] if prev_rs else np.nan,
            "prev3_r": float(np.sum(prev_rs[-3:])) if prev_rs else np.nan,
            "dow": w.index[0].dayofweek,
        })
        if d in book.index:
            hist.append((d, float(book.loc[d, "day_r"])))
    days = pd.DataFrame(rows).set_index("fx_day")
    days = days.join(book, how="left")
    traded = days[days["n_tr"].notna()].copy()
    traded["y"] = (traded["day_r"] > 0).astype(int)
    return traded.reset_index()


V1_FEATS = ["w2_ret", "w2_rng", "w2_er", "w2_vwap_dist", "w2_slope", "w2_volz", "gap",
            "atr_ratio", "pd_ret", "pd_rng", "pd_er", "prev_day_r", "prev3_r", "dow"]


def eval_day_gate(days: pd.DataFrame, oofs: dict):
    y = days["y"].to_numpy()
    print(f"\n=== V1 fx-DAY GATE: {len(days)} traded days, positive-day rate {y.mean():.3f}")
    for name, p in oofs.items():
        print(f"  OOF AUC {name:9s} = {roc_auc_score(y, p):.3f}")
    p = oofs["ENSEMBLE"]
    rows = [dict(book_stats(days["day_r"].to_numpy(), "ALL days"),
                 takerR=round(days["day_taker"].sum(), 1), days=len(days))]
    oracle = days[days["day_r"] > 0]
    rows.append(dict(book_stats(oracle["day_r"].to_numpy(), "ORACLE (perfect gate)"),
                     takerR=round(oracle["day_taker"].sum(), 1), days=len(oracle)))
    for tau in (0.40, 0.45, 0.50, 0.55, 0.60):
        sel = days[p >= tau]
        rows.append(dict(book_stats(sel["day_r"].to_numpy(), f"gate p>={tau:.2f}"),
                         takerR=round(sel["day_taker"].sum(), 1), days=len(sel)))
    show(rows, "V1 day-gate economics (2026, day-R units)")
    # rank information
    q = pd.qcut(p, 4, labels=False, duplicates="drop")
    print("\n  day-R by ensemble-prob quartile:")
    print(days.groupby(q).agg(days=("day_r", "size"), tot_r=("day_r", "sum"),
                              avg_r=("day_r", "mean"), taker=("day_taker", "sum")).round(2).to_string())
    print(f"  corr(p, day_r) = {np.corrcoef(p, days['day_r'])[0, 1]:+.3f}")


# ---------------------------------------------------------------- V2: trade-time higher-TF gate
V2_FEATS = ["er2h", "er6h", "er24h", "ret2h", "ret6h", "ret24h", "rng24h", "atr_ratio",
            "mins_in", "utc_hour", "dow", "prev_day_r", "cum_r_today", "n_today"]


def trade_dataset(df: pd.DataFrame, trades: pd.DataFrame, day_book: pd.DataFrame):
    atr = M.atr_tf(df)
    a = atr.replace(0, np.nan)
    c = df["close"]
    f = pd.DataFrame(index=df.index)
    f["er2h"] = _er(c, 120); f["er6h"] = _er(c, 360); f["er24h"] = _er(c, 1440)
    f["ret2h"] = (c - c.shift(120)) / a
    f["ret6h"] = (c - c.shift(360)) / a
    f["ret24h"] = (c - c.shift(1440)) / a
    f["rng24h"] = (df["high"].rolling(1440).max() - df["low"].rolling(1440).min()) / a
    f["atr_ratio"] = a / a.rolling(1440, min_periods=300).mean()
    f["mins_in"] = df["fx_day"].groupby(df["fx_day"]).cumcount()
    f["utc_hour"] = df.index.hour
    f["dow"] = df.index.dayofweek
    idx = df.index.get_indexer(pd.DatetimeIndex(trades["signal_time"]))
    X = f.iloc[idx].reset_index(drop=True)
    # prior-day book R (leak-free: previous fx-day fully closed)
    fx_of = pd.Series(df["fx_day"].to_numpy(), index=df.index)
    tday = fx_of.loc[trades["signal_time"]].to_numpy()
    db = day_book.sort_index()
    prev_r = []
    for d in tday:
        past = db.loc[db.index < d, "day_r"]
        prev_r.append(past.iloc[-1] if len(past) else np.nan)
    X["prev_day_r"] = prev_r
    X["cum_r_today"] = trades["cum_r_today"].to_numpy()
    X["n_today"] = trades["n_today"].to_numpy()
    return X


def eval_trade_gate(trades: pd.DataFrame, oofs: dict):
    y = trades["y"].to_numpy()
    print(f"\n=== V2 TRADE-TIME higher-TF gate: {len(trades)} trades, WR {y.mean():.3f}")
    for name, p in oofs.items():
        print(f"  OOF AUC {name:9s} = {roc_auc_score(y, p):.3f}")
    p = oofs["ENSEMBLE"]
    al = (trades["had_prev"] == 1) & (trades["prev_r_day"] < 0)
    rows = [dict(book_stats(trades["r"].to_numpy(), "ALL"), takerR=round(trades["r_taker"].sum(), 1)),
            dict(book_stats(trades.loc[al, "r"].to_numpy(), "AFTER-LOSS (shipped)"),
                 takerR=round(trades.loc[al, "r_taker"].sum(), 1))]
    for tau in (0.40, 0.45, 0.50, 0.55, 0.60):
        m = p >= tau
        rows.append(dict(book_stats(trades.loc[m, "r"].to_numpy(), f"gate p>={tau:.2f}"),
                         takerR=round(trades.loc[m, "r_taker"].sum(), 1)))
    show(rows, "V2 trade-gate economics (2026)")


# ---------------------------------------------------------------- main
if __name__ == "__main__":
    df = load_df()
    ds = pd.read_pickle(DATASET)
    t26 = ds[ds["source"] == "xau26"].sort_values("entry_time").reset_index(drop=True)
    print(f"2026 book: {len(t26)} trades  totR={t26['r'].sum():+.1f}  takerR={t26['r_taker'].sum():+.1f}")

    # V1
    days = day_dataset(df, t26)
    oofs1 = purged_oof_ensemble(days[V1_FEATS], days["y"].to_numpy(),
                                days["dec_time"].to_numpy())
    eval_day_gate(days, oofs1)
    y_sh = RNG.permutation(days["y"].to_numpy())
    null1 = purged_oof_ensemble(days[V1_FEATS], y_sh, days["dec_time"].to_numpy())
    print(f"  NULL (shuffled labels) ensemble AUC = {roc_auc_score(y_sh, null1['ENSEMBLE']):.3f}")

    # V2
    day_book = t26.copy()
    fx_of = pd.Series(df["fx_day"].to_numpy(), index=df.index)
    day_book["fx_day"] = fx_of.loc[day_book["signal_time"]].to_numpy()
    db = day_book.groupby("fx_day").agg(day_r=("r", "sum"))
    X2 = trade_dataset(df, t26, db)
    oofs2 = purged_oof_ensemble(X2[V2_FEATS], t26["y"].to_numpy(),
                                t26["entry_time"].to_numpy(), embargo=pd.Timedelta(days=1))
    eval_trade_gate(t26, oofs2)
    y_sh2 = RNG.permutation(t26["y"].to_numpy())
    null2 = purged_oof_ensemble(X2[V2_FEATS], y_sh2, t26["entry_time"].to_numpy(),
                                embargo=pd.Timedelta(days=1))
    print(f"  NULL (shuffled labels) ensemble AUC = {roc_auc_score(y_sh2, null2['ENSEMBLE']):.3f}")
