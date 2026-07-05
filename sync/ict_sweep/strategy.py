"""ICT liquidity-sweep -> MSS -> entry (the @ekinyzbb-style smart-money day-trade).

Channel methodology (Ekin Yuzbasioglu / @ekinyzbb): ICT / smart-money technical analysis for
futures + crypto — "akilli para once likiditeyi supurur, sonra yon degistirir" (smart money
sweeps liquidity, then reverses). We codify the canonical setup:

    1. LIQUIDITY SWEEP  : a 30m bar wicks BEYOND an N-bar swing extreme (a stop pool) and
                          CLOSES back inside it  (sell-side swept -> bullish, buy-side -> bearish).
    2. MSS / DISPLACEMENT: the reclaim bar shows displacement in the reversal direction — a
                          decisive body closing past the swept level (body >= DISP*ATR, and the
                          candle body points the trade's way). This is the market-structure-shift
                          confirmation folded into the signal bar (fully causal, one bar).
    3. ENTRY           : market on the signal-bar close; stop just past the swept extreme (the
                          liquidity that was raided — a tight, structural invalidation). The LIVE
                          engine then applies the +0.5R directional confirmation (ENTRY_CONFIRM_BUF)
                          before it counts as filled — an ICT "wait for continuation" proxy.

Bias: optionally gated to the 4h trend (strategy.htf_confirm) — "trade the sweep in the HTF
direction" = buy a discount sweep inside a 4h uptrend / sell a premium sweep inside a 4h
downtrend. This is the textbook ICT premium/discount bias and reuses the Donchian 4h confirm
verbatim.

Signal objects are strat.DonSignal so tsc.build_row / so.resolve_scaleout read them unchanged —
the strategy supplies ONLY entry geometry; the live scale-out + portfolio rules do the rest.

Fully causal: the swing channel excludes the current bar (shift(1)); every input on bar i uses
bars up to and including i. The fired timestamp is the signal bar's OPEN time (downstream
resolvers add the 30m ltf to reach the bar close = real fire time) — no look-ahead.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "donchian"))
import strategy as strat   # noqa: E402  (DonSignal, atr, TF_MINUTES, htf_confirm, us_hours_gate)

# ---- parameters (env-tunable for sweeps; ICT-pragmatic defaults) -------------
SWING_N = int(os.environ.get("ICT_SWING_N", "20"))      # liquidity-pool lookback (bars; 20*30m=10h)
ATR_N = strat.ATR_N                                     # ATR window for stop buffer (14)
BUFFER = float(os.environ.get("ICT_BUFFER", "0.10"))    # stop = swept extreme -/+ BUFFER*ATR
DISP = float(os.environ.get("ICT_DISP", "0.0"))         # MSS displacement: reclaim body >= DISP*ATR
RR = float(os.environ.get("ICT_RR", "8.0"))             # structural TP (cap overrides in resolver)
EXPIRY_MINUTES = 180
STRATEGY = "ICT_SWEEP"


def generate_signals(df: pd.DataFrame, symbol: str, *, swing_n: int = SWING_N,
                     buffer: float = BUFFER, disp: float = DISP, rr: float = RR
                     ) -> list["strat.DonSignal"]:
    """Liquidity-sweep + MSS reclaim reversals on 30m closes (one DonSignal per setup)."""
    if df is None or len(df) < swing_n + ATR_N + 2:
        return []
    a = strat.atr(df, ATR_N)
    hi = df["high"].rolling(swing_n).max().shift(1)     # prior swing-high pool (buy-side liquidity)
    lo = df["low"].rolling(swing_n).min().shift(1)      # prior swing-low pool  (sell-side liquidity)
    H, L, O, Cl = (df["high"].values, df["low"].values,
                   df["open"].values, df["close"].values)
    idx = df.index
    out: list[strat.DonSignal] = []
    for i in range(swing_n + ATR_N, len(df)):
        atr_i = a.iloc[i]
        if not (atr_i > 0):
            continue
        loi, hii = lo.iloc[i], hi.iloc[i]
        # bullish: swept sell-side liquidity (low below pool) then reclaimed with a bullish body
        if loi == loi and L[i] < loi and Cl[i] > loi and Cl[i] > O[i] \
                and (Cl[i] - loi) >= disp * atr_i:
            entry = float(Cl[i]); stop = L[i] - buffer * atr_i; risk = entry - stop
            if risk > 0:
                out.append(strat.DonSignal(
                    idx[i], symbol, "long", entry, stop, entry + rr * risk,
                    strategy=STRATEGY, expiry_minutes=EXPIRY_MINUTES,
                    context={"setup": "sweep_low_reclaim", "swing_n": swing_n}))
        # bearish: swept buy-side liquidity (high above pool) then reclaimed with a bearish body
        elif hii == hii and H[i] > hii and Cl[i] < hii and Cl[i] < O[i] \
                and (hii - Cl[i]) >= disp * atr_i:
            entry = float(Cl[i]); stop = H[i] + buffer * atr_i; risk = stop - entry
            if risk > 0:
                out.append(strat.DonSignal(
                    idx[i], symbol, "short", entry, stop, entry - rr * risk,
                    strategy=STRATEGY, expiry_minutes=EXPIRY_MINUTES,
                    context={"setup": "sweep_high_reclaim", "swing_n": swing_n}))
    return out
