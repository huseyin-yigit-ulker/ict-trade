"""Five ICT signal strategies (A–E) per ICT_Signal_Strategies.md.

Each strategy is implemented as a function that, given pre-computed detector
outputs and the current bar index, returns a `Signal` or None.

Signals are produced bar-by-bar so the strategy engine can scan a full DataFrame.
No look-ahead: only data at indices <= current_index is consumed.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional
import uuid

import pandas as pd

from . import config as C
from .detectors import (
    Swing, StructureEvent, LiquidityLevel, OrderBlock, FVG, PDZone,
    htf_bias, killzone_at, in_killzones, in_ote,
)


@dataclass
class Signal:
    signal_id: str
    timestamp: pd.Timestamp
    strategy: str
    symbol: str
    direction: str
    entry: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: Optional[float]
    risk_reward_1: float
    risk_reward_2: Optional[float]
    quality: str = "medium"
    confluence_score: int = 0
    confluence_factors: list[str] = field(default_factory=list)
    context: dict = field(default_factory=dict)
    expires_at_index: Optional[int] = None
    bar_index: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d


# ----------------------------- helpers -----------------------------

def _next_opposite_liquidity(price: float, direction: str, levels: list[LiquidityLevel],
                             at_index: int) -> Optional[float]:
    """Closest unswept opposite-side liquidity level visible at `at_index`."""
    candidates = []
    for lvl in levels:
        if lvl.created_at_index > at_index:
            continue
        if lvl.swept and lvl.swept_at_index is not None and lvl.swept_at_index <= at_index:
            continue
        if direction == "long" and lvl.level > price:
            candidates.append(lvl.level)
        elif direction == "short" and lvl.level < price:
            candidates.append(lvl.level)
    if not candidates:
        return None
    return min(candidates) if direction == "long" else max(candidates)


def _next_persistent_liquidity(price: float, direction: str, levels: list[LiquidityLevel],
                               at_index: int) -> Optional[float]:
    persistent = [l for l in levels if l.type in ("PDH", "PDL", "PWH", "PWL")]
    return _next_opposite_liquidity(price, direction, persistent, at_index)


def _cap_tp(entry: float, tp: Optional[float], direction: str, atr_value: float) -> Optional[float]:
    """Clamp TP1 distance to TP_MAX_ATR_MULT * ATR. Prevents 16R fantasy targets
    when the next opposite liquidity is unrealistically far."""
    if tp is None or atr_value <= 0 or C.TP_MAX_ATR_MULT <= 0:
        return tp
    max_dist = C.TP_MAX_ATR_MULT * atr_value
    if direction == "long":
        return min(tp, entry + max_dist)
    return max(tp, entry - max_dist)


def _floor_stop(entry: float, stop: float, direction: str, atr_value: float) -> float:
    """Enforce a minimum SL distance of max(MIN_SL_DIST_PCT * entry,
    MIN_SL_DIST_ATR * ATR). Razor-thin zones otherwise put the stop inside the
    spread and mint fantasy 13R wins that live fills can't deliver."""
    min_dist = max(C.MIN_SL_DIST_PCT * abs(entry), C.MIN_SL_DIST_ATR * atr_value)
    if direction == "long":
        return min(stop, entry - min_dist)
    return max(stop, entry + min_dist)


def _resolve_bias(structure_events: list, at_index: int,
                  htf_bias_series: Optional[pd.Series]) -> str:
    if htf_bias_series is not None and at_index < len(htf_bias_series):
        v = htf_bias_series.iloc[at_index]
        if isinstance(v, str):
            return v
    return htf_bias(structure_events, at_index)


def _expiry(at_index: int, expiry_bars: Optional[int]) -> int:
    return at_index + (expiry_bars if expiry_bars is not None else C.ENTRY_EXPIRY_BARS)


