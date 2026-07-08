"""TALOS-ICHI — TALOS Keltner-trend + Ichimoku Kumo-colour DIRECTION filter (XAUUSDT 1m).

RESEARCH / PAPER stream (no executor). TALOS decides WHEN (deep Keltner-band pullback in trend);
the Ichimoku cloud colour decides WHETHER the direction agrees with the slow medium-term trend —
a long is kept only when the projected Kumo is bullish (Senkou A > Senkou B), a short only when it
is bearish. This removes TALOS's deep-pullback entries that fight the larger trend ("falling-knife"
catches), which is exactly the population that bleeds in bad regimes.

WHY (validated 2026-07-08, scratchpad/fx_gold/ichimoku_xau.py + midas_ichimoku_filter.py):
the Kumo-colour filter improved TALOS's avgR / WR / PF in ALL THREE years (XAU-2026 + PAXG-2024/25)
and roughly HALVED the worst-year (2024) loss:
  2026 XAU : +86.1R avgR0.267 PF1.51  ->  +89.6R avgR0.501 WR44% PF2.04
  2024 PAXG: -167.7R PF0.55           ->  -61.1R  avgR-0.200 PF0.66
  2025 PAXG: +117.2R PF1.34           ->  +89.7R  avgR0.293 PF1.50
  3-YR     : +35.6R avgR0.023 PF1.04  ->  +118.3R avgR0.150 WR39% PF1.27 (removed book -80.0R)
The SAME filter FAILS on MIDAS (2025 reversed) — it is specific to TALOS's deeper entry.
NOT yet through the full ship battery (period plateau / null / monthly) -> ships as a research/paper
stream only, alongside TALOS, never real money.

Ichimoku is computed on 15m bars (9/26/52, the classic set; Senkou spans shifted +26 FORWARD so the
cloud at the current bar is derived from data >=26 bars in the PAST -> no lookahead). Everything else
(entry metric, exit skeleton, session discipline, cost) is TALOS/MIDAS verbatim.
"""
from __future__ import annotations
import sys
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))                 # sync/ -> trade_sync_common

# Reuse the TALOS module verbatim (which itself reuses the MIDAS engine). Loaded under a unique
# module name — every stream's file is called strategy.py.
_spec = importlib.util.spec_from_file_location("talos_strategy", _HERE.parents[1] / "talos" / "strategy.py")
T = importlib.util.module_from_spec(_spec)
sys.modules["talos_strategy"] = T                         # dataclass needs the module registered
_spec.loader.exec_module(T)
MS = T.MS                                                 # the MIDAS engine surface

SYMBOL = T.SYMBOL                     # XAUUSDT

# ---- TALOS config reused verbatim ----
COST_RT = T.COST_RT
TRAIL_MULT = T.TRAIL_MULT
MAX_HOLD_MIN = T.MAX_HOLD_MIN
TP_REF_MULT = T.TP_REF_MULT
ATR_INIT_MULT = T.ATR_INIT_MULT

# ---- Ichimoku (classic 9/26/52, projected +26) ----
ICHI_TF = "15min"
ICHI_TENKAN = 9
ICHI_KIJUN = 26
ICHI_SENKOU_B = 52
ICHI_SHIFT = 26

# Shared engine surface (identical semantics to TALOS/MIDAS)
load_1m = MS.load_1m
add_market_open = MS.add_market_open
atr_tf = MS.atr_tf
Trade = MS.Trade
walk = MS.walk
_net_r = MS._net_r


def ichimoku_kumo(df: pd.DataFrame):
    """15m Senkou Span A / Span B, shifted +26 FORWARD and ffilled to 1m. No lookahead: a 15m span
    value at bar i is derived from bars <= i-26 (the shift), and label='right'/closed='right' means a
    15m bucket contributes only after it has fully closed. Returns (span_a_1m, span_b_1m) arrays."""
    g = df.resample(ICHI_TF, label="right", closed="right").agg(
        {"high": "max", "low": "min"}).dropna()
    tenkan = (g["high"].rolling(ICHI_TENKAN).max() + g["low"].rolling(ICHI_TENKAN).min()) / 2
    kijun = (g["high"].rolling(ICHI_KIJUN).max() + g["low"].rolling(ICHI_KIJUN).min()) / 2
    span_a = ((tenkan + kijun) / 2).shift(ICHI_SHIFT)
    span_b = ((g["high"].rolling(ICHI_SENKOU_B).max()
               + g["low"].rolling(ICHI_SENKOU_B).min()) / 2).shift(ICHI_SHIFT)
    sa = span_a.reindex(df.index, method="ffill")
    sb = span_b.reindex(df.index, method="ffill")
    return sa, sb


def signals(df: pd.DataFrame, atr: pd.Series | None = None):
    """TALOS (side, stop) then DROP any signal whose direction disagrees with the Kumo colour:
    keep LONG only if Senkou A > Senkou B (bullish cloud), SHORT only if A < B (bearish cloud).
    Signals with no cloud yet (early warmup / NaN span) are dropped (fail-closed)."""
    if atr is None:
        atr = atr_tf(df)
    side, stop = T.signals(df, atr)
    sa, sb = ichimoku_kumo(df)
    sa = sa.to_numpy(); sb = sb.to_numpy()
    for i in np.flatnonzero(side != 0):
        if not (np.isfinite(sa[i]) and np.isfinite(sb[i])):
            side[i] = 0; stop[i] = np.nan; continue
        bull = sa[i] > sb[i]
        keep = bull if side[i] > 0 else (sa[i] < sb[i])
        if not keep:
            side[i] = 0; stop[i] = np.nan
    return side, stop


def generate_trades(start: pd.Timestamp, end: pd.Timestamp, *, cost=COST_RT) -> list:
    """End-to-end: fetch 1m, tag market hours, TALOS-ICHI signals, MIDAS walk -> closed trades."""
    df = load_1m(start - pd.Timedelta(days=2), end)
    if df.empty:
        return []
    df = add_market_open(df)
    atr = atr_tf(df)
    side, stop = signals(df, atr)
    trades = walk(df, side, stop, atr.to_numpy(), cost=cost, trail=TRAIL_MULT, max_hold=MAX_HOLD_MIN)
    return [t for t in trades if t.entry_time >= start]


def track_open(entry_fill: pd.Timestamp, side: int, entry: float, init_sl: float, now: pd.Timestamp):
    """LIVE trailing replay of one open position — TALOS/MIDAS tracker (direction-agnostic once in)."""
    return T.track_open(entry_fill, side, entry, init_sl, now)


def current_open(now: pd.Timestamp, lookback_hours: int = 10):
    """The currently-open TALOS-ICHI position (if any) — self-heal for canli (mirrors TALOS)."""
    trades = generate_trades(now - pd.Timedelta(hours=lookback_hours), now)
    if trades and trades[-1].reason == "open":
        t = trades[-1]
        return {"direction": "long" if t.side > 0 else "short", "entry": t.entry,
                "sl": t.stop, "tp": t.tp_ref, "signal_time": t.signal_time}
    return None


def latest_setup(now: pd.Timestamp, lookback_min: int = 10, *, cost=COST_RT):
    """Fresh TALOS-ICHI setups whose signal bar closed within `lookback_min` minutes (for canli).
    2-day warmup like TALOS/MIDAS (EMA/ATR/slope/Ichimoku need history; matches the backtest)."""
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
