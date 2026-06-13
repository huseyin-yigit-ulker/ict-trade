"""Market-regime gate for the CHOP-filtered strategy variants.

A signal is "choppy" when its symbol's 4h price action is going nowhere — measured
by Kaufman's Efficiency Ratio (ER) on the 4h timeframe (the engine's HTF):

    ER(n) = |close[i] - close[i-n]| / sum_{j} |close[j] - close[j-1]|
            (0 = pure chop / round-trip ; 1 = a clean one-way move)

2026 study (sync/out/_regime_analysis.py): MAIN signals fired in the choppiest
quartile (ER<0.25) were net-negative; gating them out lifted total R from +39 to
+55 (-33% of trades). So the CHOP variants keep only signals with ER >= ER_MIN.

ER is computed from 1h klines resampled to 4h. build_er() returns a per-symbol
series; chop_ok() looks up the value at-or-before a signal's bar. Missing data ->
allowed (never over-filter on absence).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

import trade_sync_common as tsc

ER_N = 10            # 4h bars (~1.7 days) lookback
ER_MIN = 0.25        # keep signals with ER >= this (drop the choppiest ~1/3)
# LIGHT band-pass — the 2026 regime-routing audit (sync/regime_route_analysis.py)
# found our (trend-following ICT) signals make ~85-90% of their R in the LIGHT
# regime (ER 0.20-0.35); strong/mid trend is break-even-to-negative. The LIGHT
# streams keep ONLY signals fired in this band. Matches REGIME_BANDS in
# src/utils/symbolMeta.js (light = [0.20, 0.35)).
LIGHT_LO = 0.20
LIGHT_HI = 0.35
_AGG = {"open": "first", "high": "max", "low": "min", "close": "last"}


def build_er(symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series | None:
    """Per-bar 4h Efficiency Ratio for `symbol` over [start, end] (None if no data)."""
    df1 = tsc.fetch_1h(symbol, start, end)
    if df1 is None or df1.empty:
        return None
    df4 = df1.resample("4h", label="right", closed="right").agg(_AGG).dropna()
    if len(df4) <= ER_N:
        return None
    c = df4["close"].values
    er = np.full(len(c), np.nan)
    for i in range(ER_N, len(c)):
        change = abs(c[i] - c[i - ER_N])
        vol = float(np.sum(np.abs(np.diff(c[i - ER_N:i + 1]))))
        er[i] = (change / vol) if vol > 0 else 0.0
    return pd.Series(er, index=df4.index)


def _er_at(er_series, ts):
    """ER value at the last 4h bar at/before ts, or None if unavailable."""
    if er_series is None or len(er_series) == 0:
        return None
    idx = er_series.index
    t = pd.Timestamp(ts)
    if t.tz is None:
        t = t.tz_localize("UTC")
    pos = int(idx.searchsorted(t, side="right")) - 1
    if pos < 0 or pos >= len(er_series):
        return None
    v = er_series.iloc[pos]
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return float(v)


def chop_ok(er_series: pd.Series | None, ts) -> bool:
    """True if the signal at `ts` is NOT choppy (ER >= ER_MIN). Missing -> True
    (never over-filter on absent data)."""
    v = _er_at(er_series, ts)
    return True if v is None else v >= ER_MIN


def is_choppy(er_series: pd.Series | None, ts) -> bool:
    """True only when ER is PRESENT and < ER_MIN — the confirmed-choppy complement
    of chop_ok (missing data -> False, so it isn't counted as choppy). Used by the
    diagnostic CHOP-ONLY stream."""
    v = _er_at(er_series, ts)
    return v is not None and v < ER_MIN


def light_ok(er_series: pd.Series | None, ts) -> bool:
    """LIGHT band-pass: True only when ER is PRESENT and in [LIGHT_LO, LIGHT_HI)
    (the light-trend regime where our signals earn their edge). Unlike chop_ok this
    is an INCLUSION gate — missing ER -> False (can't confirm light, so don't trade
    it). Used by the LIGHT stream variants."""
    v = _er_at(er_series, ts)
    return v is not None and LIGHT_LO <= v < LIGHT_HI
