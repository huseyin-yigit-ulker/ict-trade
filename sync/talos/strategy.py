"""TALOS — gold-only intraday KELTNER-trend strategy (XAUUSDT 1m). Public codename: ANTARES.

The 3rd live stream (2026-07-07), researched in the "MIDAS'tan iyi XAU" scan (MIDAS.md changelog
2026-07-07): 30+ entry families were tested on the MIDAS skeleton; the ONE robust non-VWAP entry is
a DEEP pullback to the 15m Keltner band. TALOS = that candidate (KELT075), productized.

Entry: on the 15m chart, EMA(20) defines the trend (4-bar slope); the Keltner band is EMA ± 0.75 x
ATR(20, 15m). LONG when the trend is up and a 1m bar dips to/below the LOWER band (within
0.25 x ATR15 tolerance) then closes back bullish above it — a deeper discount than MIDAS's VWAP
touch. SHORT symmetric on the upper band. Decided on bar CLOSE, filled next-bar OPEN (no lookahead).

Exit/skeleton: IDENTICAL to MIDAS and reused from it verbatim (import) — 1.5 x ATR(15m) initial stop
(1R), NO fixed target, 3.5 x ATR chandelier trailing stop, 8h time-stop, session-close flat, real
FX-gold market hours + US-holiday calendar + Fri-16:00-ET weekend buffer, London 07-13 UTC skipped,
first-120min session-maturity filter, one position at a time, $0.50/oz round-trip cost.

Validated (see MIDAS.md 2026-07-07 entry): XAU 2026-H1 +87.5R / 314 trades / PF 1.54 / maxDD -8.3R
(IS +55.9 / OOS +31.6); parameter plateau flat (kmult .625-.875 x trail 3.5-4.0); random-entry null
P=0.000. Multi-year PAXG proxy OOS: 2024 -168.8 / 2025 +114.5 (PF 1.33) / 2026 +93.5 (PF 1.55) =
3yr +39.2R vs MIDAS-repro -183.0R — the reason TALOS ships: it is the regime-robust sibling.
Volume-free by construction (EMA/ATR only), so it transfers to volume-less gold feeds.

COST NOTE: like MIDAS this is an FX-cost model ($0.50/oz rt). PAPER stream only — no executor.
"""
from __future__ import annotations
import sys
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))                 # sync/ -> trade_sync_common

# Reuse the MIDAS engine verbatim (session mask, data, ATR, walk/trailing, live tracker).
# Loaded under a unique module name — both files are called strategy.py.
_spec = importlib.util.spec_from_file_location("midas_strategy", _HERE.parents[1] / "midas" / "strategy.py")
MS = importlib.util.module_from_spec(_spec)
sys.modules["midas_strategy"] = MS                        # dataclass needs the module registered
_spec.loader.exec_module(MS)

SYMBOL = MS.SYMBOL                    # XAUUSDT

# ---- tuned config (plateau-confirmed; see MIDAS.md 2026-07-07 scan entry) ----
EMA_TF = "15min"      # Keltner timeframe
EMA_N = 20            # Keltner midline EMA + band-ATR period
KMULT = 0.75          # band width in ATR(20, 15m)
SLOPE_TF_BARS = 4     # trend = EMA20 slope over 4 x 15m bars (1h)
ATR_TF = MS.ATR_TF    # 15min — stop/trail ATR (14), same as MIDAS
ATR_N = MS.ATR_N
ATR_INIT_MULT = 1.5   # initial stop distance (1R)
TRAIL_MULT = 3.5      # ATR chandelier trailing multiple
TOUCH_TOL = 0.25      # band-touch tolerance in ATR15
MAX_HOLD_MIN = 480    # 8h time-stop
COST_RT = 0.50        # $/oz round-trip (ECN-FX)
TP_REF_MULT = TRAIL_MULT / ATR_INIT_MULT   # nominal "target" line for the UI only
SKIP_UTC_START = MS.SKIP_UTC_START         # 7  — London pre-NY window skipped (same as MIDAS)
SKIP_UTC_END = MS.SKIP_UTC_END             # 13
MATURE_MIN = MS.MATURE_MIN                 # 120 — no entries in the fresh fx-session

# Shared engine surface (identical semantics to MIDAS)
load_1m = MS.load_1m
add_market_open = MS.add_market_open
atr_tf = MS.atr_tf
Trade = MS.Trade
walk = MS.walk                        # trail/max_hold passed explicitly below
_net_r = MS._net_r


def keltner(df: pd.DataFrame):
    """15m EMA(20) midline, ATR(20, 15m) band width and 4-bar slope, ffilled to 1m (no lookahead:
    label='right', closed='right' — a 15m value exists only once its bucket has fully closed)."""
    g = df.resample(EMA_TF, label="right", closed="right").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    ema = g["close"].ewm(span=EMA_N, adjust=False).mean()
    pc = g["close"].shift(1)
    tr = pd.concat([(g["high"] - g["low"]), (g["high"] - pc).abs(), (g["low"] - pc).abs()],
                   axis=1).max(axis=1)
    katr = tr.ewm(alpha=1 / EMA_N, adjust=False).mean()
    slope = ema - ema.shift(SLOPE_TF_BARS)
    ema1 = ema.reindex(df.index, method="ffill")
    katr1 = katr.reindex(df.index, method="ffill")
    slope1 = slope.reindex(df.index, method="ffill")
    return ema1, katr1, slope1