def _ob_alive_at(ob, at_index: int) -> bool:
    """Time-aware OB visibility:
    - the OB must already be CONFIRMED by `at_index` (its impulse must have fired)
    - it must not yet be mitigated by `at_index`
    Both checks are required for real-time parity."""
    if ob.confirmed_at_index > at_index:
        return False
    if not ob.mitigated:
        return True
    return ob.mitigation_index is None or ob.mitigation_index > at_index


def _fvg_alive_at(fvg, at_index: int) -> bool:
    """Was this FVG unfilled at `at_index`?"""
    return fvg.filled_at_index is None or fvg.filled_at_index > at_index


def _rr(entry: float, stop: float, target: float, direction: str) -> float:
    risk = abs(entry - stop)
    reward = abs(target - entry)
    if risk == 0:
        return 0.0
    return reward / risk if (
        (direction == "long" and target > entry) or (direction == "short" and target < entry)
    ) else 0.0


def _atr_at(atr_series: pd.Series, idx: int) -> float:
    if idx >= len(atr_series):
        return 0.0
    val = atr_series.iloc[idx]
    return float(val) if not pd.isna(val) else 0.0


# ----------------------------- Strategy A: Liquidity Sweep Reversal -----------------------------

def strategy_a(symbol: str,
               df: pd.DataFrame,
               at_index: int,
               atr_series: pd.Series,
               structure_events: list[StructureEvent],
               liquidity_levels: list[LiquidityLevel],
               obs: list[OrderBlock],
               fvgs: list[FVG],
               htf_bias_series: Optional[pd.Series] = None,
               expiry_bars: Optional[int] = None) -> Optional[Signal]:
    ts = df.index[at_index]
    if not in_killzones(ts, ["london_open", "ny_open", "silver_bullet_am", "silver_bullet_pm"]):
        return None

    bias = _resolve_bias(structure_events, at_index, htf_bias_series)
    if bias == "range":
        return None

    recent = [
        l for l in liquidity_levels
        if l.swept and l.swept_at_index is not None
        and at_index - C.SWEEP_LOOKBACK_BARS <= l.swept_at_index <= at_index
    ]
    if not recent:
        return None
    swept = recent[-1]

    # CHoCH after sweep, in HTF bias direction.
    # `e.broken_at_index <= at_index` is critical: without it the strategy sees
    # CHoCHes from FUTURE bars (look-ahead bias).
    choch = next(
        (e for e in structure_events
         if e.type == "CHoCH"
         and e.broken_at_index <= at_index
         and swept.swept_at_index <= e.broken_at_index <= swept.swept_at_index + C.CHOCH_AFTER_SWEEP_BARS
         and ((bias == "bullish" and e.direction == "bullish") or (bias == "bearish" and e.direction == "bearish"))),
        None
    )
    if not choch:
        return None

    # find OB / FVG produced by the impulse that drove the CHoCH
    impulse_window = range(swept.swept_at_index, choch.broken_at_index + 1)
    candidate_obs = [
        o for o in obs
        if o.created_at_index in impulse_window
        and _ob_alive_at(o, at_index)
        and ((bias == "bullish" and o.type == "bullish_ob") or (bias == "bearish" and o.type == "bearish_ob"))
    ]
    candidate_fvgs = [
        f for f in fvgs
        if f.created_at_index in impulse_window
        and _fvg_alive_at(f, at_index)
        and ((bias == "bullish" and f.type == "bullish_fvg") or (bias == "bearish" and f.type == "bearish_fvg"))
    ]
    if not candidate_obs and not candidate_fvgs:
        return None

    if candidate_obs:
        ob = candidate_obs[-1]
        entry_zone_top, entry_zone_bottom = ob.top, ob.bottom
    else:
        f = candidate_fvgs[-1]
        entry_zone_top, entry_zone_bottom = f.top, f.bottom

    direction = "long" if bias == "bullish" else "short"
    entry = (entry_zone_top + entry_zone_bottom) / 2

    a = _atr_at(atr_series, at_index)
    if direction == "long":
        stop = swept.sweep_extreme - C.SL_ATR_BUFFER * a
    else:
        stop = swept.sweep_extreme + C.SL_ATR_BUFFER * a
    stop = _floor_stop(entry, stop, direction, a)

    tp1 = _next_opposite_liquidity(entry, direction, liquidity_levels, at_index)
    tp1 = _cap_tp(entry, tp1, direction, a)
    tp2 = _next_persistent_liquidity(entry, direction, liquidity_levels, at_index)
    if tp1 is None:
        return None

    rr1 = _rr(entry, stop, tp1, direction)
    if rr1 < C.MIN_RR_DEFAULT:
        return None
    rr2 = _rr(entry, stop, tp2, direction) if tp2 is not None else None

    # OTE quality
    leg_high = max(swept.sweep_extreme, df["high"].iloc[choch.broken_at_index])
    leg_low = min(swept.sweep_extreme, df["low"].iloc[choch.broken_at_index])
    zone = PDZone(leg_high, leg_low)
    ote = in_ote(zone, entry, "bullish" if direction == "long" else "bearish")

    factors = ["htf_aligned", "liquidity_swept", "ltf_choch", "in_killzone"]
    if ote:
        factors.append("ote_zone")
    if (direction == "long" and zone.is_discount(entry)) or (direction == "short" and zone.is_premium(entry)):
        factors.append("discount_premium")

    quality = "high" if ote else "medium"

    return Signal(
        signal_id=str(uuid.uuid4()),
        timestamp=ts,
        strategy="A_liquidity_sweep_reversal",
        symbol=symbol,
        direction=direction,
        entry=float(entry),
        stop_loss=float(stop),
        take_profit_1=float(tp1),
        take_profit_2=float(tp2) if tp2 is not None else None,
        risk_reward_1=float(rr1),
        risk_reward_2=float(rr2) if rr2 is not None else None,
        quality=quality,
        confluence_factors=factors,
        context={
            "htf_bias": bias,
            "swept_liquidity": swept.type,
            "ote_zone": ote,
            "killzone": killzone_at(ts),
        },
        expires_at_index=_expiry(at_index, expiry_bars),
        bar_index=at_index,
    )


