"""Backtest engine: simulate signal lifecycle bar-by-bar.

State machine per spec §7:
    PENDING -> ACTIVE -> (FILLED -> TP_HIT | SL_HIT) | EXPIRED | INVALIDATED
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
import json
from pathlib import Path

import pandas as pd

from ict import config as C
from ict.strategies import Signal


def _net_r(entry: float, exit_price: float, risk: float, direction: str) -> float:
    """R after round-trip friction: C.FEE_PCT_PER_SIDE of notional on each leg.
    A losing trade therefore costs slightly more than -1R and a TP slightly
    less than its gross RR — matching what a live taker fill actually pays."""
    if risk <= 0:
        return 0.0
    gross = (exit_price - entry) if direction == "long" else (entry - exit_price)
    fees = C.FEE_PCT_PER_SIDE * (entry + exit_price)
    return (gross - fees) / risk


class TradeStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"
    TP_HIT = "tp_hit"
    SL_HIT = "sl_hit"


@dataclass
class TradeResult:
    signal: Signal
    status: TradeStatus
    entry_index: Optional[int] = None
    exit_index: Optional[int] = None
    exit_price: Optional[float] = None
    pnl_r: Optional[float] = None    # in R units
    pnl_pct: Optional[float] = None  # raw % move from entry
    bars_to_exit: Optional[int] = None

    def to_dict(self) -> dict:
        d = {
            "signal": self.signal.to_dict(),
            "status": self.status.value,
            "entry_index": self.entry_index,
            "exit_index": self.exit_index,
            "exit_price": self.exit_price,
            "pnl_r": self.pnl_r,
            "pnl_pct": self.pnl_pct,
            "bars_to_exit": self.bars_to_exit,
        }
        return d


def _resolve_partial(sig: Signal, df: pd.DataFrame, entry_idx: int) -> TradeResult:
    """Partial-TP + breakeven lifecycle (ict/config.PARTIAL_TP_*), from the entry bar.

    Scale out C.PARTIAL_TP_CLOSE_FRAC of the position at C.PARTIAL_TP_TRIGGER_FRAC of
    the distance entry->TP1 and (if PARTIAL_TP_BREAKEVEN) pull the stop to entry; the
    remainder targets TP1. Reported R is the notional-weighted sum of the two legs
    (round-trip fees per leg via _net_r — fractions sum to 1, so the entry fee is
    charged exactly once). Status is sign-based on the blended R (pnl>0 -> tp_hit, else
    sl_hit) so the 1m resolver and compute_metrics — which key on tp_hit/sl_hit — count
    a net-positive scale-out as a win and a net-negative one as a loss. The breakeven
    stop is only armed from the bar AFTER the partial (the entry bar's low/high is the
    pre-fill wick, not a post-partial reversal)."""
    n = len(df)
    long = sig.direction == "long"
    entry, tp1 = sig.entry, sig.take_profit_1
    risk = abs(entry - sig.stop_loss)
    cf = C.PARTIAL_TP_CLOSE_FRAC
    partial_level = entry + C.PARTIAL_TP_TRIGGER_FRAC * (tp1 - entry)  # long & short

    def pct(px):
        return (px - entry) / entry * (1 if long else -1)

    def out(status, j, exit_price, pnl_r, pnl_pct):
        return TradeResult(sig, status, entry_index=entry_idx, exit_index=j,
                           exit_price=exit_price, pnl_r=pnl_r, pnl_pct=pnl_pct,
                           bars_to_exit=j - sig.bar_index)

    def classify(pnl_r):
        return TradeStatus.TP_HIT if pnl_r > 0 else TradeStatus.SL_HIT

    partial_done = False
    banked_r = 0.0
    banked_pct = 0.0
    stop = sig.stop_loss
    for j in range(entry_idx, n):
        bar = df.iloc[j]
        hi, lo = bar["high"], bar["low"]
        if long:
            stop_touched, tp_touched, partial_touched = lo <= stop, hi >= tp1, hi >= partial_level
        else:
            stop_touched, tp_touched, partial_touched = hi >= stop, lo <= tp1, lo <= partial_level

        if not partial_done:
            if stop_touched and not tp_touched:                       # full stop, no partial yet
                return out(TradeStatus.SL_HIT, j, stop,
                           _net_r(entry, stop, risk, sig.direction), pct(stop))
            if tp_touched:                                            # gap through partial + TP1
                if stop_touched:                                      # worst case: stop first
                    return out(TradeStatus.SL_HIT, j, stop,
                               _net_r(entry, stop, risk, sig.direction), pct(stop))
                pnl = cf * _net_r(entry, partial_level, risk, sig.direction) \
                    + (1 - cf) * _net_r(entry, tp1, risk, sig.direction)
                return out(classify(pnl), j, tp1, pnl, cf * pct(partial_level) + (1 - cf) * pct(tp1))
            if partial_touched:                                       # scale out, arm breakeven
                banked_r = cf * _net_r(entry, partial_level, risk, sig.direction)
                banked_pct = cf * pct(partial_level)
                partial_done = True
                if C.PARTIAL_TP_BREAKEVEN:
                    stop = entry
                continue
        else:                                                         # remainder rides to TP1 / stop
            if tp_touched and not stop_touched:
                pnl = banked_r + (1 - cf) * _net_r(entry, tp1, risk, sig.direction)
                return out(TradeStatus.TP_HIT, j, tp1, pnl, banked_pct + (1 - cf) * pct(tp1))
            if stop_touched:                                          # both -> worst case stop first
                pnl = banked_r + (1 - cf) * _net_r(entry, stop, risk, sig.direction)
                return out(classify(pnl), j, stop, pnl, banked_pct + (1 - cf) * pct(stop))

    return TradeResult(sig, TradeStatus.ACTIVE, entry_index=entry_idx)


def _dir_confirmed(sig: Signal, df: pd.DataFrame, expiry: int, n: int) -> str:
    """Directional entry confirmation (C.ENTRY_CONFIRM_BUF). Within the fill window, return
    'fav' if price extends FAVOURABLY (toward TP) by buf*risk before moving adversely (toward
    SL) by buf*risk, 'adv' if it goes adverse first (ties -> adv, pessimistic), or 'none' if
    neither happens in the window. buf<=0 -> always 'fav' (gate off)."""
    buf = getattr(C, "ENTRY_CONFIRM_BUF", 0.0)
    risk = abs(sig.entry - sig.stop_loss)
    if buf <= 0 or risk <= 0:
        return "fav"
    long = sig.direction == "long"
    fav_lvl = sig.entry + buf * risk if long else sig.entry - buf * risk
    adv_lvl = sig.entry - buf * risk if long else sig.entry + buf * risk
    for i in range(sig.bar_index + 1, min(expiry, n - 1) + 1):
        bar = df.iloc[i]
        if long:
            adv, fav = bar["low"] <= adv_lvl, bar["high"] >= fav_lvl
        else:
            adv, fav = bar["high"] >= adv_lvl, bar["low"] <= fav_lvl
        if adv:
            return "adv"
        if fav:
            return "fav"
    return "none"


def simulate_signal(sig: Signal, df: pd.DataFrame, *,
                    use_tp1_only: bool = True) -> TradeResult:
    """Walk forward from sig.bar_index+1 to fill / TP / SL / expiry."""
    n = len(df)
    expiry = sig.expires_at_index or (sig.bar_index + 12)

    # Directional entry confirmation: only TAKE the trade if the breakout confirms its
    # direction first (price moves toward TP by buf*risk before toward SL). A reversal back
    # toward the stop (the AVAX-short case) -> no trade. Off when C.ENTRY_CONFIRM_BUF <= 0.
    conf = _dir_confirmed(sig, df, expiry, n)
    if conf == "adv":
        return TradeResult(sig, TradeStatus.INVALIDATED)
    if conf == "none":
        return TradeResult(sig, TradeStatus.EXPIRED)

    entry_idx: Optional[int] = None
    for i in range(sig.bar_index + 1, min(expiry, n - 1) + 1):
        bar = df.iloc[i]
        if sig.direction == "long":
            entry_touched = bar["low"] <= sig.entry
            tp_touched = bar["high"] >= sig.take_profit_1
            sl_touched = bar["low"] <= sig.stop_loss
        else:
            entry_touched = bar["high"] >= sig.entry
            tp_touched = bar["low"] <= sig.take_profit_1
            sl_touched = bar["high"] >= sig.stop_loss

        if not entry_touched and (tp_touched or sl_touched):
            return TradeResult(sig, TradeStatus.INVALIDATED, exit_index=i, bars_to_exit=i - sig.bar_index)

        if entry_touched:
            entry_idx = i
            if C.PARTIAL_TP_ENABLED:
                return _resolve_partial(sig, df, i)
            # within same bar, decide TP or SL by which extreme is closer to open (worst-case heuristic)
            risk = abs(sig.entry - sig.stop_loss)
            if sl_touched and tp_touched:
                # ambiguous in same bar — worst case: assume SL hits first
                return TradeResult(sig, TradeStatus.SL_HIT, entry_index=i, exit_index=i,
                                   exit_price=sig.stop_loss,
                                   pnl_r=_net_r(sig.entry, sig.stop_loss, risk, sig.direction),
                                   pnl_pct=(sig.stop_loss - sig.entry) / sig.entry * (1 if sig.direction == "long" else -1),
                                   bars_to_exit=i - sig.bar_index)
            if tp_touched:
                return TradeResult(sig, TradeStatus.TP_HIT, entry_index=i, exit_index=i,
                                   exit_price=sig.take_profit_1,
                                   pnl_r=_net_r(sig.entry, sig.take_profit_1, risk, sig.direction),
                                   pnl_pct=(sig.take_profit_1 - sig.entry) / sig.entry * (1 if sig.direction == "long" else -1),
                                   bars_to_exit=i - sig.bar_index)
            if sl_touched:
                return TradeResult(sig, TradeStatus.SL_HIT, entry_index=i, exit_index=i,
                                   exit_price=sig.stop_loss,
                                   pnl_r=_net_r(sig.entry, sig.stop_loss, risk, sig.direction),
                                   pnl_pct=(sig.stop_loss - sig.entry) / sig.entry * (1 if sig.direction == "long" else -1),
                                   bars_to_exit=i - sig.bar_index)
            break

    if entry_idx is None:
        return TradeResult(sig, TradeStatus.EXPIRED)

    # entered but not exited within signal expiry — keep walking until TP/SL or end of data
    risk = abs(sig.entry - sig.stop_loss)
    for j in range(entry_idx + 1, n):
        bar = df.iloc[j]
        if sig.direction == "long":
            tp_touched = bar["high"] >= sig.take_profit_1
            sl_touched = bar["low"] <= sig.stop_loss
        else:
            tp_touched = bar["low"] <= sig.take_profit_1
            sl_touched = bar["high"] >= sig.stop_loss

        if tp_touched and sl_touched:
            return TradeResult(sig, TradeStatus.SL_HIT, entry_index=entry_idx, exit_index=j,
                               exit_price=sig.stop_loss,
                                   pnl_r=_net_r(sig.entry, sig.stop_loss, risk, sig.direction),
                               pnl_pct=(sig.stop_loss - sig.entry) / sig.entry * (1 if sig.direction == "long" else -1),
                               bars_to_exit=j - sig.bar_index)
        if tp_touched:
            return TradeResult(sig, TradeStatus.TP_HIT, entry_index=entry_idx, exit_index=j,
                               exit_price=sig.take_profit_1,
                               pnl_r=abs(sig.take_profit_1 - sig.entry) / risk if risk > 0 else 0.0,
                               pnl_pct=(sig.take_profit_1 - sig.entry) / sig.entry * (1 if sig.direction == "long" else -1),
                               bars_to_exit=j - sig.bar_index)
        if sl_touched:
            return TradeResult(sig, TradeStatus.SL_HIT, entry_index=entry_idx, exit_index=j,
                               exit_price=sig.stop_loss,
                                   pnl_r=_net_r(sig.entry, sig.stop_loss, risk, sig.direction),
                               pnl_pct=(sig.stop_loss - sig.entry) / sig.entry * (1 if sig.direction == "long" else -1),
                               bars_to_exit=j - sig.bar_index)

    return TradeResult(sig, TradeStatus.ACTIVE, entry_index=entry_idx)


def simulate_signals(signals: list[Signal], df: pd.DataFrame) -> list[TradeResult]:
    return [simulate_signal(s, df) for s in signals]


# ----------------------------- metrics -----------------------------

def compute_metrics(results: list[TradeResult]) -> dict:
    closed = [r for r in results if r.status in (TradeStatus.TP_HIT, TradeStatus.SL_HIT)]
    expired = [r for r in results if r.status == TradeStatus.EXPIRED]
    invalidated = [r for r in results if r.status == TradeStatus.INVALIDATED]
    open_ = [r for r in results if r.status == TradeStatus.ACTIVE]

    wins = [r for r in closed if r.status == TradeStatus.TP_HIT]
    losses = [r for r in closed if r.status == TradeStatus.SL_HIT]

    total_r = sum((r.pnl_r or 0) for r in closed)
    avg_r_win = (sum(r.pnl_r for r in wins) / len(wins)) if wins else 0.0
    avg_r_loss = (sum(r.pnl_r for r in losses) / len(losses)) if losses else 0.0

    cumulative = []
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in closed:
        cum += r.pnl_r or 0
        cumulative.append(cum)
        peak = max(peak, cum)
        max_dd = min(max_dd, cum - peak)

    expectancy = (total_r / len(closed)) if closed else 0.0
    win_rate = (len(wins) / len(closed)) if closed else 0.0

    return {
        "total_signals": len(results),
        "closed": len(closed),
        "expired": len(expired),
        "invalidated": len(invalidated),
        "still_open": len(open_),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 4),
        "total_r": round(total_r, 4),
        "expectancy_r": round(expectancy, 4),
        "avg_r_win": round(avg_r_win, 4),
        "avg_r_loss": round(avg_r_loss, 4),
        "max_drawdown_r": round(max_dd, 4),
        "by_strategy": _group_by_strategy(results),
    }


def _group_by_strategy(results: list[TradeResult]) -> dict:
    out: dict = {}
    for r in results:
        key = r.signal.strategy
        if key not in out:
            out[key] = {"n": 0, "wins": 0, "losses": 0, "total_r": 0.0}
        out[key]["n"] += 1
        if r.status == TradeStatus.TP_HIT:
            out[key]["wins"] += 1
            out[key]["total_r"] += r.pnl_r or 0
        elif r.status == TradeStatus.SL_HIT:
            out[key]["losses"] += 1
            out[key]["total_r"] += r.pnl_r or 0

    for key, v in out.items():
        closed_n = v["wins"] + v["losses"]
        v["win_rate"] = round(v["wins"] / closed_n, 4) if closed_n else 0.0
        v["expectancy_r"] = round(v["total_r"] / closed_n, 4) if closed_n else 0.0
        v["total_r"] = round(v["total_r"], 4)
    return out


def export_results(results: list[TradeResult], path: str | Path) -> None:
    path = Path(path)
    payload = {
        "metrics": compute_metrics(results),
        "trades": [r.to_dict() for r in results],
    }
    path.write_text(json.dumps(payload, indent=2, default=str))
