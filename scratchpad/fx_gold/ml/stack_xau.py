"""STACKING blender — every XAU strategy we have (repo + literature families) as FEATURES under
one ML model, plus genuinely NEW features (cross-asset silver/BTC/SPY lead-lag).

Question (user): combine all XAU strategies, blend their signals with an ML model, add new
features on top — does the blend beat the market-features-only TB-LGBM (+27.8R OOS, §4c)?

Feature sets raced under the IDENTICAL harness of ml_signal_xau.py (15m bars, triple-barrier
label, monthly expanding walk-forward Mar-Jul OOS, train-quantile thresholds, engine economics):

  BASE   the 20 market features of §4c (reference re-run)
  STRAT  strategy signals ONLY: 12 rule families' 1m signals aggregated to 15m (net fire count)
         + 4 state features (supertrend dir, PSAR dir, Donchian position, Keltner-band z)
         Families: shipped MIDAS, TALOS Keltner-band 0.75 (shipped cfg), Keltner-mid, EMA200 pull,
         KAMA pull, Supertrend flip+pull, Donchian-120 break, prev-day H/L break, Asian-range
         break, PSAR flip, session TSMOM (all from scratchpad/fx_gold/strategies2.py, scan-era cfg).
  B+S    BASE + STRAT (the stack)
  ALL    B+S + cross-asset NEW features: silver ret4/16/96 (XAG-ATR units), gold/silver-ratio z,
         BTC ret16, SPY ret16 (pickles end Jun-30 -> July NaN, LightGBM handles).

Run: .venv/bin/python scratchpad/fx_gold/ml/stack_xau.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
FXG = HERE.parent
sys.path.insert(0, str(HERE))
import ml_signal_xau as S                    # noqa: E402  (fixes strategy/engine import order)
from ml_signal_xau import (build_15m, add_features, tb_label, mirror, walk_forward,  # noqa: E402
                           economics, FEATS, M)
from sklearn.metrics import roc_auc_score    # noqa: E402

sys.path.insert(0, str(FXG))
import strategies2 as S2                     # noqa: E402

S.TAUS = (0.95, 0.97)                        # selective thresholds (q90 was net-negative in §4c)

STRAT_SIG = ["s_midas", "s_kelt075", "s_keltmid", "s_ema200", "s_kama", "s_stflip", "s_stpull",
             "s_donch", "s_pdhl", "s_asian", "s_psar", "s_tsm"]
STRAT_STATE = ["st_dir", "psar_d", "donch_pos", "kelt_z"]
CROSS = ["xag_r4", "xag_r16", "xag_r96", "gs_z", "btc_r16", "spy_r16"]


def load_1m() -> pd.DataFrame:
    xa = pd.read_pickle(FXG / "xauusdt_1m_2026h1.pkl")
    xj = pd.read_pickle(FXG / "xau_jul2026.pkl")
    df = pd.concat([xa, xj])
    df = df[~df.index.duplicated()].sort_index()[["open", "high", "low", "close", "volume"]]
    df = M.add_market_open(df)
    df["fx_day"] = M._fx_day(df)
    return df


def strategy_signals_1m(df: pd.DataFrame) -> pd.DataFrame:
    atr1 = M.atr_tf(df)
    a = atr1
    out = pd.DataFrame(index=df.index)
    side, _ = M.signals(df, atr1)                                    # shipped MIDAS (all filters)
    out["s_midas"] = side
    gens = {
        "s_kelt075": lambda: S2.keltner_pull(df, "15min", kmult=0.75, slope_n=4, touch_tol=0.25,
                                             entry="band", atr=a),   # TALOS shipped cfg
        "s_keltmid": lambda: S2.keltner_pull(df, "15min", entry="mid", atr=a),
        "s_ema200": lambda: S2.ema_pull(df, ema_n=200, atr=a),
        "s_kama": lambda: S2.kama_pull(df, atr=a),
        "s_stflip": lambda: S2.st_flip(df, atr=a),
        "s_stpull": lambda: S2.st_pull(df, atr=a),
        "s_donch": lambda: S2.donch_break(df, lookback=120, atr=a),
        "s_pdhl": lambda: S2.pdhl_break(df, atr=a),
        "s_asian": lambda: S2.asian_break(df, atr=a),
        "s_psar": lambda: S2.psar_flip(df, atr=a),
        "s_tsm": lambda: S2.tsm_session(df, atr=a),
    }
    for name, fn in gens.items():
        out[name] = fn()[0]
        print(f"    {name}: {int((out[name] != 0).sum())} signals", flush=True)
    return out


def add_strat_features(d: pd.DataFrame, sig1m: pd.DataFrame) -> pd.DataFrame:
    g = sig1m.resample("15min", label="right", closed="right").sum()
    for col in STRAT_SIG:
        d[col] = g[col].reindex(d.index)
    # state features on the 15m frame itself
    g15 = d[["open", "high", "low", "close"]]
    d["st_dir"] = S2.supertrend_dir(g15, 10, 3.0).to_numpy()
    d["psar_d"] = S2.psar_dir(g15).to_numpy()
    hi96 = d["high"].rolling(96).max(); lo96 = d["low"].rolling(96).min()
    d["donch_pos"] = (d["close"] - lo96) / (hi96 - lo96).replace(0, np.nan)
    ema20 = d["close"].ewm(span=20, adjust=False).mean()
    d["kelt_z"] = (d["close"] - ema20) / (0.75 * d["atr"].replace(0, np.nan))
    return d


def add_cross_features(d: pd.DataFrame) -> pd.DataFrame:
    def close15(path):
        x = pd.read_pickle(path)[["close", "high", "low"]]
        return x.resample("15min", label="right", closed="right").agg(
            {"close": "last", "high": "max", "low": "min"}).reindex(d.index)
    xag = close15(FXG / "_1m_XAGUSDT.pkl")
    tr = pd.concat([(xag["high"] - xag["low"]),
                    (xag["high"] - xag["close"].shift(1)).abs(),
                    (xag["low"] - xag["close"].shift(1)).abs()], axis=1).max(axis=1)
    xa_atr = tr.ewm(alpha=1 / 14, adjust=False).mean().replace(0, np.nan)
    for w, nm in ((4, "xag_r4"), (16, "xag_r16"), (96, "xag_r96")):
        d[nm] = (xag["close"] - xag["close"].shift(w)) / xa_atr
    ratio = d["close"] / xag["close"]
    d["gs_z"] = (ratio - ratio.rolling(96, min_periods=30).mean()) / ratio.rolling(96, min_periods=30).std()
    for sym, nm in (("_1m_BTCUSDT.pkl", "btc_r16"), ("_1m_SPYUSDT.pkl", "spy_r16")):
        x = close15(FXG / sym)["close"]
        d[nm] = (x - x.shift(16)) / x.shift(16) * 100
    return d


def mirror_stack(X: pd.DataFrame) -> pd.DataFrame:
    base_cols = [c for c in X.columns if c in FEATS]
    Xm = X.copy()
    if base_cols:
        Xm[base_cols] = mirror(X[base_cols].copy())[base_cols]
    for col in STRAT_SIG + ["st_dir", "psar_d", "kelt_z"] + CROSS:
        if col in Xm:
            Xm[col] = -Xm[col]
    if "donch_pos" in Xm:
        Xm["donch_pos"] = 1 - Xm["donch_pos"]
    return Xm


if __name__ == "__main__":
    df1 = load_1m()
    print("computing strategy signals on 1m ...", flush=True)
    sig1m = strategy_signals_1m(df1)
    d = add_features(build_15m())
    d = add_strat_features(d, sig1m)
    d = add_cross_features(d)
    yL = tb_label(d, +1); yS = tb_label(d, -1)
    v = ~np.isnan(yL)

    sets = {"BASE-LGBM": FEATS,
            "STRAT-LGBM": STRAT_SIG + STRAT_STATE,
            "B+S-LGBM": FEATS + STRAT_SIG + STRAT_STATE,
            "ALL-LGBM": FEATS + STRAT_SIG + STRAT_STATE + CROSS}
    all_rows, aucs_all, probs = [], {}, {}
    for name, cols in sets.items():
        X = d[cols].copy()
        Xm = mirror_stack(X)
        pL, pS, aucs = walk_forward(d, X, Xm, yL, yS, name)
        probs[name] = (pL, pS)
        m = v & np.isfinite(pL)
        pooled = roc_auc_score(yL[m], pL[m])
        aucs_all[name] = (pooled, aucs)
        all_rows += economics(d, pL, pS, name, "tb")
        print(f"  {name}: pooled OOS AUC {pooled:.3f}   months: "
              + "  ".join(f"{mn.split('-')[1]}:{a:.2f}" for mn, a in aucs), flush=True)

    print("\n================ OOS (Mar..Jul 2026) economics — engine-audited, $0.50 FX")
    print(pd.DataFrame(all_rows).to_string(index=False))

    # importance of the full blend (final fit, all data)
    import lightgbm as lgb
    cols = sets["ALL-LGBM"]
    X = d[cols]; Xm = mirror_stack(X.copy())
    vS = ~np.isnan(yS)
    Xtr = pd.concat([X.loc[v], Xm.loc[vS]], ignore_index=True)
    ytr = np.concatenate([yL[v], yS[vS]])
    mdl = S.make_model("ALL-LGBM"); mdl.fit(Xtr, ytr)
    gain = pd.Series(mdl.booster_.feature_importance("gain"), index=cols)
    print("\ntop-15 features (gain, full blend):")
    print((gain / gain.sum()).sort_values(ascending=False).head(15).round(3).to_string())
    grp = {"market": [c for c in cols if c in FEATS], "strat": STRAT_SIG + STRAT_STATE, "cross": CROSS}
    tot = gain.sum()
    print("\ngain share by group: " + "  ".join(f"{k}:{gain[vv].sum()/tot:.2f}" for k, vv in grp.items()))
