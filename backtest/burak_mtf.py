"""'Eth Burak' strategy set with MULTI-TIMEFRAME confirmation (4h -> 1h -> 15m).

Cascade (no trade without all three aligning):
  4H  context : the range (RANGE_DEV) / pivot-structure trend (zone strategies)
  1H  setup   : deviation + close back inside the range  /  OB-IC-FVG zone forms
  15M trigger : structure break in the trade direction (RANGE_DEV) or a rejection
                candle at the zone (close above the previous 15m high for longs)
                — only then is the signal emitted, at the 15m close (market-style).

Same risk discipline and management as backtest/burak_strategy.py (RR 1.5..3,
SL beyond the invalidation extreme + buffer, partial-TP at ~EQ + breakeven via the
runner). Walk-forward: every decision uses only COMPLETED bars of each timeframe.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from burak_strategy import (
    BurakSignal, _atr, _floor_risk, _gate_rr, _touch_clusters,
    RANGE_WINDOW, DEV_GAP,
    RANGE_MIN_ATR, RANGE_MAX_ATR, TOUCH_BAND_FRAC, MIN_TOUCHES, MIN_EQ_CROSSES,
    DEV_MIN_POKE_ATR, DEV_MAX_FRAC, OPP_SIDE_TOL_ATR,
    STRONG_BODY_ATR, IC_BODY_FRAC, FVG_MIN_GAP_ATR, FVG_DISPL_BODY_ATR,
    OB_IMPULSE_ATR, OB_LOOKBACK, TARGET_LOOKBACK, PIVOT_K, SL_BUF_ATR, DEDUP_PCT,
)

# --- MTF parameters ---------------------------------------------------------
RANGE_WINDOW_4H = 90        # range established over 90 completed 4h bars (~15 days)
DEV_GAP_4H = 3              # ...ending 3 bars back (the deviation leg lives here)
ARM_BARS_1H = 12            # a reclaimed deviation stays armed for 12 x 1h
ZONE_MAX_AGE_1H = 100       # zones expire after 100 x 1h
TRIG_LOOKBACK_15 = 3        # 15m structure break = close beyond prior 3-bar extreme
ZONE_NEAR_ATR = 0.5         # trigger must close within zone edge + 0.5 ATR(1h)
COOLDOWN_15 = 96            # 24h re-fire suppression per strategy+direction
EXPIRY_MIN = 180            # market-style entries: fill within 3h or cancel


def _pivots(h: np.ndarray, l: np.ndarray, k: int = PIVOT_K):
    n = len(h)
    is_ph = np.zeros(n, bool); is_pl = np.zeros(n, bool)
    for p in range(k, n - k):
        seg_h = h[p - k:p + k + 1]; seg_l = l[p - k:p + k + 1]
        if h[p] == seg_h.max() and (seg_h == h[p]).sum() == 1:
            is_ph[p] = True
        if l[p] == seg_l.min() and (seg_l == l[p]).sum() == 1:
            is_pl[p] = True
    return is_ph, is_pl


def generate_signals_mtf(df4h: pd.DataFrame, df1h: pd.DataFrame,
                         df15: pd.DataFrame, range_on: str = "4h") -> list[BurakSignal]:
    """range_on='4h': the range lives on 4h bars (full MTF). range_on='1h': hybrid —
    the range/deviation logic stays on 1h (like burak_strategy) and only the entry
    trigger drops to 15m; isolates the effect of the 15m confirmation."""
    o4, h4, l4, c4 = (df4h[c].values for c in ("open", "high", "low", "close"))
    o1, h1, l1, c1 = (df1h[c].values for c in ("open", "high", "low", "close"))
    h15v, l15v, c15v = (df15[c].values for c in ("high", "low", "close"))
    atr4, atr1 = _atr(df4h), _atr(df1h)
    body1 = np.abs(c1 - o1)
    n4, n1, n15 = len(df4h), len(df1h), len(df15)

    t4_close = (df4h.index + pd.Timedelta(hours=4)).values
    t1_close = (df1h.index + pd.Timedelta(hours=1)).values
    t15_close = (df15.index + pd.Timedelta(minutes=15)).values

    ph4, pl4 = _pivots(h4, l4)
    ph1, pl1 = _pivots(h1, l1)
    piv4_hi: list[float] = []; piv4_lo: list[float] = []
    piv1_hi: list[float] = []; piv1_lo: list[float] = []

    # current 4h context (refreshed on each completed 4h bar)
    rng = None                       # (rng_hi, rng_lo, width, eq) or None
    trend4 = "none"

    # 1h deviation state per direction: phase IDLE/OUT/ARMED
    dev = {d: {"phase": "IDLE", "ext": None, "until": -1} for d in ("SHORT", "LONG")}
    zones: list[dict] = []           # 1h zones awaiting a 15m trigger
    signals: list[BurakSignal] = []
    cooldown: dict[tuple[str, str], int] = {}

    def on_cd(strat, d, t):
        return t - cooldown.get((strat, d), -10**9) < COOLDOWN_15

    def emit(t, d, entry, sl, target, strat, qual, score, meta):
        long = d == "LONG"
        a = atr1[j1] if j1 >= 0 and not np.isnan(atr1[j1]) else None
        if a is None:
            return
        sl = _floor_risk(entry, sl, a, long)
        tp = _gate_rr(entry, sl, target, long)
        if tp is None:
            return
        cooldown[(strat, d)] = t
        signals.append(BurakSignal(df15.index[t], d, float(entry), float(sl),
                                   float(tp), strat, qual, score, EXPIRY_MIN, meta))

    def on_new_4h(j):
        nonlocal rng, trend4
        p = j - PIVOT_K
        if p >= 0:
            if ph4[p]:
                piv4_hi.append(h4[p])
            if pl4[p]:
                piv4_lo.append(l4[p])
        if len(piv4_hi) >= 2 and len(piv4_lo) >= 2:
            hh, hl = piv4_hi[-1] > piv4_hi[-2], piv4_lo[-1] > piv4_lo[-2]
            trend4 = "up" if (hh and hl) else ("down" if (not hh and not hl) else "none")
        if range_on != "4h":
            return
        rng = None
        e0, e1 = j - DEV_GAP_4H - RANGE_WINDOW_4H + 1, j - DEV_GAP_4H
        if e0 < 0 or np.isnan(atr4[j]) or atr4[j] <= 0:
            return
        rh, rl = h4[e0:e1 + 1].max(), l4[e0:e1 + 1].min()
        width = rh - rl; eq = (rh + rl) / 2.0
        if not (RANGE_MIN_ATR * atr4[j] <= width <= RANGE_MAX_ATR * atr4[j]):
            return
        band = TOUCH_BAND_FRAC * width
        est_h, est_l, est_c = h4[e0:e1 + 1], l4[e0:e1 + 1], c4[e0:e1 + 1]
        if (_touch_clusters(est_h, rh - band, np.inf) >= MIN_TOUCHES
                and _touch_clusters(-est_l, -(rl + band), np.inf) >= MIN_TOUCHES
                and int(np.sum(np.diff(np.sign(est_c - eq)) != 0)) >= MIN_EQ_CROSSES):
            rng = (rh, rl, width, eq)

    def on_new_1h(i):
        nonlocal rng
        p = i - PIVOT_K
        if p >= 0 and ph1[p]:
            piv1_hi.append(h1[p])
        if p >= 0 and pl1[p]:
            piv1_lo.append(l1[p])
        a1 = atr1[i]
        if np.isnan(a1) or a1 <= 0:
            return
        # hybrid mode: the range lives on 1h bars (same gates as burak_strategy)
        if range_on == "1h":
            rng = None
            e0, e1 = i - DEV_GAP - RANGE_WINDOW + 1, i - DEV_GAP
            if e0 >= 0:
                rh_, rl_ = h1[e0:e1 + 1].max(), l1[e0:e1 + 1].min()
                width_ = rh_ - rl_; eq_ = (rh_ + rl_) / 2.0
                if RANGE_MIN_ATR * a1 <= width_ <= RANGE_MAX_ATR * a1:
                    band = TOUCH_BAND_FRAC * width_
                    est_h, est_l, est_c = h1[e0:e1 + 1], l1[e0:e1 + 1], c1[e0:e1 + 1]
                    if (_touch_clusters(est_h, rh_ - band, np.inf) >= MIN_TOUCHES
                            and _touch_clusters(-est_l, -(rl_ + band), np.inf) >= MIN_TOUCHES
                            and int(np.sum(np.diff(np.sign(est_c - eq_)) != 0)) >= MIN_EQ_CROSSES):
                        rng = (rh_, rl_, width_, eq_)
        # ---- deviation state machine (needs a valid range) ----
        if rng is None:
            dev["SHORT"]["phase"] = dev["LONG"]["phase"] = "IDLE"
        else:
            rh, rl, width, eq = rng
            a4 = a1 if range_on == "1h" \
                else atr4[min(np.searchsorted(t4_close, t1_close[i]), n4) - 1]
            for d, bnd, opp in (("SHORT", rh, rl), ("LONG", rl, rh)):
                st = dev[d]; sgn = 1 if d == "SHORT" else -1
                ext_now = h1[i] if d == "SHORT" else l1[i]
                outside = sgn * (ext_now - bnd) > DEV_MIN_POKE_ATR * a4
                close_in = rl < c1[i] < rh
                opp_broken = (l1[i] < rl - OPP_SIDE_TOL_ATR * a4) if d == "SHORT" \
                    else (h1[i] > rh + OPP_SIDE_TOL_ATR * a4)
                if st["phase"] == "IDLE" and outside and not opp_broken:
                    st["phase"], st["ext"] = "OUT", ext_now
                elif st["phase"] == "OUT":
                    st["ext"] = max(st["ext"], ext_now) if d == "SHORT" else min(st["ext"], ext_now)
                    if sgn * (st["ext"] - bnd) > DEV_MAX_FRAC * width or opp_broken:
                        st["phase"] = "IDLE"          # real breakout / messy -> no fade
                    elif close_in:
                        st["phase"], st["until"] = "ARMED", i + ARM_BARS_1H
                elif st["phase"] == "ARMED":
                    if sgn * (ext_now - bnd) > 0:      # re-deviates -> back to OUT
                        st["phase"] = "OUT"
                        st["ext"] = max(st["ext"], ext_now) if d == "SHORT" else min(st["ext"], ext_now)
                    elif i > st["until"] or opp_broken:
                        st["phase"] = "IDLE"
        # ---- 1h zones (need 4h trend) ----
        if i < max(TARGET_LOOKBACK, OB_LOOKBACK + 4):
            return
        tgt_hi = h1[i - TARGET_LOOKBACK + 1:i + 1].max()
        tgt_lo = l1[i - TARGET_LOOKBACK + 1:i + 1].min()

        def add_zone(strat, d, zlo, zhi, target, score):
            if any(z["strat"] == strat and z["dir"] == d and not z["dead"]
                   and min(zhi, z["hi"]) > max(zlo, z["lo"]) for z in zones):
                return                                  # overlapping live zone = dup
            zones.append({"strat": strat, "dir": d, "lo": zlo, "hi": zhi,
                          "target": target, "born": i, "touched": False,
                          "dead": False, "score": score})

        b1_, b2_, b3_ = body1[i - 2], body1[i - 1], body1[i]
        if b1_ >= STRONG_BODY_ATR * a1 and b3_ >= STRONG_BODY_ATR * a1 \
                and b2_ <= IC_BODY_FRAC * min(b1_, b3_):
            if trend4 == "up" and c1[i - 2] > o1[i - 2] and c1[i] > o1[i] and c1[i] > h1[i - 2]:
                add_zone("IC_RETEST", "LONG", l1[i - 1], h1[i - 1], tgt_hi, 6)
            if trend4 == "down" and c1[i - 2] < o1[i - 2] and c1[i] < o1[i] and c1[i] < l1[i - 2]:
                add_zone("IC_RETEST", "SHORT", l1[i - 1], h1[i - 1], tgt_lo, 6)
        if body1[i - 1] >= FVG_DISPL_BODY_ATR * a1:
            if trend4 == "up" and l1[i] > h1[i - 2] and l1[i] - h1[i - 2] >= FVG_MIN_GAP_ATR * a1:
                add_zone("FVG_TREND", "LONG", h1[i - 2], l1[i], tgt_hi, 6)
            if trend4 == "down" and h1[i] < l1[i - 2] and l1[i - 2] - h1[i] >= FVG_MIN_GAP_ATR * a1:
                add_zone("FVG_TREND", "SHORT", h1[i], l1[i - 2], tgt_lo, 6)
        if trend4 == "up" and c1[i] - o1[i - 3] >= OB_IMPULSE_ATR * a1 \
                and piv1_hi and h1[i] > piv1_hi[-1]:
            for k in range(i - 1, i - 1 - OB_LOOKBACK, -1):
                if c1[k] < o1[k]:
                    if (h1[k] + l1[k]) / 2.0 < c1[i] - 0.3 * a1:
                        add_zone("OB_PULLBACK", "LONG", l1[k], h1[k], tgt_hi, 7)
                    break
        if trend4 == "down" and o1[i - 3] - c1[i] >= OB_IMPULSE_ATR * a1 \
                and piv1_lo and l1[i] < piv1_lo[-1]:
            for k in range(i - 1, i - 1 - OB_LOOKBACK, -1):
                if c1[k] > o1[k]:
                    if (h1[k] + l1[k]) / 2.0 > c1[i] + 0.3 * a1:
                        add_zone("OB_PULLBACK", "SHORT", l1[k], h1[k], tgt_lo, 7)
                    break
        # expire old zones
        for z in zones:
            if not z["dead"] and i - z["born"] > ZONE_MAX_AGE_1H:
                z["dead"] = True

    # ------------------------------- main 15m walk -------------------------------
    j4 = j1 = -1
    for t in range(n15):
        ct = t15_close[t]
        while j4 + 1 < n4 and t4_close[j4 + 1] <= ct:
            j4 += 1; on_new_4h(j4)
        while j1 + 1 < n1 and t1_close[j1 + 1] <= ct:
            j1 += 1; on_new_1h(j1)
        if t < TRIG_LOOKBACK_15 or j1 < 0 or np.isnan(atr1[j1]):
            continue
        a1 = atr1[j1]

        # RANGE_DEV: armed setup + 15m structure break in the fade direction
        if rng is not None:
            rh, rl, width, eq = rng
            if dev["SHORT"]["phase"] == "ARMED" and not on_cd("RANGE_DEV", "SHORT", t) \
                    and c15v[t] < l15v[t - TRIG_LOOKBACK_15:t].min() and rl < c15v[t] < rh:
                emit(t, "SHORT", c15v[t], dev["SHORT"]["ext"] + SL_BUF_ATR * a1, rl,
                     "RANGE_DEV", "high", 8,
                     {"rng_hi": rh, "rng_lo": rl, "eq": eq, "dev_ext": dev["SHORT"]["ext"]})
                dev["SHORT"]["phase"] = "IDLE"
            if dev["LONG"]["phase"] == "ARMED" and not on_cd("RANGE_DEV", "LONG", t) \
                    and c15v[t] > h15v[t - TRIG_LOOKBACK_15:t].max() and rl < c15v[t] < rh:
                emit(t, "LONG", c15v[t], dev["LONG"]["ext"] - SL_BUF_ATR * a1, rh,
                     "RANGE_DEV", "high", 8,
                     {"rng_hi": rh, "rng_lo": rl, "eq": eq, "dev_ext": dev["LONG"]["ext"]})
                dev["LONG"]["phase"] = "IDLE"

        # zone strategies: touch the 1h zone, then a 15m rejection candle
        for z in zones:
            if z["dead"]:
                continue
            long = z["dir"] == "LONG"
            if long:
                if c15v[t] < z["lo"] - 0.2 * a1:
                    z["dead"] = True; continue
                if l15v[t] <= z["hi"]:
                    z["touched"] = True
                trig = z["touched"] and c15v[t] > h15v[t - 1] \
                    and z["lo"] <= c15v[t] <= z["hi"] + ZONE_NEAR_ATR * a1
            else:
                if c15v[t] > z["hi"] + 0.2 * a1:
                    z["dead"] = True; continue
                if h15v[t] >= z["lo"]:
                    z["touched"] = True
                trig = z["touched"] and c15v[t] < l15v[t - 1] \
                    and z["hi"] >= c15v[t] >= z["lo"] - ZONE_NEAR_ATR * a1
            want = "up" if long else "down"
            if trig and trend4 == want and not on_cd(z["strat"], z["dir"], t):
                sl = z["lo"] - SL_BUF_ATR * a1 if long else z["hi"] + SL_BUF_ATR * a1
                emit(t, z["dir"], c15v[t], sl, z["target"], z["strat"], "medium",
                     z["score"], {"zone": (z["lo"], z["hi"])})
                z["dead"] = True

    out: list[BurakSignal] = []
    for s in signals:
        dup = any(k.direction == s.direction
                  and abs(k.entry - s.entry) / s.entry <= DEDUP_PCT
                  and (s.timestamp - k.timestamp) <= pd.Timedelta(hours=24)
                  for k in out)
        if not dup:
            out.append(s)
    return out
