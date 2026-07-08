"""Candidate B — STANDALONE ML signal generation on XAU (2026, 15m bars).

The literature's main model families race under ONE honest harness:

  TB-LGBM   LightGBM on a triple-barrier label (AFML standard): does a LONG entered at next-open
            hit +3.5*ATR before -1.5*ATR within 8h / session end? Shorts via feature mirroring.
  FH-LGBM   LightGBM on the classic fixed-horizon label (sign of next 2h return) — the typical
            "ML predicts gold direction" paper target, evaluated WITH costs for once.
  TB-LOGIT  linear baseline on the TB label (is any nonlinearity real?).
  TB-MLP    feature-input neural net on the TB label.
  SEQ-MLP   lag-return-sequence input (last 32 x 15m ATR-normalized returns) neural net — the
            practical small-data equivalent of the "LSTM gold prediction" paper family.
  ENSEMBLE  probability mean of TB-LGBM + TB-LOGIT + TB-MLP.

Protocol (2026-only, per user):
  * 1m XAUUSDT Jan..Jul-7 -> 15m bars; only fully-open bars are tradable; ATR15(14 EWM).
  * Labels respect the session: barrier race stops at a closed bar (MIDAS never holds overnight).
  * Monthly EXPANDING walk-forward: train on all months < m (min 2), 1-day purge gap, test month m
    -> OOS = Mar..Jul. No hyperparameter search; params fixed and small.
  * Signals: long if p(x) >= tau, short if p(mirror(x)) >= tau; tau = train-probability quantile
    (q90 / q97 — "selective classification": abstain unless confident).
  * Economics: audited engine.backtest, exits MATCH the label (SL 1.5*ATR / TP 3.5*ATR / 8h cap /
    session flat for TB; SL + 2h time-stop for FH). Costs $0.50/oz FX + 10bps-taker view.
  * NULL band: 20x random entries at the same signal count, same exits.

Run: .venv/bin/python scratchpad/fx_gold/ml/ml_signal_xau.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
FXG = HERE.parent
REPO = FXG.parents[1]
sys.path.insert(0, str(REPO / "sync" / "midas"))
sys.path.insert(0, str(HERE))
import strategy as M                    # noqa: E402
sys.path.insert(0, str(FXG))            # AFTER strategy import — it prepends backtest/ (own engine.py)
import engine as E                      # noqa: E402
assert "fx_gold" in E.__file__, f"wrong engine module: {E.__file__}"

import lightgbm as lgb                  # noqa: E402
from sklearn.impute import SimpleImputer                    # noqa: E402
from sklearn.linear_model import LogisticRegression         # noqa: E402
from sklearn.metrics import roc_auc_score                   # noqa: E402
from sklearn.neural_network import MLPClassifier            # noqa: E402
from sklearn.pipeline import make_pipeline                  # noqa: E402
from sklearn.preprocessing import StandardScaler            # noqa: E402

warnings.filterwarnings("ignore")
RNG = np.random.default_rng(42)

SL_K, TP_K, HOLD_BARS = 1.5, 3.5, 32          # TB geometry = MIDAS-like (1R stop, 8h cap)
FH_BARS = 8                                    # fixed-horizon: 2h
TAUS = (0.90, 0.97)                            # train-prob quantiles ("selective classification")
N_SEQ = 32                                     # lag-return window for SEQ-MLP

DIRECTIONAL = ["ret1", "ret4", "ret16", "ret96", "ema20_d", "ema96_d", "vwap_d", "vwap_slope",
               "body", "day_ret"]


# ---------------------------------------------------------------- data -> 15m frame
def build_15m() -> pd.DataFrame:
    xa = pd.read_pickle(FXG / "xauusdt_1m_2026h1.pkl")
    xj = pd.read_pickle(FXG / "xau_jul2026.pkl")
    df = pd.concat([xa, xj])
    df = df[~df.index.duplicated()].sort_index()[["open", "high", "low", "close", "volume"]]
    df = M.add_market_open(df)
    df["fx_day"] = M._fx_day(df)
    vwap1 = M.anchored_vwap(df)
    g = df.resample("15min", label="right", closed="right")
    d15 = g.agg({"open": "first", "high": "max", "low": "min", "close": "last",
                 "volume": "sum", "open_mkt": "mean", "fx_day": "last"}).dropna(subset=["close"])
    d15["open_mkt"] = d15["open_mkt"] >= 1.0                 # tradable = fully-open 15m bar
    d15["vwap"] = vwap1.resample("15min", label="right", closed="right").last()
    return d15


def add_features(d: pd.DataFrame) -> pd.DataFrame:
    c, o, h, lo = d["close"], d["open"], d["high"], d["low"]
    tr = pd.concat([(h - lo), (h - c.shift(1)).abs(), (lo - c.shift(1)).abs()], axis=1).max(axis=1)
    a = tr.ewm(alpha=1 / 14, adjust=False).mean().replace(0, np.nan)
    d["atr"] = a
    for w in (1, 4, 16, 96):
        d[f"ret{w}"] = (c - c.shift(w)) / a
    d["ema20_d"] = (c - c.ewm(span=20, adjust=False).mean()) / a
    d["ema96_d"] = (c - c.ewm(span=96, adjust=False).mean()) / a
    d["vwap_d"] = (c - d["vwap"]) / a
    d["vwap_slope"] = (d["vwap"] - d["vwap"].shift(4)) / a
    delta = c.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    d["rsi"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    d["atr_ratio"] = a / a.rolling(96, min_periods=30).mean()
    d["range_atr"] = (h - lo) / a
    d["body"] = (c - o) / a
    for w, nm in ((16, "er16"), (96, "er96")):
        d[nm] = (c - c.shift(w)).abs() / c.diff().abs().rolling(w).sum()
    v = d["volume"].replace(0, np.nan)
    d["vol_z"] = (v - v.rolling(96, min_periods=30).mean()) / v.rolling(96, min_periods=30).std()
    day = d["fx_day"]
    first = c.groupby(day).transform("first")
    d["day_ret"] = (c - first) / a
    dhi = h.groupby(day).cummax(); dlo = lo.groupby(day).cummin()
    d["pos_range"] = (c - dlo) / (dhi - dlo).replace(0, np.nan)
    d["mins_in"] = day.groupby(day).cumcount() * 15
    d["utc_hour"] = d.index.hour
    d["dow"] = d.index.dayofweek
    return d


FEATS = ["ret1", "ret4", "ret16", "ret96", "ema20_d", "ema96_d", "vwap_d", "vwap_slope", "rsi",
         "atr_ratio", "range_atr", "body", "er16", "er96", "vol_z", "day_ret", "pos_range",
         "mins_in", "utc_hour", "dow"]


def mirror(X: pd.DataFrame) -> pd.DataFrame:
    Xm = X.copy()
    for col in DIRECTIONAL:
        Xm[col] = -Xm[col]
    Xm["rsi"] = 100 - Xm["rsi"]
    Xm["pos_range"] = 1 - Xm["pos_range"]
    return Xm


# ---------------------------------------------------------------- labels (session-aware)
def tb_label(d: pd.DataFrame, s: int) -> np.ndarray:
    """1 = s-side TP (+TP_K*ATR favorable) before SL (-SL_K*ATR adverse) within HOLD_BARS, entered
    next open; 0 otherwise. Race stops at a closed bar (session flat). NOTE: the short race is NOT
    1-long (asymmetric barriers + timeouts) — it gets its own pass. Same-bar both-hit = SL."""
    o = d["open"].to_numpy(); h = d["high"].to_numpy(); lo = d["low"].to_numpy()
    a = d["atr"].to_numpy(); op = d["open_mkt"].to_numpy(bool); n = len(d)
    y = np.full(n, np.nan)
    for i in range(n - 1):
        if not op[i] or not op[i + 1] or not np.isfinite(a[i]) or a[i] <= 0:
            continue
        e = o[i + 1]; tp = e + s * TP_K * a[i]; sl = e - s * SL_K * a[i]
        y[i] = 0.0
        for j in range(i + 1, min(n, i + 1 + HOLD_BARS)):
            if not op[j]:
                break
            if (lo[j] <= sl) if s > 0 else (h[j] >= sl):
                break
            if (h[j] >= tp) if s > 0 else (lo[j] <= tp):
                y[i] = 1.0; break
    return y


def fh_label_long(d: pd.DataFrame) -> np.ndarray:
    """Classic fixed-horizon: next FH_BARS return sign (from next open), NaN if session breaks."""
    o = d["open"].to_numpy(); c = d["close"].to_numpy(); op = d["open_mkt"].to_numpy(bool)
    n = len(d); y = np.full(n, np.nan)
    for i in range(n - 1 - FH_BARS):
        if not op[i] or not all(op[i + 1:i + 1 + FH_BARS]):
            continue
        y[i] = float(c[i + FH_BARS] - o[i + 1] > 0)
    return y


# ---------------------------------------------------------------- models
def make_model(name: str):
    if name.endswith("LGBM"):
        return lgb.LGBMClassifier(objective="binary", n_estimators=300, learning_rate=0.03,
                                  num_leaves=15, min_child_samples=60, subsample=0.8,
                                  subsample_freq=1, colsample_bytree=0.7, reg_lambda=5.0,
                                  random_state=42, verbose=-1)
    if name == "TB-LOGIT":
        return make_pipeline(SimpleImputer(), StandardScaler(),
                             LogisticRegression(C=0.3, max_iter=2000))
    return make_pipeline(SimpleImputer(), StandardScaler(),
                         MLPClassifier(hidden_layer_sizes=(32, 16), alpha=1e-3, max_iter=400,
                                       early_stopping=True, random_state=42))


def seq_matrix(d: pd.DataFrame) -> pd.DataFrame:
    """Lag-return sequence input: last N_SEQ 15m returns in ATR units (the LSTM-paper diet)."""
    r = d["ret1"]
    cols = {f"lag{k}": r.shift(k) for k in range(N_SEQ)}
    return pd.DataFrame(cols, index=d.index)


# ---------------------------------------------------------------- walk-forward
def walk_forward(d: pd.DataFrame, X: pd.DataFrame, Xm: pd.DataFrame, yL: np.ndarray,
                 yS: np.ndarray, name: str):
    """Expanding monthly WF. One model learns BOTH worlds: rows = [X, yL] + [mirror(X), yS].
    Returns per-bar long/short OOS scores + per-month AUC list (on the long label)."""
    months = d.index.to_period("M")
    uniq = sorted(months.unique())
    pL = np.full(len(d), np.nan); pS = np.full(len(d), np.nan)
    aucs = []
    validL = ~np.isnan(yL); validS = ~np.isnan(yS)
    for k in range(2, len(uniq)):
        te = np.asarray(months == uniq[k])
        gap = np.asarray(d.index < (d.index[te][0] - pd.Timedelta(days=1)))
        base = np.asarray(months < uniq[k]) & gap
        trL = base & validL; trS = base & validS
        if trL.sum() < 500:
            continue
        Xtr = pd.concat([X.loc[trL], Xm.loc[trS]], ignore_index=True)
        ytr = np.concatenate([yL[trL], yS[trS]])
        mdl = make_model(name)
        mdl.fit(Xtr, ytr)
        pL[te] = mdl.predict_proba(X.loc[te])[:, 1]
        pS[te] = mdl.predict_proba(Xm.loc[te])[:, 1]
        m = te & validL
        if m.sum() > 30 and len(np.unique(yL[m])) > 1:
            aucs.append((str(uniq[k]), roc_auc_score(yL[m], pL[m])))
        # train-quantile thresholds, stored per test month
        ptr = mdl.predict_proba(Xtr)[:, 1]
        for tau_q in TAUS:
            d.loc[te, f"_tau{tau_q}_{name}"] = np.quantile(ptr, tau_q)
    return pL, pS, aucs


def economics(d: pd.DataFrame, pL, pS, name: str, exit_style: str):
    rows = []
    for tau_q in TAUS:
        tau = d[f"_tau{tau_q}_{name}"].to_numpy()
        side = np.zeros(len(d))
        side[(pL >= tau) & np.isfinite(pL)] = 1
        side[(pS >= tau) & np.isfinite(pS) & (side == 0)] = -1
        a = d["atr"].to_numpy(); c = d["close"].to_numpy()
        stop = np.where(side != 0, c - side * SL_K * a, np.nan)
        if exit_style == "tb":
            target = np.where(side != 0, c + side * TP_K * a, np.nan)
            cfg = E.Cfg(cost_rt=0.50, max_hold_min=HOLD_BARS)
        else:                                                  # fixed-horizon exit
            target = np.full(len(d), np.nan)
            cfg = E.Cfg(cost_rt=0.50, max_hold_min=FH_BARS)
        tr = E.backtest(d, side, stop, target, cfg)
        if len(tr):
            taker = ((tr["gross"] - 1e-3 * tr["entry"]) / tr["stop_dist"]).sum()
            st = E.stats(tr, cfg, f"{name} q{int(tau_q*100)}")
            nulls = null_band(d, int(len(tr)), exit_style)
            rows.append({**{k: st[k] for k in ("label", "n", "totR", "wr", "avgR", "pf", "maxddR")},
                         "takerR": round(float(taker), 1), "null": nulls})
        else:
            rows.append({"label": f"{name} q{int(tau_q*100)}", "n": 0, "totR": 0.0, "null": ""})
    return rows


def null_band(d: pd.DataFrame, n_sig: int, exit_style: str, reps: int = 20) -> str:
    """Random same-count entries, same exits -> mean±std totR (the no-skill band)."""
    ok = np.flatnonzero(d["open_mkt"].to_numpy(bool) & np.isfinite(d["atr"].to_numpy())
                        & (d.index.to_period("M") >= pd.Period("2026-03")))
    tots = []
    a = d["atr"].to_numpy(); c = d["close"].to_numpy()
    for _ in range(reps):
        side = np.zeros(len(d))
        pick = RNG.choice(ok, size=min(n_sig * 2, len(ok)), replace=False)  # extra: engine skips overlaps
        side[pick] = RNG.choice([1, -1], size=len(pick))
        stop = np.where(side != 0, c - side * SL_K * a, np.nan)
        if exit_style == "tb":
            target = np.where(side != 0, c + side * TP_K * a, np.nan)
            cfg = E.Cfg(cost_rt=0.50, max_hold_min=HOLD_BARS)
        else:
            target = np.full(len(d), np.nan)
            cfg = E.Cfg(cost_rt=0.50, max_hold_min=FH_BARS)
        tr = E.backtest(d, side, stop, target, cfg)
        if len(tr):
            tots.append(tr["r"].sum() * n_sig / len(tr))       # scale to same trade count
    return f"{np.mean(tots):+.0f}±{np.std(tots):.0f}R" if tots else ""


# ---------------------------------------------------------------- main
if __name__ == "__main__":
    d = add_features(build_15m())
    print(f"15m bars: {len(d)}  ({d.index[0]} .. {d.index[-1]})  tradable: {int(d['open_mkt'].sum())}")
    y_tbL = tb_label(d, +1); y_tbS = tb_label(d, -1)
    y_fhL = fh_label_long(d); y_fhS = 1 - y_fhL              # FH sign flip IS the mirror
    v = ~np.isnan(y_tbL)
    print(f"TB label: n={int(v.sum())}  base L={np.nanmean(y_tbL):.3f} S={np.nanmean(y_tbS):.3f}  "
          f"FH: n={int((~np.isnan(y_fhL)).sum())}  base={np.nanmean(y_fhL):.3f}")

    X = d[FEATS].copy()
    Xm = mirror(X)
    Xseq = seq_matrix(d)
    Xseq_m = -Xseq                                            # lag returns: mirror = sign flip
    all_rows, auc_summary, probs = [], {}, {}
    specs = [("TB-LGBM", X, Xm, y_tbL, y_tbS, "tb"), ("FH-LGBM", X, Xm, y_fhL, y_fhS, "fh"),
             ("TB-LOGIT", X, Xm, y_tbL, y_tbS, "tb"), ("TB-MLP", X, Xm, y_tbL, y_tbS, "tb"),
             ("SEQ-MLP", Xseq, Xseq_m, y_tbL, y_tbS, "tb")]
    for name, Xi, Xim, yiL, yiS, ex in specs:
        pL, pS, aucs = walk_forward(d, Xi, Xim, yiL, yiS, name)
        probs[name] = (pL, pS)
        auc_summary[name] = aucs
        all_rows += economics(d, pL, pS, name, ex)
        print(f"  {name}: done  OOS AUC by month: "
              + "  ".join(f"{m}:{a:.3f}" for m, a in aucs), flush=True)

    # ensemble of the three TB feature models
    ens = ["TB-LGBM", "TB-LOGIT", "TB-MLP"]
    pL = np.nanmean([probs[k][0] for k in ens], axis=0)
    pS = np.nanmean([probs[k][1] for k in ens], axis=0)
    for tau_q in TAUS:                          # ensemble tau = mean of member taus
        d[f"_tau{tau_q}_ENSEMBLE"] = np.nanmean([d[f"_tau{tau_q}_{k}"] for k in ens], axis=0)
    m = v & np.isfinite(pL)
    print(f"  ENSEMBLE pooled OOS AUC (TB label): {roc_auc_score(y_tbL[m], pL[m]):.3f}")
    all_rows += economics(d, pL, pS, "ENSEMBLE", "tb")

    print("\n================ OOS (Mar..Jul 2026) economics — engine-audited, $0.50 FX cost")
    print(pd.DataFrame(all_rows).to_string(index=False))
    print("\npooled OOS AUC:")
    for name, aucs in auc_summary.items():
        if aucs:
            print(f"  {name:9s} mean {np.mean([a for _, a in aucs]):.3f}   months: "
                  + "  ".join(f"{m.split('-')[1]}:{a:.2f}" for m, a in aucs))
    print("\nreference: MIDAS (rule-based) 2026 Mar-Jul ≈ +97R FX (full-year +143R, 396tr)")
