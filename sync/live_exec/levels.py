"""Deterministic leg-price math for the d30so8c live bridge.

ONE place computes every order level from a signal's (entry_close, sl) and the scale-out
constants, so the executor (intent), the parity report, and any test all agree by construction.

All levels are derived in terms of risk0 = |entry_close - sl| (the breakout-close risk), which
makes them EXACTLY reproduce sync/donchian/scaleout.resolve_scaleout under ENTRY_AT_CONFIRM:

  Mode B (·0.5R confirmed entry), long (short mirrors with the sign flipped):
    entry_stop = entry_close + buf*risk0            # STOP that triggers at the confirm level
    eff_entry  = entry_close + buf*risk0            # == scaleout entry_eff (the fav level)
    risk_eff   = (1+buf)*risk0                       # entry_eff -> sl distance
    sl         = entry_close - 1*risk0              # structural full stop (unchanged)
    tp1        = eff_entry + first_r*risk_eff        # book close_frac here  (= entry_close + 2*risk0 for buf .5)
    be         = eff_entry                           # runner stop after TP1
    cap        = entry_close + runner_cap_r*risk0    # == scaleout cap_price (structural, the row's tp_price)

  Mode A (breakout-close LIMIT) sets eff_entry = entry_close and risk_eff = risk0, so
  tp1 = entry_close + first_r*risk0 and cap = entry_close + runner_cap_r*risk0.

These are the INTENDED levels (deterministic). Once the entry actually fills, the executor
re-anchors tp1/be to the real avgFillPrice (B2) while cap stays pinned to the structural price.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Levels:
    direction: str       # 'long' | 'short'
    sign: int            # +1 long, -1 short
    entry_close: float   # breakout-close reference (signal.entry)
    risk0: float         # |entry_close - sl|
    entry_stop: float    # Mode B trigger / Mode A limit price
    eff_entry: float     # intended fill reference
    risk_eff: float      # eff_entry -> sl distance
    sl: float            # structural full stop
    tp1: float           # +first_r of risk_eff -> book close_frac
    be: float            # runner breakeven stop (after TP1)
    cap: float           # runner cap (structural, = the row's tp_price)
    tp1_frac: float      # close_frac (e.g. 0.60)
    runner_frac: float   # 1 - close_frac


def compute_levels(direction: str, entry_close: float, sl: float, *,
                   entry_mode: str, confirm_buf: float, first_r: float,
                   close_frac: float, runner_cap_r: float) -> Levels:
    lng = str(direction).lower() == "long"
    sign = 1 if lng else -1
    risk0 = abs(float(entry_close) - float(sl))
    buf = confirm_buf if entry_mode == "B" else 0.0
    eff_entry = entry_close + sign * buf * risk0
    risk_eff = (1.0 + buf) * risk0
    entry_stop = eff_entry                       # B: STOP at the confirm level; A: LIMIT at entry_close
    return Levels(
        direction="long" if lng else "short",
        sign=sign,
        entry_close=float(entry_close),
        risk0=risk0,
        entry_stop=float(entry_stop),
        eff_entry=float(eff_entry),
        risk_eff=float(risk_eff),
        sl=float(sl),
        tp1=float(eff_entry + sign * first_r * risk_eff),
        be=float(eff_entry),
        cap=float(entry_close + sign * runner_cap_r * risk0),
        tp1_frac=float(close_frac),
        runner_frac=float(1.0 - close_frac),
    )


def reanchor(levels: Levels, avg_fill: float, *, first_r: float) -> Levels:
    """After the entry FILLS at avg_fill, re-anchor tp1/be to the real fill (B2).
    sl stays structural (full close at the original stop); cap stays pinned to the structural
    price (matches the backtest row's tp_price). risk_eff becomes |avg_fill - sl|."""
    risk_eff = abs(float(avg_fill) - levels.sl)
    return Levels(
        direction=levels.direction,
        sign=levels.sign,
        entry_close=levels.entry_close,
        risk0=levels.risk0,
        entry_stop=levels.entry_stop,
        eff_entry=float(avg_fill),
        risk_eff=risk_eff,
        sl=levels.sl,
        tp1=float(avg_fill + levels.sign * first_r * risk_eff),
        be=float(avg_fill),
        cap=levels.cap,
        tp1_frac=levels.tp1_frac,
        runner_frac=levels.runner_frac,
    )
