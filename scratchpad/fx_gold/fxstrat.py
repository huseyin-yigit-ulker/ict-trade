"""Candidate intraday XAUUSD strategies. Each returns (side, stop, target) arrays aligned to df,
decided as of bar i's CLOSE (engine fills at i+1 open). Absolute price levels for stop/target.

All indicators use only past/closed-bar data. ATR/VWAP anchored per FX-day (18:00 ET reset).
"""
from __future__ import annotations
import numpy as np
import pandas as pd


# ---------- helpers ----------
def atr_tf(df: pd.DataFrame, tf: str = "15min", n: int = 14) -> pd.Series:
    """ATR computed on a higher timeframe, forward-filled to 1m (no lookahead)."""
    g = df.resample(tf, label="right", closed="right").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    pc = g["close"].shift(1)
    tr = pd.concat([(g["high"] - g["low"]), (g["high"] - pc).abs(), (g["low"] - pc).abs()], axis=1).max(axis=1)
    a = tr.ewm(alpha=1 / n, adjust=False).mean()
    return a.reindex(df.index, method="ffill")


def fx_day(df: pd.DataFrame) -> np.ndarray:
    """Integer FX-day id: increments at the 18:00 ET session open (the gold/FX day boundary)."""
    et = df.index.tz_convert("America/New_York")
    # shift so that 18:00 ET is the day boundary
    shifted = et - pd.Timedelta(hours=18)
    return shifted.normalize().view("int64")


def anchored_vwap(df: pd.DataFrame):
    """Per-FX-day anchored VWAP and rolling std of (typical-vwap). No lookahead (cumulative)."""
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    vol = df["volume"].replace(0, np.nan).fillna(method="ffill").fillna(1.0)
    day = pd.Series(fx_day(df), index=df.index)
    pv = (tp * vol).groupby(day).cumsum()
    cv = vol.groupby(day).cumsum()
    vwap = pv / cv
    dev = tp - vwap
    # cumulative std of deviation within the day
    var = (dev.pow(2)).groupby(day).cumsum() / cv.groupby(day).cumcount().add(1)
    sd = np.sqrt(var.clip(lower=0))
    return vwap, sd


def _et_minofday(df):
    et = df.index.tz_convert("America/New_York")
    return (et.hour * 60 + et.minute).to_numpy()


# ---------- 1. Opening Range Breakout ----------
def orb(df, session_start=(8, 0), or_min=30, entry_window=240, rr=2.0,
        stop_mode="range", atr_mult=1.0, atr=None):
    """Break of the first `or_min` minutes after a session open. session_start in ET (h,m).
    stop_mode='range' -> stop at opposite OR extreme; 'atr' -> entry -/+ atr_mult*ATR."""
    n = len(df); side = np.zeros(n); stop = np.full(n, np.nan); target = np.full(n, np.nan)
    H = df["high"].to_numpy(); L = df["low"].to_numpy(); C = df["close"].to_numpy()
    openmkt = df["open_mkt"].to_numpy(bool)
    mod = _et_minofday(df)
    if atr is None and stop_mode == "atr":
        atr = atr_tf(df, "15min", 14).to_numpy()
    s0 = session_start[0] * 60 + session_start[1]
    or_end = s0 + or_min; ent_end = s0 + entry_window
    day = fx_day(df)
    for d in np.unique(day):
        dm = (day == d) & openmkt
        idx = np.where(dm)[0]
        if idx.size == 0:
            continue
        m = mod[idx]
        orbars = idx[(m >= s0) & (m < or_end)]
        if orbars.size < 2:
            continue
        orH = H[orbars].max(); orL = L[orbars].min()
        post = idx[(m >= or_end) & (m < ent_end)]
        for p in post:
            if C[p] > orH:
                es = orL if stop_mode == "range" else C[p] - atr_mult * atr[p]
                risk = C[p] - es
                if risk <= 0:
                    continue
                side[p] = 1; stop[p] = es; target[p] = C[p] + rr * risk; break
            if C[p] < orL:
                es = orH if stop_mode == "range" else C[p] + atr_mult * atr[p]
                risk = es - C[p]
                if risk <= 0:
                    continue
                side[p] = -1; stop[p] = es; target[p] = C[p] - rr * risk; break
    return side, stop, target


# ---------- 2. VWAP trend pullback ----------
def vwap_trend(df, rr=2.0, slope_n=30, atr_mult=1.5, touch_tol=0.25, atr=None):
    """Uptrend (close>VWAP, VWAP rising): buy the reclaim after a pullback that touches VWAP.
    Stop = atr_mult*ATR below entry; target = rr*risk."""
    n = len(df); side = np.zeros(n); stop = np.full(n, np.nan); target = np.full(n, np.nan)
    vwap, sd = anchored_vwap(df)
    if atr is None:
        atr = atr_tf(df, "15min", 14)
    C = df["close"]; O = df["open"]; L = df["low"]; Hg = df["high"]
    vw = vwap.to_numpy(); slope = (vwap - vwap.shift(slope_n)).to_numpy()
    c = C.to_numpy(); o = O.to_numpy(); lo = L.to_numpy(); hi = Hg.to_numpy(); a = atr.to_numpy()
    tol = touch_tol * a
    openmkt = df["open_mkt"].to_numpy(bool)
    for i in range(2, n):
        if not openmkt[i] or not np.isfinite(vw[i]) or not np.isfinite(a[i]) or a[i] <= 0:
            continue
        # long: uptrend + this bar dipped to vwap then closed back above, bullish
        if c[i] > vw[i] and slope[i] > 0 and lo[i] <= vw[i] + tol[i] and c[i] > o[i]:
            es = c[i] - atr_mult * a[i]; risk = c[i] - es
            side[i] = 1; stop[i] = es; target[i] = c[i] + rr * risk
        elif c[i] < vw[i] and slope[i] < 0 and hi[i] >= vw[i] - tol[i] and c[i] < o[i]:
            es = c[i] + atr_mult * a[i]; risk = es - c[i]
            side[i] = -1; stop[i] = es; target[i] = c[i] - rr * risk
    return side, stop, target