# ----------------------------- Strategy B: Power of Three -----------------------------

def _asia_range_for(df: pd.DataFrame, at_index: int) -> Optional[tuple[float, float, int, int]]:
    """Return (high, low, start_idx, end_idx) of the Asia session that ended most recently
    before `at_index`. Asia is NY 19:00–24:00."""
    ts = df.index[at_index]
    ny = ts.tz_convert(C.NY_TZ) if ts.tz is not None else ts.tz_localize("UTC").tz_convert(C.NY_TZ)
    ny_today = ny.normalize()
    # Asia session: previous calendar day 19:00 NY -> today 00:00 NY
    asia_start_ny = ny_today - pd.Timedelta(days=1) + pd.Timedelta(hours=19)
    asia_end_ny = ny_today
    asia_start = asia_start_ny.tz_convert("UTC")
    asia_end = asia_end_ny.tz_convert("UTC")

    mask = (df.index >= asia_start) & (df.index < asia_end)
    sub = df.loc[mask]
    if sub.empty:
        return None
    start_idx = df.index.get_loc(sub.index[0])
    end_idx = df.index.get_loc(sub.index[-1])
    return float(sub["high"].max()), float(sub["low"].min()), start_idx, end_idx


def strategy_b(symbol: str,
               df: pd.DataFrame,
               at_index: int,
               atr_series: pd.Series,
               structure_events: list[StructureEvent],
               liquidity_levels: list[LiquidityLevel],
               obs: list[OrderBlock],
               fvgs: list[FVG],
               htf_bias_series: Optional[pd.Series] = None,
               expiry_bars: Optional[int] = None) -> Optional[Signal]:
    ts = df.index[at_index]
    if not in_killzones(ts, ["london_open", "ny_open"]):
        return None

    rng = _asia_range_for(df, at_index)
    if not rng:
        return None
    a_hi, a_lo, _asia_start_i, asia_end_i = rng

    a = _atr_at(atr_series, at_index)
    if a <= 0:
        return None
    if (a_hi - a_lo) > C.ASIA_RANGE_MAX_ATR * a:
        return None

    # Look for manipulation: between asia_end_i and at_index, did price wick outside the range
    # then close back inside?
    sweep_dir = None  # "above" or "below"
    sweep_idx = None
    for j in range(asia_end_i + 1, at_index + 1):
        if df["high"].iloc[j] > a_hi and df["close"].iloc[j] < a_hi:
            sweep_dir = "above"
            sweep_idx = j
            break
        if df["low"].iloc[j] < a_lo and df["close"].iloc[j] > a_lo:
            sweep_dir = "below"
            sweep_idx = j
            break
    if sweep_dir is None or sweep_idx is None:
        return None

    direction = "short" if sweep_dir == "above" else "long"

    # CHoCH against the manipulation, after sweep
    choch = next(
        (e for e in structure_events
         if e.type == "CHoCH"
         and sweep_idx <= e.broken_at_index <= at_index
         and ((direction == "short" and e.direction == "bearish") or (direction == "long" and e.direction == "bullish"))),
        None
    )
    if not choch:
        return None

    # entry zone: OB or FVG from the manipulation leg
    impulse_range = range(sweep_idx, choch.broken_at_index + 1)
    candidate_obs = [
        o for o in obs
        if o.created_at_index in impulse_range
        and _ob_alive_at(o, at_index)
        and ((direction == "long" and o.type == "bullish_ob") or (direction == "short" and o.type == "bearish_ob"))
    ]
    candidate_fvgs = [
        f for f in fvgs
        if f.created_at_index in impulse_range
        and _fvg_alive_at(f, at_index)
        and ((direction == "long" and f.type == "bullish_fvg") or (direction == "short" and f.type == "bearish_fvg"))
    ]
    if not candidate_obs and not candidate_fvgs:
        return None

    if candidate_obs:
        zone_top, zone_bottom = candidate_obs[-1].top, candidate_obs[-1].bottom
    else:
        zone_top, zone_bottom = candidate_fvgs[-1].top, candidate_fvgs[-1].bottom

    entry = (zone_top + zone_bottom) / 2
    sweep_extreme = float(df["high"].iloc[sweep_idx]) if sweep_dir == "above" else float(df["low"].iloc[sweep_idx])
    stop = sweep_extreme + C.SL_ATR_BUFFER * a if direction == "short" else sweep_extreme - C.SL_ATR_BUFFER * a
    stop = _floor_stop(entry, stop, direction, a)

    tp1 = a_lo if direction == "short" else a_hi
    tp1 = _cap_tp(entry, tp1, direction, a)
    tp2 = _next_persistent_liquidity(entry, direction, liquidity_levels, at_index)
    rr1 = _rr(entry, stop, tp1, direction)
    if rr1 < C.MIN_RR_DEFAULT:
        return None
    rr2 = _rr(entry, stop, tp2, direction) if tp2 is not None else None

    factors = ["liquidity_swept", "ltf_choch", "in_killzone", "power_of_three"]
    bias_now = _resolve_bias(structure_events, at_index, htf_bias_series)
    if (direction == "long" and bias_now == "bullish") or (direction == "short" and bias_now == "bearish"):
        factors.append("htf_aligned")

    return Signal(
        signal_id=str(uuid.uuid4()),
        timestamp=ts,
        strategy="B_power_of_three",
        symbol=symbol,
        direction=direction,
        entry=float(entry),
        stop_loss=float(stop),
        take_profit_1=float(tp1),
        take_profit_2=float(tp2) if tp2 is not None else None,
        risk_reward_1=float(rr1),
        risk_reward_2=float(rr2) if rr2 is not None else None,
        quality="medium",
        confluence_factors=factors,
        context={
            "asia_high": a_hi, "asia_low": a_lo,
            "sweep_dir": sweep_dir,
            "killzone": killzone_at(ts),
        },
        expires_at_index=_expiry(at_index, expiry_bars),
        bar_index=at_index,
    )


