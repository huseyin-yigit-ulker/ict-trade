"""Signal-moment features for the MIDAS meta-labeling model.

Every feature is computable from data up to and INCLUDING the signal bar's CLOSE — the exact
information set signals() itself uses (decision at bar i close, fill at bar i+1 open). Nothing
here peeks at the fill bar or beyond. Directional features are side-adjusted (multiplied by the
signal side) so long and short pool into one model.

Feature groups:
  * VWAP geometry: side-adjusted distance to anchored VWAP, slope over 30/60/180 bars, pullback
    touch depth (how far past the TOUCH_TOL line the extreme reached).
  * Volatility regime: ATR as bps-of-price, 15m-ATR vs its own 1440-bar mean (vol expansion),
    signal-bar body and range in ATR.
  * Intraday context: minutes since the 18:00 ET anchor, UTC hour, day-of-week, intraday
    efficiency ratio, side-adjusted day return in ATR, position inside the day's range.
  * Volume: 300-bar z-score (PAXG spot and XAU futures volumes live on different scales; the
    z-score normalizes both).
NaNs are left in place — LightGBM handles them natively (early-session rolling windows).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def feature_frame(df: pd.DataFrame, atr: pd.Series, vwap: pd.Series,
                  slope_n: int = 60, touch_tol: float = 0.25) -> pd.DataFrame:
    """Per-bar feature columns (direction-NEUTRAL parts). Side-adjustment happens in
    `signal_features` once the signal side is known."""
    c = df["close"]; o = df["open"]; h = df["high"]; lo = df["low"]
    a = atr.replace(0, np.nan)

    f = pd.DataFrame(index=df.index)
    f["dist_vwap"] = (c - vwap) / a                       # signed; side-adjusted later
    f["slope30"] = (vwap - vwap.shift(30)) / a
    f["slope60"] = (vwap - vwap.shift(slope_n)) / a
    f["slope180"] = (vwap - vwap.shift(180)) / a
    f["body"] = (c - o) / a                               # signed; side-adjusted later
    f["range_atr"] = (h - lo) / a
    f["atr_bps"] = a / c * 1e4
    f["atr_ratio"] = a / a.rolling(1440, min_periods=300).mean()

    # pullback depth past the touch-tolerance line, per prospective side
    f["_touch_long"] = (vwap + touch_tol * a - lo) / a    # >0 = low pierced the touch line
    f["_touch_short"] = (h - (vwap - touch_tol * a)) / a

    # intraday context (fx-day groups are supplied by the caller as a column)
    day = df["fx_day"]
    g = c.groupby(day)
    day_first = g.transform("first")
    day_hi = h.groupby(day).cummax()
    day_lo = lo.groupby(day).cummin()
    f["day_ret"] = (c - day_first) / a                    # signed; side-adjusted later
    rng = (day_hi - day_lo).replace(0, np.nan)
    f["pos_in_range"] = (c - day_lo) / rng
    move = (c - day_first).abs()
    path = c.diff().abs().groupby(day).cumsum()
    f["day_er"] = move / path.replace(0, np.nan)          # intraday efficiency ratio
    f["mins_in"] = day.groupby(day).cumcount()
    f["utc_hour"] = df.index.hour
    f["dow"] = df.index.dayofweek

    v = df["volume"].replace(0, np.nan)
    f["vol_z"] = (v - v.rolling(300, min_periods=60).mean()) / v.rolling(300, min_periods=60).std()
    return f


def signal_features(feat: pd.DataFrame, idx: np.ndarray, sides: np.ndarray) -> pd.DataFrame:
    """Select signal-bar rows and side-adjust the directional columns."""
    X = feat.iloc[idx].copy()
    s = np.asarray(sides, float)
    for col in ("dist_vwap", "slope30", "slope60", "slope180", "body", "day_ret"):
        X[col] = X[col].to_numpy() * s
    X["touch_depth"] = np.where(s > 0, X["_touch_long"].to_numpy(), X["_touch_short"].to_numpy())
    X["pos_in_range"] = np.where(s > 0, X["pos_in_range"].to_numpy(), 1.0 - X["pos_in_range"].to_numpy())
    X = X.drop(columns=["_touch_long", "_touch_short"])
    X["side"] = s
    return X.reset_index(drop=True)
