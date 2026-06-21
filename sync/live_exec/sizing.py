"""Position sizing — fixed USD risk per trade -> contract qty, then the 60/40 leg split.

risk_usd is the USD lost if the FULL position is stopped at sl, so:
    qty = risk_usd / |entry - sl|              (then floored to LOT_SIZE.stepSize)
TP1 books close_frac of that (floored to the step); the runner is whatever the position
ACTUALLY has left after TP1 fills (read from positionRisk), not a recomputed 40% — rounding
makes the real remainder drift from the nominal split.
"""
from __future__ import annotations

from exchange_info import ExchangeInfo


def qty_for_risk(entry: float, sl: float, risk_usd: float) -> float:
    """Raw (un-quantized) contract qty so a full stop loses ~risk_usd."""
    dist = abs(float(entry) - float(sl))
    if dist <= 0:
        return 0.0
    return risk_usd / dist


def plan_qty(symbol: str, entry: float, sl: float, risk_usd: float,
             xi: ExchangeInfo) -> tuple[float, float]:
    """Return (total_qty, tp1_qty) both floored to the exchange step. tp1_qty is close_frac of
    the floored total, itself floored. Caller still checks passes_min_notional on total_qty."""
    raw = qty_for_risk(entry, sl, risk_usd)
    total = xi.floor_qty(symbol, raw)
    return total, total      # tp1 split is applied by split_tp1 once close_frac is known


def split_tp1(symbol: str, total_qty: float, close_frac: float, xi: ExchangeInfo) -> float:
    """TP1 leg qty = floor_step(close_frac * total). Runner = total - tp1 (computed at fill time
    from the real residual, this is only the INTENDED split for the order)."""
    return xi.floor_qty(symbol, total_qty * close_frac)