# ----------------------------- Strategy C: FVG + OB Confluence -----------------------------

def _overlap_pct(a_top: float, a_bot: float, b_top: float, b_bot: float) -> float:
    inter = max(0.0, min(a_top, b_top) - max(a_bot, b_bot))
    union = max(a_top, b_top) - min(a_bot, b_bot)
    return inter / union if union > 0 else 0.0


def strategy_c(symbol: str,
               df: pd.DataFrame,
               at_index: int,
               atr_series: pd.Series,
               structure_events: list[StructureEvent],
               liquidity_levels: list[LiquidityLevel],
               obs: list[OrderBlock],
               fvgs: list[FVG],
               htf_bias_series: Optional[pd.Series] = None,
               expiry_bars: Optional[int] = None) -> Optional[Signal]:
    bias = _resolve_bias(structure_events, at_index, htf_bias_series)
    if bias == "range":
        return None

    # 2 consecutive same-direction BOS confirms a real trend (uses primary-TF
    # structure since HTF structure is implicit via htf_bias_series)
    bos_seq = [e for e in structure_events if e.type == "BOS" and e.broken_at_index <= at_index]
    if len(bos_seq) < 2 or bos_seq[-1].direction != bos_seq[-2].direction:
        return None

    direction = "long" if bias == "bullish" else "short"
    side = "bullish" if direction == "long" else "bearish"

    a = _atr_at(atr_series, at_index)
    if a <= 0:
        return None

    price = float(df["close"].iloc[at_index])
    age_floor = at_index - C.ZONE_MAX_AGE_BARS
    valid_obs = [o for o in obs if age_floor <= o.created_at_index <= at_index
                 and _ob_alive_at(o, at_index) and o.type == f"{side}_ob"]
    valid_fvgs = [f for f in fvgs if age_floor <= f.created_at_index <= at_index
                  and _fvg_alive_at(f, at_index) and f.type == f"{side}_fvg"]

    # Pick the confluence zone CLOSEST to current price (not highest overlap).
    # The strategy fires when price approaches a known zone — picking the
    # highest-overlap zone often returns one far from price, never triggering.
    best = None  # (distance_to_price, ovl, top, bot)
    for o in valid_obs:
        for f in valid_fvgs:
            ovl = _overlap_pct(o.top, o.bottom, f.top, f.bottom)
            if ovl >= C.OB_FVG_OVERLAP_MIN:
                top = max(o.top, f.top)
                bot = min(o.bottom, f.bottom)
                mid = (top + bot) / 2
                dist = abs(price - mid)
                if best is None or dist < best[0]:
                    best = (dist, ovl, top, bot)

    if not best:
        return None

    dist, _, top, bot = best
    if dist > C.STRAT_C_PROXIMITY_ATR * a:
        return None  # nearest zone still too far

    entry = bot if direction == "long" else top
    stop = (bot - C.SL_ATR_BUFFER_C * a) if direction == "long" else (top + C.SL_ATR_BUFFER_C * a)
    stop = _floor_stop(entry, stop, direction, a)

    # TP1: last opposite swing-ish — use most recent opposite-side liquidity
    tp1 = _next_opposite_liquidity(entry, direction, liquidity_levels, at_index)
    tp1 = _cap_tp(entry, tp1, direction, a)
    tp2 = _next_persistent_liquidity(entry, direction, liquidity_levels, at_index)
    if tp1 is None:
        return None
    rr1 = _rr(entry, stop, tp1, direction)
    if rr1 < C.MIN_RR_DEFAULT:
        return None
    rr2 = _rr(entry, stop, tp2, direction) if tp2 is not None else None

    return Signal(
        signal_id=str(uuid.uuid4()),
        timestamp=df.index[at_index],
        strategy="C_fvg_ob_confluence",
        symbol=symbol,
        direction=direction,
        entry=float(entry),
        stop_loss=float(stop),
        take_profit_1=float(tp1),
        take_profit_2=float(tp2) if tp2 is not None else None,
        risk_reward_1=float(rr1),
        risk_reward_2=float(rr2) if rr2 is not None else None,
        quality="high",
        confluence_factors=["htf_aligned", "ob_fvg_overlap", "in_killzone"]
            if in_killzones(df.index[at_index], ["london_open", "ny_open"]) else
            ["htf_aligned", "ob_fvg_overlap"],
        context={"htf_bias": bias, "killzone": killzone_at(df.index[at_index])},
        expires_at_index=_expiry(at_index, expiry_bars),
        bar_index=at_index,
    )


