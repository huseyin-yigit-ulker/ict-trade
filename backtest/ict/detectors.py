"""ICT detector library.

All detectors are pure functions: input is a closed-bar OHLCV DataFrame,
output is a list of dataclass records. No look-ahead: a record at index i
only references information from bars [0..i].
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from . import config as C


# ----------------------------- dataclasses -----------------------------

@dataclass
class Swing:
    type: str             # "swing_high" | "swing_low"
    index: int
    timestamp: pd.Timestamp
    price: float
    confirmed_at: int     # bar index where it became confirmable (index + N)


@dataclass
class StructureEvent:
    type: str             # "BOS" | "CHoCH"
    direction: str        # "bullish" | "bearish"
    broken_level: float
    broken_at_index: int
    broken_at_ts: pd.Timestamp
    trend_before: str
    trend_after: str


@dataclass
class LiquidityLevel:
    type: str             # PDH/PDL/PWH/PWL/EQH/EQL
    level: float
    created_at_index: int
    swept: bool = False
    swept_at_index: Optional[int] = None
    sweep_extreme: Optional[float] = None  # the wick extreme when sweep happened


@dataclass
class OrderBlock:
    type: str             # bullish_ob | bearish_ob
    top: float
    bottom: float
    created_at_index: int           # bar index of the OB body itself
    impulse_size_atr: float
    confirmed_at_index: int = 0     # bar index where the impulse confirmed the OB
                                    # (real-time visibility threshold)
    mitigated: bool = False
    mitigation_index: Optional[int] = None


@dataclass
class FVG:
    type: str             # bullish_fvg | bearish_fvg
    top: float
    bottom: float
    created_at_index: int
    fill_status: str = "open"
    fill_pct: float = 0.0
    filled_at_index: Optional[int] = None      # bar index where fill_status became "filled"
    partial_at_index: Optional[int] = None     # first bar a partial penetration occurred


# ----------------------------- swings -----------------------------

def detect_swings(df: pd.DataFrame, n: int = C.SWING_N_ITF) -> list[Swing]:
    """Fractal swings: a bar is a swing iff it's the strict high/low of the +/- n window.

    A swing at index i is only `confirmed_at` index i+n (visible after n bars).
    """
    out: list[Swing] = []
    high = df["high"].values
    low = df["low"].values
    idx = df.index
    for i in range(n, len(df) - n):
        win_h = high[i - n:i + n + 1]
        win_l = low[i - n:i + n + 1]
        if high[i] == win_h.max() and (win_h == high[i]).sum() == 1:
            out.append(Swing("swing_high", i, idx[i], float(high[i]), i + n))
        if low[i] == win_l.min() and (win_l == low[i]).sum() == 1:
            out.append(Swing("swing_low", i, idx[i], float(low[i]), i + n))
    return out


# ----------------------------- structure (BOS / CHoCH) -----------------------------

def detect_structure(df: pd.DataFrame, swings: list[Swing]) -> list[StructureEvent]:
    """Walk closes and emit BOS/CHoCH against the most recent confirmed swings."""
    if not swings:
        return []

    swings_sorted = sorted(swings, key=lambda s: s.confirmed_at)
    closes = df["close"].values
    idx = df.index
    events: list[StructureEvent] = []
    trend = "range"
    last_high: Optional[Swing] = None
    last_low: Optional[Swing] = None
    s_pos = 0

    for i in range(len(df)):
        while s_pos < len(swings_sorted) and swings_sorted[s_pos].confirmed_at <= i:
            sw = swings_sorted[s_pos]
            if sw.type == "swing_high":
                last_high = sw
            else:
                last_low = sw
            s_pos += 1

        c = closes[i]
        if last_high and c > last_high.price:
            new_trend = "up"
            evt_type = "BOS" if trend == "up" else "CHoCH"
            events.append(StructureEvent(evt_type, "bullish", last_high.price, i, idx[i], trend, new_trend))
            trend = new_trend
            last_high = None  # consume; wait for next confirmed swing high
        elif last_low and c < last_low.price:
            new_trend = "down"
            evt_type = "BOS" if trend == "down" else "CHoCH"
            events.append(StructureEvent(evt_type, "bearish", last_low.price, i, idx[i], trend, new_trend))
            trend = new_trend
            last_low = None

    return events


def htf_bias(structure_events: list[StructureEvent], at_index: int) -> str:
    """Return 'bullish' / 'bearish' / 'range' based on the most recent BOS/CHoCH at or before at_index."""
    last = None
    for e in structure_events:
        if e.broken_at_index > at_index:
            break
        last = e
    if not last:
        return "range"
    return "bullish" if last.trend_after == "up" else ("bearish" if last.trend_after == "down" else "range")


# ----------------------------- liquidity -----------------------------

def _level_tolerance(price: float, atr_value: float) -> float:
    return max(C.EQUAL_LEVEL_TOL_PCT * price, C.EQUAL_LEVEL_TOL_ATR * atr_value)


def detect_persistent_liquidity(df: pd.DataFrame) -> list[LiquidityLevel]:
    """Previous Day/Week High & Low (PDH/PDL/PWH/PWL).

    Daily levels are emitted at first bar of each new UTC day; weekly at first bar of new UTC week.
    """
    out: list[LiquidityLevel] = []
    if df.empty:
        return out

    daily = df.resample("1D").agg({"high": "max", "low": "min"}).dropna()
    weekly = df.resample("1W").agg({"high": "max", "low": "min"}).dropna()

    daily_by_date = {ts.date(): row for ts, row in daily.iterrows()}
    weekly_by_iso = {(ts.isocalendar().year, ts.isocalendar().week): row for ts, row in weekly.iterrows()}

    seen_day = None
    seen_week = None
    prev_day_row = None
    prev_week_row = None

    for i in range(len(df)):
        ts = df.index[i]
        d = ts.date()
        iso = ts.isocalendar()
        w = (iso.year, iso.week)

        if d != seen_day:
            if prev_day_row is not None:
                out.append(LiquidityLevel("PDH", float(prev_day_row["high"]), i))
                out.append(LiquidityLevel("PDL", float(prev_day_row["low"]), i))
            if d in daily_by_date:
                prev_day_row = daily_by_date[d]
            seen_day = d

        if w != seen_week:
            if prev_week_row is not None:
                out.append(LiquidityLevel("PWH", float(prev_week_row["high"]), i))
                out.append(LiquidityLevel("PWL", float(prev_week_row["low"]), i))
            if w in weekly_by_iso:
                prev_week_row = weekly_by_iso[w]
            seen_week = w

    return out


def detect_equal_levels(swings: list[Swing], atr_series: pd.Series) -> list[LiquidityLevel]:
    """Mark EQH/EQL where two consecutive same-type swings sit within tolerance."""
    out: list[LiquidityLevel] = []
    highs = [s for s in swings if s.type == "swing_high"]
    lows = [s for s in swings if s.type == "swing_low"]

    for i in range(1, len(highs)):
        a, b = highs[i - 1], highs[i]
        a_atr = float(atr_series.iloc[a.index]) if not pd.isna(atr_series.iloc[a.index]) else 0
        if abs(a.price - b.price) <= _level_tolerance(b.price, a_atr):
            level = (a.price + b.price) / 2
            out.append(LiquidityLevel("EQH", level, b.confirmed_at))

    for i in range(1, len(lows)):
        a, b = lows[i - 1], lows[i]
        a_atr = float(atr_series.iloc[a.index]) if not pd.isna(atr_series.iloc[a.index]) else 0
        if abs(a.price - b.price) <= _level_tolerance(b.price, a_atr):
            level = (a.price + b.price) / 2
            out.append(LiquidityLevel("EQL", level, b.confirmed_at))

    return out


def mark_sweeps(df: pd.DataFrame, levels: list[LiquidityLevel]) -> None:
    """In-place: mark `swept`, `swept_at_index`, `sweep_extreme` for each level."""
    high = df["high"].values
    low = df["low"].values
    close = df["close"].values

    for lvl in levels:
        if lvl.swept:
            continue
        for i in range(lvl.created_at_index, len(df)):
            is_high_level = lvl.type in ("PDH", "PWH", "EQH")
            if is_high_level:
                if high[i] > lvl.level and close[i] < lvl.level:
                    lvl.swept = True
                    lvl.swept_at_index = i
                    lvl.sweep_extreme = float(high[i])
                    break
            else:
                if low[i] < lvl.level and close[i] > lvl.level:
                    lvl.swept = True
                    lvl.swept_at_index = i
                    lvl.sweep_extreme = float(low[i])
                    break


# ----------------------------- order blocks -----------------------------

def _is_impulse(df: pd.DataFrame, start: int, end: int, atr_value: float) -> Optional[str]:
    """Return 'bullish'/'bearish' if [start..end] is an impulse, else None."""
    if end <= start or atr_value <= 0:
        return None
    move = df["close"].iloc[end] - df["close"].iloc[start]
    if abs(move) >= C.IMPULSE_ATR_MULT * atr_value:
        return "bullish" if move > 0 else "bearish"
    # consecutive same-direction bars
    direction = None
    streak = 0
    for i in range(start + 1, end + 1):
        d = "bullish" if df["close"].iloc[i] > df["open"].iloc[i] else "bearish"
        if d == direction:
            streak += 1
        else:
            direction = d
            streak = 1
        if streak >= C.IMPULSE_CONSEC_BARS:
            return direction
    return None


def detect_order_blocks(df: pd.DataFrame, atr_series: pd.Series) -> list[OrderBlock]:
    """Scan for impulses and tag the last opposite-direction body as OB."""
    out: list[OrderBlock] = []
    n = len(df)
    o = df["open"].values
    c = df["close"].values

    i = C.IMPULSE_BAR_WINDOW
    while i < n:
        a_val = atr_series.iloc[i] if not pd.isna(atr_series.iloc[i]) else 0
        impulse = _is_impulse(df, i - C.IMPULSE_BAR_WINDOW, i, float(a_val))
        if impulse:
            # walk back to find last opposite candle
            base_dir = "bullish" if impulse == "bearish" else "bearish"
            ob_idx = None
            for j in range(i - 1, max(i - C.IMPULSE_BAR_WINDOW - 5, -1), -1):
                bar_dir = "bullish" if c[j] > o[j] else "bearish"
                if bar_dir == base_dir:
                    ob_idx = j
                    break
            if ob_idx is not None:
                top = max(o[ob_idx], c[ob_idx])
                bot = min(o[ob_idx], c[ob_idx])
                ob_type = "bullish_ob" if impulse == "bullish" else "bearish_ob"
                out.append(OrderBlock(
                    ob_type, float(top), float(bot), ob_idx,
                    abs(c[i] - c[i - C.IMPULSE_BAR_WINDOW]) / max(float(a_val), 1e-9),
                    confirmed_at_index=i,  # OB only "exists" once impulse confirms at bar i
                ))
            i += C.IMPULSE_BAR_WINDOW  # skip ahead so we don't double-count
        else:
            i += 1

    _mark_ob_mitigation(df, out)
    return out


def _mark_ob_mitigation(df: pd.DataFrame, obs: list[OrderBlock]) -> None:
    """An OB is only 'mitigated' once price has moved at least one body-height away
    and then returned. The previous logic triggered immediately on the impulse bar
    that *created* the OB, leaving 0 valid OBs for downstream strategies."""
    high = df["high"].values
    low = df["low"].values
    for ob in obs:
        body = max(ob.top - ob.bottom, 1e-9)
        moved_away = False
        for i in range(ob.created_at_index + 1, len(df)):
            if ob.type == "bullish_ob":
                if not moved_away:
                    if low[i] > ob.top + body:
                        moved_away = True
                    continue
                if low[i] <= ob.top:
                    ob.mitigated = True
                    ob.mitigation_index = i
                    break
            else:
                if not moved_away:
                    if high[i] < ob.bottom - body:
                        moved_away = True
                    continue
                if high[i] >= ob.bottom:
                    ob.mitigated = True
                    ob.mitigation_index = i
                    break


# ----------------------------- FVG -----------------------------

def detect_fvgs(df: pd.DataFrame) -> list[FVG]:
    """Three-bar fair value gap detection."""
    out: list[FVG] = []
    high = df["high"].values
    low = df["low"].values
    for i in range(1, len(df) - 1):
        # bullish: gap between bar[i-1].high and bar[i+1].low
        if low[i + 1] > high[i - 1]:
            out.append(FVG("bullish_fvg", float(low[i + 1]), float(high[i - 1]), i + 1))
        # bearish
        if high[i + 1] < low[i - 1]:
            out.append(FVG("bearish_fvg", float(low[i - 1]), float(high[i + 1]), i + 1))

    _update_fvg_fill(df, out)
    return out


def _update_fvg_fill(df: pd.DataFrame, fvgs: list[FVG]) -> None:
    """Pre-compute fill events. Both `filled_at_index` and `partial_at_index`
    are stored so strategies can ask 'was this filled by bar X?' without
    look-ahead bias."""
    high = df["high"].values
    low = df["low"].values
    for fvg in fvgs:
        size = max(fvg.top - fvg.bottom, 1e-9)
        for i in range(fvg.created_at_index + 1, len(df)):
            if fvg.type == "bullish_fvg":
                if low[i] <= fvg.bottom:
                    fvg.fill_status = "filled"
                    fvg.fill_pct = 1.0
                    fvg.filled_at_index = i
                    break
                if low[i] < fvg.top:
                    pen = (fvg.top - low[i]) / size
                    if pen > fvg.fill_pct:
                        fvg.fill_pct = float(pen)
                        fvg.fill_status = "partial"
                        if fvg.partial_at_index is None:
                            fvg.partial_at_index = i
            else:
                if high[i] >= fvg.top:
                    fvg.fill_status = "filled"
                    fvg.fill_pct = 1.0
                    fvg.filled_at_index = i
                    break
                if high[i] > fvg.bottom:
                    pen = (high[i] - fvg.bottom) / size
                    if pen > fvg.fill_pct:
                        fvg.fill_pct = float(pen)
                        fvg.fill_status = "partial"
                        if fvg.partial_at_index is None:
                            fvg.partial_at_index = i


# ----------------------------- killzone clock -----------------------------

def killzone_at(ts: pd.Timestamp) -> list[str]:
    """Return list of killzone names active at `ts` (timezone-aware UTC)."""
    if ts.tz is None:
        ts = ts.tz_localize("UTC")
    ny = ts.tz_convert(C.NY_TZ)
    h = ny.hour
    active = []
    for name, (start_h, end_h) in C.KILLZONES_NY.items():
        if start_h <= end_h:
            if start_h <= h < end_h:
                active.append(name)
        else:
            if h >= start_h or h < end_h:
                active.append(name)
    return active


def in_killzones(ts: pd.Timestamp, names: list[str]) -> bool:
    active = killzone_at(ts)
    return any(n in active for n in names)


# ----------------------------- premium / discount / OTE -----------------------------

@dataclass
class PDZone:
    high: float
    low: float

    @property
    def equilibrium(self) -> float:
        return (self.high + self.low) / 2

    def is_premium(self, price: float) -> bool:
        return price >= self.equilibrium

    def is_discount(self, price: float) -> bool:
        return price <= self.equilibrium

    def ote(self, direction: str) -> tuple[float, float]:
        """Return (low, high) of OTE retracement zone for a leg of `direction`."""
        size = self.high - self.low
        if direction == "bullish":
            return (self.high - C.OTE_HIGH * size, self.high - C.OTE_LOW * size)
        return (self.low + C.OTE_LOW * size, self.low + C.OTE_HIGH * size)


def in_ote(zone: PDZone, price: float, direction: str) -> bool:
    lo, hi = zone.ote(direction)
    return lo <= price <= hi