# ---------- 3. VWAP fade (mean reversion) ----------
def vwap_fade(df, k=2.0, atr_mult=1.0, atr=None):
    """Fade extensions: short when close > VWAP + k*sd, target VWAP. Long symmetric."""
    n = len(df); side = np.zeros(n); stop = np.full(n, np.nan); target = np.full(n, np.nan)
    vwap, sd = anchored_vwap(df)
    if atr is None:
        atr = atr_tf(df, "15min", 14)
    c = df["close"].to_numpy(); vw = vwap.to_numpy(); s = sd.to_numpy(); a = atr.to_numpy()
    openmkt = df["open_mkt"].to_numpy(bool)
    for i in range(n):
        if not openmkt[i] or not np.isfinite(vw[i]) or not np.isfinite(s[i]) or s[i] <= 0:
            continue
        if c[i] > vw[i] + k * s[i]:
            side[i] = -1; stop[i] = c[i] + atr_mult * a[i]; target[i] = vw[i]
        elif c[i] < vw[i] - k * s[i]:
            side[i] = 1; stop[i] = c[i] - atr_mult * a[i]; target[i] = vw[i]
    return side, stop, target


# ---------- 4. Bollinger fade (Asian-session mean reversion) ----------
def bb_fade(df, win=20, k=2.0, atr_mult=1.0, sess_et=(18, 2), atr=None):
    """Fade Bollinger-band extremes during the quiet Asian session (default 18:00-02:00 ET).
    Short if close>upper, target mid. tf=5min bands ffilled to 1m."""
    n = len(df); side = np.zeros(n); stop = np.full(n, np.nan); target = np.full(n, np.nan)
    g = df["close"].resample("5min", label="right", closed="right").last().dropna()
    mid = g.rolling(win).mean(); std = g.rolling(win).std()
    up = (mid + k * std).reindex(df.index, method="ffill").to_numpy()
    dn = (mid - k * std).reindex(df.index, method="ffill").to_numpy()
    md = mid.reindex(df.index, method="ffill").to_numpy()
    if atr is None:
        atr = atr_tf(df, "15min", 14)
    a = atr.to_numpy(); c = df["close"].to_numpy()
    mod = _et_minofday(df); openmkt = df["open_mkt"].to_numpy(bool)
    h0 = sess_et[0] * 60; h1 = sess_et[1] * 60
    insess = (mod >= h0) | (mod < h1)  # wraps past midnight
    for i in range(n):
        if not openmkt[i] or not insess[i] or not np.isfinite(up[i]) or not np.isfinite(md[i]):
            continue
        if c[i] > up[i]:
            side[i] = -1; stop[i] = c[i] + atr_mult * a[i]; target[i] = md[i]
        elif c[i] < dn[i]:
            side[i] = 1; stop[i] = c[i] - atr_mult * a[i]; target[i] = md[i]
    return side, stop, target


# ---------- 5. Momentum breakout (Donchian-FREE: N-bar high/low + EMA filter) ----------
def mom_break(df, lookback=60, ema_n=200, rr=2.0, atr_mult=1.5, atr=None):
    """Intraday momentum: break of prior `lookback`-min high with price above EMA(ema_n).
    Distinct from the repo's 30m/4h Donchian — pure 1m intraday, EMA-trend gated, ATR stop."""
    n = len(df); side = np.zeros(n); stop = np.full(n, np.nan); target = np.full(n, np.nan)
    H = df["high"]; L = df["low"]; C = df["close"]
    hh = H.shift(1).rolling(lookback).max().to_numpy()
    ll = L.shift(1).rolling(lookback).min().to_numpy()
    ema = C.ewm(span=ema_n, adjust=False).mean().to_numpy()
    if atr is None:
        atr = atr_tf(df, "15min", 14)
    a = atr.to_numpy(); c = C.to_numpy()
    openmkt = df["open_mkt"].to_numpy(bool)
    for i in range(n):
        if not openmkt[i] or not np.isfinite(hh[i]) or not np.isfinite(a[i]) or a[i] <= 0:
            continue
        if c[i] > hh[i] and c[i] > ema[i]:
            es = c[i] - atr_mult * a[i]; side[i] = 1; stop[i] = es; target[i] = c[i] + rr * (c[i] - es)
        elif c[i] < ll[i] and c[i] < ema[i]:
            es = c[i] + atr_mult * a[i]; side[i] = -1; stop[i] = es; target[i] = c[i] - rr * (es - c[i])
    return side, stop, target
