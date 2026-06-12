"""'Eth Burak' style pure price-action strategy set (experimental stream, no DB writes).

Codifies the publicly described method of the Turkish PA trader "Eth Burak":
  - 1H macro chart, no indicators (ATR is used ONLY for buffers/floors, not signals).
  - RANGE_DEV  (ana strateji): draw a range (high/low/EQ); a DEVIATION = price pokes
    outside the range and closes back inside -> fade it, target the opposite side.
  - OB_PULLBACK: last opposite candle before an impulsive structure-breaking move;
    enter on the pullback to the block's mid ("esneklik payi").
  - IC_RETEST : indecision candle (tiny opposite-color bar sandwiched between two
    strong same-direction bars); enter on the return to the IC zone, with trend.
  - FVG_TREND : 3-bar imbalance aligned with the trend; enter at the gap midpoint.

Trade management (his actual edge, modelled by the repo's partial-TP machinery):
  - scale out 50% at 50% of entry->TP distance (~EQ for range trades) and pull the
    stop to breakeven (ict/config PARTIAL_TP_*  — flipped on by the runner).
  - modest targets: structural target (opposite range end / recent swing), capped at
    3R and floored at 1.5R (signals below 1.5R are skipped) — "ucuk hedefler yok".

NOTE: his exact mechanical parameters are not public (videos/paid platform only);
the thresholds below are this repo's codification of the publicly described rules.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# ----------------------------------------------------------------- parameters
ATR_LEN = 14

# Range + deviation (ana strateji)
RANGE_WINDOW = 96          # bars (1h) the range must be established over (~4 days)
DEV_GAP = 12               # most recent bars allowed to hold the deviation leg
RANGE_MIN_ATR = 2.5        # range width floor (in ATR) — needs room to trade
RANGE_MAX_ATR = 12.0       # width cap — wider = not a tradable range
TOUCH_BAND_FRAC = 0.15     # boundary touch band = 15% of range width
MIN_TOUCHES = 2            # per side, distinct touch clusters
MIN_EQ_CROSSES = 3         # closes must recross EQ — filters trend channels
DEV_MIN_POKE_ATR = 0.25    # deviation must exceed boundary by >= 0.25 ATR
DEV_MAX_FRAC = 0.5         # ...but by <= 50% of width (further = real breakout)
OPP_SIDE_TOL_ATR = 0.25    # opposite boundary must hold during the deviation leg

# Zone strategies (OB / IC / FVG)
STRONG_BODY_ATR = 0.7      # 'strong candle' body floor for IC
IC_BODY_FRAC = 0.35        # IC body <= 35% of the smaller neighbour body
FVG_MIN_GAP_ATR = 0.3
FVG_DISPL_BODY_ATR = 1.0   # displacement candle body floor
OB_IMPULSE_ATR = 1.8       # net 4-bar move that qualifies as the impulse leg
OB_LOOKBACK = 8            # bars to scan back for the last opposite candle
TARGET_LOOKBACK = 50       # structural target = recent extreme over this window
PIVOT_K = 3                # fractal pivots, confirmed K bars later

# Risk / reward discipline ("muhendis gibi")
RR_FLOOR = 1.5
RR_CAP = 3.0
SL_BUF_ATR = 0.2           # stop buffer beyond the invalidation extreme
MIN_SL_DIST_PCT = 0.0015   # SL floor: max(0.15% of entry, 0.5 ATR)
MIN_SL_DIST_ATR = 0.5

COOLDOWN_BARS = 24         # per strategy+direction re-fire suppression
DEDUP_PCT = 0.001          # global: same direction, entry within 0.1% & 24h = dup

EXPIRY_FAST_MIN = 180      # RANGE_DEV enters at market (confirm-bar close)
EXPIRY_ZONE_MIN = 6000     # resting limit at a zone may wait ~100 bars for the pullback


@dataclass
class BurakSignal:
    timestamp: pd.Timestamp        # bar OPEN time (fires at close = ts + 1h)
    direction: str                 # "LONG" / "SHORT"
    entry: float
    stop_loss: float
    take_profit_1: float
    strategy: str
    quality: str
    confluence_score: int
    expiry_minutes: int
    meta: dict = field(default_factory=dict)


# ----------------------------------------------------------------- helpers
def _atr(df: pd.DataFrame, n: int = ATR_LEN) -> np.ndarray:
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).rolling(n, min_periods=n).mean().values


def _touch_clusters(vals: np.ndarray, band_lo: float, band_hi: float) -> int:
    """Count distinct visits into [band_lo, band_hi] (consecutive bars = one touch)."""
    inside = (vals >= band_lo) & (vals <= band_hi)
    return int(np.sum(inside[1:] & ~inside[:-1]) + (1 if inside[0] else 0))


def _floor_risk(entry: float, sl: float, atr: float, long: bool) -> float:
    """Push the stop out to the floor distance if it sits closer than the spread allows."""
    floor = max(MIN_SL_DIST_PCT * entry, MIN_SL_DIST_ATR * atr)
    risk = abs(entry - sl)
    if risk < floor:
        sl = entry - floor if long else entry + floor
    return sl


def _gate_rr(entry: float, sl: float, target: float, long: bool):
    """Apply the 1.5R floor / 3R cap. Returns the final TP or None (signal skipped)."""
    risk = abs(entry - sl)
    if risk <= 0:
        return None
    reward = (target - entry) if long else (entry - target)
    rr = reward / risk
    if rr < RR_FLOOR:
        return None
    if rr > RR_CAP:
        return entry + RR_CAP * risk if long else entry - RR_CAP * risk
    return target


# ----------------------------------------------------------------- generator
def generate_signals(df: pd.DataFrame) -> list[BurakSignal]:
    """Walk the 1h frame bar by bar (no lookahead) and emit Burak-style signals."""
    n = len(df)
    if n < RANGE_WINDOW + DEV_GAP + ATR_LEN + 10:
        return []
    o = df["open"].values; h = df["high"].values
    l = df["low"].values;  c = df["close"].values
    body = np.abs(c - o)
    atr = _atr(df)
    idx = df.index

    # fractal pivots (confirmed PIVOT_K bars later)
    piv_hi: list[tuple[int, float]] = []   # (bar, price), confirmed only
    piv_lo: list[tuple[int, float]] = []
    is_ph = np.zeros(n, bool); is_pl = np.zeros(n, bool)
    for p in range(PIVOT_K, n - PIVOT_K):
        seg_h = h[p - PIVOT_K:p + PIVOT_K + 1]
        seg_l = l[p - PIVOT_K:p + PIVOT_K + 1]
        if h[p] == seg_h.max() and (seg_h == h[p]).sum() == 1:
            is_ph[p] = True
        if l[p] == seg_l.min() and (seg_l == l[p]).sum() == 1:
            is_pl[p] = True

    def trend() -> str:
        if len(piv_hi) < 2 or len(piv_lo) < 2:
            return "none"
        hh = piv_hi[-1][1] > piv_hi[-2][1]; hl = piv_lo[-1][1] > piv_lo[-2][1]
        if hh and hl:
            return "up"
        if (not hh) and (not hl):
            return "down"
        return "none"

    signals: list[BurakSignal] = []
    cooldown: dict[tuple[str, str], int] = {}   # (strategy, dir) -> last bar fired

    def on_cooldown(strat: str, d: str, i: int) -> bool:
        return i - cooldown.get((strat, d), -10**9) < COOLDOWN_BARS

    def emit(i, d, entry, sl, target, strat, qual, score, expiry, meta):
        long = d == "LONG"
        sl = _floor_risk(entry, sl, atr[i], long)
        tp = _gate_rr(entry, sl, target, long)
        if tp is None:
            return
        cooldown[(strat, d)] = i
        signals.append(BurakSignal(idx[i], d, float(entry), float(sl), float(tp),
                                   strat, qual, score, expiry, meta))

    start = max(RANGE_WINDOW + DEV_GAP, ATR_LEN + 1)
    for i in range(start, n):
        # confirm pivots up to i (pivot at p is known at p + PIVOT_K)
        p = i - PIVOT_K
        if p >= 0:
            if is_ph[p]:
                piv_hi.append((p, h[p]))
            if is_pl[p]:
                piv_lo.append((p, l[p]))
        if np.isnan(atr[i]) or atr[i] <= 0:
            continue
        a = atr[i]
        tr = trend()

        # ---------------- RANGE_DEV (ana strateji): fade the deviation -------------
        e0, e1 = i - DEV_GAP - RANGE_WINDOW + 1, i - DEV_GAP   # establishment window
        rng_hi = h[e0:e1 + 1].max(); rng_lo = l[e0:e1 + 1].min()
        width = rng_hi - rng_lo
        eq = (rng_hi + rng_lo) / 2.0
        if RANGE_MIN_ATR * a <= width <= RANGE_MAX_ATR * a:
            band = TOUCH_BAND_FRAC * width
            est_h, est_l, est_c = h[e0:e1 + 1], l[e0:e1 + 1], c[e0:e1 + 1]
            touches_top = _touch_clusters(est_h, rng_hi - band, np.inf)
            touches_bot = _touch_clusters(-est_l, -(rng_lo + band), np.inf)
            eq_cross = int(np.sum(np.diff(np.sign(est_c - eq)) != 0))
            if touches_top >= MIN_TOUCHES and touches_bot >= MIN_TOUCHES and eq_cross >= MIN_EQ_CROSSES:
                dv_h, dv_l, dv_c = h[e1 + 1:i + 1], l[e1 + 1:i + 1], c[e1 + 1:i + 1]
                # SHORT: poke above range high, close back inside
                if not on_cooldown("RANGE_DEV", "SHORT", i):
                    dev_ext = dv_h.max() if len(dv_h) else -np.inf
                    reclaim = (h[i] > rng_hi or c[i - 1] > rng_hi) and rng_lo < c[i] < rng_hi
                    opp_ok = (dv_l.min() if len(dv_l) else np.inf) > rng_lo - OPP_SIDE_TOL_ATR * a
                    if (reclaim and opp_ok
                            and rng_hi + DEV_MIN_POKE_ATR * a <= dev_ext <= rng_hi + DEV_MAX_FRAC * width):
                        swept = any(ph > rng_hi and ph <= dev_ext for _, ph in piv_hi[-5:])
                        emit(i, "SHORT", c[i], dev_ext + SL_BUF_ATR * a, rng_lo,
                             "RANGE_DEV", "high", 8 + int(swept), EXPIRY_FAST_MIN,
                             {"rng_hi": rng_hi, "rng_lo": rng_lo, "eq": eq, "dev_ext": dev_ext})
                # LONG: poke below range low, close back inside
                if not on_cooldown("RANGE_DEV", "LONG", i):
                    dev_ext = dv_l.min() if len(dv_l) else np.inf
                    reclaim = (l[i] < rng_lo or c[i - 1] < rng_lo) and rng_lo < c[i] < rng_hi
                    opp_ok = (dv_h.max() if len(dv_h) else -np.inf) < rng_hi + OPP_SIDE_TOL_ATR * a
                    if (reclaim and opp_ok
                            and rng_lo - DEV_MAX_FRAC * width <= dev_ext <= rng_lo - DEV_MIN_POKE_ATR * a):
                        swept = any(pl < rng_lo and pl >= dev_ext for _, pl in piv_lo[-5:])
                        emit(i, "LONG", c[i], dev_ext - SL_BUF_ATR * a, rng_hi,
                             "RANGE_DEV", "high", 8 + int(swept), EXPIRY_FAST_MIN,
                             {"rng_hi": rng_hi, "rng_lo": rng_lo, "eq": eq, "dev_ext": dev_ext})

        if i < TARGET_LOOKBACK:
            continue
        tgt_hi = h[i - TARGET_LOOKBACK + 1:i + 1].max()   # structural targets
        tgt_lo = l[i - TARGET_LOOKBACK + 1:i + 1].min()

        # ---------------- IC_RETEST: indecision candle, with trend ----------------
        b1, b2, b3 = body[i - 2], body[i - 1], body[i]
        if b1 >= STRONG_BODY_ATR * a and b3 >= STRONG_BODY_ATR * a and b2 <= IC_BODY_FRAC * min(b1, b3):
            zone_mid = (h[i - 1] + l[i - 1]) / 2.0
            if (tr == "up" and c[i - 2] > o[i - 2] and c[i] > o[i] and c[i] > h[i - 2]
                    and not on_cooldown("IC_RETEST", "LONG", i)):
                emit(i, "LONG", zone_mid, l[i - 1] - SL_BUF_ATR * a, tgt_hi,
                     "IC_RETEST", "medium", 6, EXPIRY_ZONE_MIN, {"ic_bar": str(idx[i - 1])})
            if (tr == "down" and c[i - 2] < o[i - 2] and c[i] < o[i] and c[i] < l[i - 2]
                    and not on_cooldown("IC_RETEST", "SHORT", i)):
                emit(i, "SHORT", zone_mid, h[i - 1] + SL_BUF_ATR * a, tgt_lo,
                     "IC_RETEST", "medium", 6, EXPIRY_ZONE_MIN, {"ic_bar": str(idx[i - 1])})

        # ---------------- FVG_TREND: 3-bar imbalance, with trend -------------------
        if body[i - 1] >= FVG_DISPL_BODY_ATR * a:
            if (tr == "up" and l[i] > h[i - 2] and l[i] - h[i - 2] >= FVG_MIN_GAP_ATR * a
                    and not on_cooldown("FVG_TREND", "LONG", i)):
                gap_b, gap_t = h[i - 2], l[i]
                emit(i, "LONG", (gap_b + gap_t) / 2.0, gap_b - SL_BUF_ATR * a, tgt_hi,
                     "FVG_TREND", "medium", 6, EXPIRY_ZONE_MIN, {"gap": (gap_b, gap_t)})
            if (tr == "down" and h[i] < l[i - 2] and l[i - 2] - h[i] >= FVG_MIN_GAP_ATR * a
                    and not on_cooldown("FVG_TREND", "SHORT", i)):
                gap_b, gap_t = h[i], l[i - 2]
                emit(i, "SHORT", (gap_b + gap_t) / 2.0, gap_t + SL_BUF_ATR * a, tgt_lo,
                     "FVG_TREND", "medium", 6, EXPIRY_ZONE_MIN, {"gap": (gap_b, gap_t)})

        # ---------------- OB_PULLBACK: impulse + structure break -------------------
        if tr == "up" and c[i] - o[i - 3] >= OB_IMPULSE_ATR * a and piv_hi \
                and h[i] > piv_hi[-1][1] and not on_cooldown("OB_PULLBACK", "LONG", i):
            for k in range(i - 1, max(i - 1 - OB_LOOKBACK, 0), -1):
                if c[k] < o[k]:                       # last bearish candle = the OB
                    entry = (h[k] + l[k]) / 2.0
                    if entry < c[i] - 0.3 * a:        # zone genuinely below price
                        emit(i, "LONG", entry, l[k] - SL_BUF_ATR * a, tgt_hi,
                             "OB_PULLBACK", "medium", 7, EXPIRY_ZONE_MIN, {"ob_bar": str(idx[k])})
                    break
        if tr == "down" and o[i - 3] - c[i] >= OB_IMPULSE_ATR * a and piv_lo \
                and l[i] < piv_lo[-1][1] and not on_cooldown("OB_PULLBACK", "SHORT", i):
            for k in range(i - 1, max(i - 1 - OB_LOOKBACK, 0), -1):
                if c[k] > o[k]:                       # last bullish candle = the OB
                    entry = (h[k] + l[k]) / 2.0
                    if entry > c[i] + 0.3 * a:
                        emit(i, "SHORT", entry, h[k] + SL_BUF_ATR * a, tgt_lo,
                             "OB_PULLBACK", "medium", 7, EXPIRY_ZONE_MIN, {"ob_bar": str(idx[k])})
                    break

    # global dedup: same direction, entry within 0.1%, within 24h -> keep the first
    out: list[BurakSignal] = []
    for s in signals:
        dup = any(k.direction == s.direction
                  and abs(k.entry - s.entry) / s.entry <= DEDUP_PCT
                  and (s.timestamp - k.timestamp) <= pd.Timedelta(hours=24)
                  for k in out)
        if not dup:
            out.append(s)
    return out