# ----------------------------- Strategy D: Silver Bullet -----------------------------

def strategy_d(symbol: str,
               df: pd.DataFrame,
               at_index: int,
               atr_series: pd.Series,
               structure_events: list[StructureEvent],
               liquidity_levels: list[LiquidityLevel],
               obs: list[OrderBlock],
               fvgs: list[FVG],
               htf_bias_series: Optional[pd.Series] = None,
               expiry_bars: Optional[int] = None) -> Optional[Signal]:
    if symbol in C.D_EXCLUDE_SYMBOLS:
        return None
    ts = df.index[at_index]
    if not in_killzones(ts, ["silver_bullet_am", "silver_bullet_pm"]):
        return None

    bias = _resolve_bias(structure_events, at_index, htf_bias_series)
    if bias == "range":
        return None
    direction = "long" if bias == "bullish" else "short"
    side = "bullish" if direction == "long" else "bearish"

    # need a sweep within last ~60 1m bars (roughly)
    sweep = next(
        (l for l in liquidity_levels
         if l.swept and l.swept_at_index is not None
         and at_index - 60 <= l.swept_at_index <= at_index),
        None
    )
    if not sweep:
        return None

    # FVG created within current killzone window (today)
    today_start = at_index - 60
    fvg = next(
        (f for f in reversed(fvgs)
         if today_start <= f.created_at_index <= at_index
         and _fvg_alive_at(f, at_index)
         and f.type == f"{side}_fvg"),
        None
    )
    if not fvg:
        return None

    a = _atr_at(atr_series, at_index)
    if a <= 0:
        return None

    entry = (fvg.top + fvg.bottom) / 2
    if direction == "long":
        stop = fvg.bottom - C.SL_ATR_BUFFER * a
    else:
        stop = fvg.top + C.SL_ATR_BUFFER * a
    stop = _floor_stop(entry, stop, direction, a)

    tp1 = _next_opposite_liquidity(entry, direction, liquidity_levels, at_index)
    tp1 = _cap_tp(entry, tp1, direction, a)
    tp2 = _next_persistent_liquidity(entry, direction, liquidity_levels, at_index)
    if tp1 is None:
        return None
    rr1 = _rr(entry, stop, tp1, direction)
    if rr1 < C.MIN_RR_SILVER_BULLET:
        return None
    rr2 = _rr(entry, stop, tp2, direction) if tp2 is not None else None

    return Signal(
        signal_id=str(uuid.uuid4()),
        timestamp=ts,
        strategy="D_silver_bullet",
        symbol=symbol,
        direction=direction,
        entry=float(entry),
        stop_loss=float(stop),
        take_profit_1=float(tp1),
        take_profit_2=float(tp2) if tp2 is not None else None,
        risk_reward_1=float(rr1),
        risk_reward_2=float(rr2) if rr2 is not None else None,
        quality="high",
        confluence_factors=["htf_aligned", "liquidity_swept", "silver_bullet", "in_killzone"],
        context={"htf_bias": bias, "killzone": killzone_at(ts), "sweep_type": sweep.type},
        expires_at_index=_expiry(at_index, expiry_bars),
        bar_index=at_index,
    )