def signals(df: pd.DataFrame, atr: pd.Series | None = None):
    """(side, stop) arrays. side +1/-1/0 decided at bar i close; stop = initial-stop price.
    LONG: 15m-EMA20 slope up + bar dips to the LOWER Keltner band (low <= band_lo + 0.25*ATR15)
    + closes back above the band, bullish (c>o). SHORT symmetric on the upper band."""
    if atr is None:
        atr = atr_tf(df)
    ema1, katr1, slope1 = keltner(df)
    n = len(df); side = np.zeros(n); stop = np.full(n, np.nan)
    m = ema1.to_numpy(); ka = katr1.to_numpy(); sl = slope1.to_numpy()
    c = df["close"].to_numpy(); o = df["open"].to_numpy()
    lo = df["low"].to_numpy(); hi = df["high"].to_numpy()
    a = atr.to_numpy(); openmkt = df["open_mkt"].to_numpy(bool)
    uth = df.index.hour.to_numpy()
    day = pd.Series(MS._fx_day(df))
    bars_in = day.groupby(day).cumcount().to_numpy()
    band_lo = m - KMULT * ka; band_hi = m + KMULT * ka
    tol = TOUCH_TOL * a
    for i in range(n):
        if not openmkt[i] or not np.isfinite(m[i]) or not np.isfinite(sl[i]) \
           or not np.isfinite(a[i]) or a[i] <= 0:
            continue
        if SKIP_UTC_START <= uth[i] < SKIP_UTC_END:   # London pre-NY chop window
            continue
        if bars_in[i] < MATURE_MIN:                    # fresh fx-session
            continue
        if sl[i] > 0 and c[i] > band_lo[i] and lo[i] <= band_lo[i] + tol[i] and c[i] > o[i]:
            side[i] = 1; stop[i] = c[i] - ATR_INIT_MULT * a[i]
        elif sl[i] < 0 and c[i] < band_hi[i] and hi[i] >= band_hi[i] - tol[i] and c[i] < o[i]:
            side[i] = -1; stop[i] = c[i] + ATR_INIT_MULT * a[i]
    return side, stop


def generate_trades(start: pd.Timestamp, end: pd.Timestamp, *, cost=COST_RT) -> list:
    """End-to-end: fetch 1m, tag market hours, TALOS signals, MIDAS walk -> closed trades."""
    df = load_1m(start - pd.Timedelta(days=2), end)
    if df.empty:
        return []
    df = add_market_open(df)
    atr = atr_tf(df)
    side, stop = signals(df, atr)
    trades = walk(df, side, stop, atr.to_numpy(), cost=cost, trail=TRAIL_MULT, max_hold=MAX_HOLD_MIN)
    return [t for t in trades if t.entry_time >= start]


def track_open(entry_fill: pd.Timestamp, side: int, entry: float, init_sl: float, now: pd.Timestamp):
    """LIVE trailing replay of one open position — MIDAS's tracker with TALOS constants."""
    return MS.track_open(entry_fill, side, entry, init_sl, now,
                         trail=TRAIL_MULT, max_hold=MAX_HOLD_MIN, cost=COST_RT)


def current_open(now: pd.Timestamp, lookback_hours: int = 10):
    """The currently-open TALOS position (if any) — self-heal for canli (mirrors MIDAS)."""
    trades = generate_trades(now - pd.Timedelta(hours=lookback_hours), now)
    if trades and trades[-1].reason == "open":
        t = trades[-1]
        return {"direction": "long" if t.side > 0 else "short", "entry": t.entry,
                "sl": t.stop, "tp": t.tp_ref, "signal_time": t.signal_time}
    return None


def latest_setup(now: pd.Timestamp, lookback_min: int = 10, *, cost=COST_RT):
    """Fresh TALOS setups whose signal bar closed within `lookback_min` minutes (for canli).
    2-day warmup like MIDAS (EMA/ATR/slope need history; matches the backtest values)."""
    df = load_1m(now - pd.Timedelta(days=2), now)
    if df.empty:
        return []
    df = add_market_open(df)
    bar = pd.Timedelta(minutes=1)
    df = df[df.index + bar <= now]                 # drop the still-forming candle
    if df.empty:
        return []
    atr = atr_tf(df)
    side, stop = signals(df, atr)
    floor = now - pd.Timedelta(minutes=lookback_min)
    out = []
    c = df["close"].to_numpy()
    for i in range(len(df)):
        if side[i] == 0:
            continue
        sig_close = df.index[i] + bar
        if not (floor <= sig_close <= now):
            continue
        entry = float(c[i]); sl = float(stop[i]); sd = abs(entry - sl)
        d = "long" if side[i] > 0 else "short"
        tp = entry + side[i] * TP_REF_MULT * sd
        out.append({"direction": d, "entry": entry, "sl": sl, "tp": float(tp),
                    "signal_time": df.index[i]})
    return out