# ----------------------------- Strategy E: EQH/EQL Liquidity Run -----------------------------

def strategy_e(symbol: str,
               df: pd.DataFrame,
               at_index: int,
               atr_series: pd.Series,
               structure_events: list[StructureEvent],
               liquidity_levels: list[LiquidityLevel],
               obs: list[OrderBlock],
               fvgs: list[FVG],
               htf_bias_series: Optional[pd.Series] = None,
               expiry_bars: Optional[int] = None) -> Optional[Signal]:
    ts = df.index[at_index]
    if not in_killzones(ts, ["london_open", "ny_open"]):
        return None

    bias = _resolve_bias(structure_events, at_index, htf_bias_series)
    if bias == "range":
        return None

    eq_recent = [
        l for l in liquidity_levels
        if l.type in ("EQH", "EQL") and l.swept and l.swept_at_index is not None
        and at_index - 3 <= l.swept_at_index <= at_index
    ]
    if not eq_recent:
        return None
    swept = eq_recent[-1]

    direction = "short" if swept.type == "EQH" else "long"
    if (direction == "long" and bias != "bullish") or (direction == "short" and bias != "bearish"):
        return None

    side = "bullish" if direction == "long" else "bearish"
    impulse_range = range(swept.swept_at_index, at_index + 1)
    candidate_obs = [
        o for o in obs
        if o.created_at_index in impulse_range
        and _ob_alive_at(o, at_index) and o.type == f"{side}_ob"
    ]
    candidate_fvgs = [
        f for f in fvgs
        if f.created_at_index in impulse_range
        and _fvg_alive_at(f, at_index) and f.type == f"{side}_fvg"
    ]
    if not candidate_obs and not candidate_fvgs:
        return None

    if candidate_obs:
        zone_top, zone_bottom = candidate_obs[-1].top, candidate_obs[-1].bottom
    else:
        zone_top, zone_bottom = candidate_fvgs[-1].top, candidate_fvgs[-1].bottom

    entry = (zone_top + zone_bottom) / 2
    a = _atr_at(atr_series, at_index)
    if a <= 0:
        return None

    if direction == "long":
        stop = swept.sweep_extreme - C.SL_ATR_BUFFER * a
    else:
        stop = swept.sweep_extreme + C.SL_ATR_BUFFER * a
    stop = _floor_stop(entry, stop, direction, a)

    tp1 = _next_opposite_liquidity(entry, direction, liquidity_levels, at_index)
    tp1 = _cap_tp(entry, tp1, direction, a)
    tp2 = _next_persistent_liquidity(entry, direction, liquidity_levels, at_index)
    if tp1 is None:
        return None
    rr1 = _rr(entry, stop, tp1, direction)
    if rr1 < C.MIN_RR_DEFAULT:
        return None
    rr2 = _rr(entry, stop, tp2, direction) if tp2 is not None else None

    return Signal(
        signal_id=str(uuid.uuid4()),
        timestamp=ts,
        strategy="E_eqh_eql_run",
        symbol=symbol,
        direction=direction,
        entry=float(entry),
        stop_loss=float(stop),
        take_profit_1=float(tp1),
        take_profit_2=float(tp2) if tp2 is not None else None,
        risk_reward_1=float(rr1),
        risk_reward_2=float(rr2) if rr2 is not None else None,
        quality="medium",
        confluence_factors=["htf_aligned", "eqh_eql_swept", "in_killzone"],
        context={"htf_bias": bias, "killzone": killzone_at(ts), "swept": swept.type},
        expires_at_index=_expiry(at_index, expiry_bars),
        bar_index=at_index,
    )


STRATEGIES = [strategy_a, strategy_b, strategy_c, strategy_d, strategy_e]
