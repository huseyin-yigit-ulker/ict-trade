"""Donchian(55) breakout — the TREND/momentum complement to the RANGE/main book.

Why this strategy exists
------------------------
The 'main' ICT set is structurally a RANGE / mean-reversion system: ~85-90% of its R
lives in the 4h-ER LIGHT band (ER 0.20-0.35) and it is break-even-to-negative in
strong trends. The textbook diversifier for a mean-reversion book is a trend follower:
their returns are weakly/negatively correlated because they earn in mutually exclusive
regimes. This module is that missing momentum wing — gated to the STRONG-trend regime
(Kaufman efficiency ratio >= 0.35) so it only fires where main is weak (near-zero overlap).

Backtest (1h, 12mo to 2026-06-16, BTC/ETH/SOL/XAU/XAG; fixed SL+TP, ATR2x stop, RR=4,
0.1% round-trip fee, no-overlap, 1h-resolved):
    BTC +19R  ETH +31R  SOL +4R  XAU +26R  XAG +5R  ->  ALL +85R, WR 27%
Low win rate / large winners is the trend-follower signature (expect 4-5 consecutive
losers between runners). In-sample, no param optimisation — validate 2025 OOS before
trusting size.

Shared by BOTH submodules of the package:
    donchian.backtest  -> historical R backfill  (version='donchian')
    donchian.canli     -> live signal emission   (ict_trade.signals, mode='donchian')
Both consume generate_signals() so entry geometry is identical live vs backtest.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# ---- parameters (validated defaults; see module docstring) ------------------
N_ENTRY = 55          # Donchian channel lookback (Turtle "slow" system)
ER_N = 24             # Kaufman efficiency-ratio window (bars)
ER_MIN = 0.35         # strong-trend gate: only fire when ER >= this (main is weak here)
ATR_N = 14            # ATR window for stop sizing
ATR_MULT = 2.0        # stop distance = ATR_MULT * ATR
RR = 4.0              # take-profit = entry +/- RR * risk
EXPIRY_MINUTES = 180  # entry-fill window on the 1m resolver (breakout fills ~immediately)
MAX_HOLD_MINUTES = 3 * 24 * 60  # 3-day TIME LIMIT: a position that hasn't hit TP/SL by here is
                                # closed at MARKET (mark-to-market). Uniform across ALL streams.
STRATEGY = "DONCHIAN_BO"
VERSION = "donchian"  # backtest trading_signals.version tag (1h base stream)
MODE = "donchian"     # live ict_trade.signals.mode tag (1h base stream)


# Short stem for suffixed timeframe tags. The backtest trading_signals.version column is
# varchar(10), so the full 'donchian_30m' (12) overflows — 'donch_30m'/'donch_15m'/'donch_4h'
# (<=9) fit. 1h keeps the bare 'donchian' tag (the original base stream).
_SHORT = "donch"


def version_for(tf: str) -> str:
    """Backtest version tag per signal timeframe, e.g. 'donch_30m' (1h -> bare 'donchian')."""
    return VERSION if tf == "1h" else f"{_SHORT}_{tf}"


def mode_for(tf: str) -> str:
    """Live ict_trade.signals.mode tag per signal timeframe (mirrors version_for)."""
    return MODE if tf == "1h" else f"{_SHORT}_{tf}"


# Bar duration per timeframe (minutes) — shared by backtest/live for fire-time math.
TF_MINUTES = {"15m": 15, "30m": 30, "1h": 60, "4h": 240}

# US equity-backed perps: their underlying only has real price discovery during US market
# hours, so breakouts fired outside (pre-market 04:00 ET .. regular close 16:00 ET, Mon-Fri)
# are thin/noise. Gated out of BOTH backtest and live (us_hours_gate). Holidays are NOT
# handled — weekday + time-of-day only. tz-aware via the America/New_York zone (DST-correct).
STOCK_SYMBOLS = frozenset({
    "NVDAUSDT", "METAUSDT", "AMZNUSDT", "COINUSDT", "MSTRUSDT", "CRCLUSDT", "PLTRUSDT",
    "TSLAUSDT", "INTCUSDT", "HOODUSDT", "MSFTUSDT", "AVGOUSDT", "BABAUSDT", "BXUSDT",
    "HPEUSDT", "AMATUSDT", "CRWDUSDT", "CRDOUSDT", "AAOIUSDT", "IWMUSDT",
})
US_OPEN_MIN = 4 * 60       # 04:00 ET — pre-market open
US_CLOSE_MIN = 16 * 60     # 16:00 ET — regular-session close

# NYSE full-day closures 2024-2026 (ET dates). On these the underlying equities don't trade,
# so the perp has no real price discovery — treated like a weekend. (Early-close half-days
# are not modelled.) Mirror in src/utils/sessions.js US_HOLIDAYS.
US_HOLIDAYS = frozenset({
    "2024-01-01", "2024-01-15", "2024-02-19", "2024-03-29", "2024-05-27", "2024-06-19",
    "2024-07-04", "2024-09-02", "2024-11-28", "2024-12-25",
    "2025-01-01", "2025-01-20", "2025-02-17", "2025-04-18", "2025-05-26", "2025-06-19",
    "2025-07-04", "2025-09-01", "2025-11-27", "2025-12-25",
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19",
    "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
})


def in_us_market_hours(ts: pd.Timestamp) -> bool:
    """True if ts falls in US pre-market+regular hours (Mon-Fri 04:00-16:00 ET, DST-correct),
    excluding NYSE holidays (US_HOLIDAYS). Early-close half-days are not modelled."""
    et = (ts.tz_convert("America/New_York") if ts.tz is not None
          else ts.tz_localize("UTC").tz_convert("America/New_York"))
    if et.weekday() >= 5:                      # Sat / Sun
        return False
    if et.strftime("%Y-%m-%d") in US_HOLIDAYS:  # NYSE full-day closure
        return False
    m = et.hour * 60 + et.minute
    return US_OPEN_MIN <= m < US_CLOSE_MIN


def us_hours_gate(signals: list["DonSignal"], symbol: str, tf: str) -> list["DonSignal"]:
    """For US stock-perps, keep only signals whose bar CLOSE (fire time = open + tf bar) lands
    in US market hours; non-stock symbols pass through unchanged."""
    if symbol not in STOCK_SYMBOLS:
        return signals
    bar = pd.Timedelta(minutes=TF_MINUTES.get(tf, 60))
    return [s for s in signals if in_us_market_hours(s.timestamp + bar)]


def hybrid_tag(base_tf: str, htf_tf: str) -> str:
    """Tag for a HYBRID stream = base-tf breakout confirmed by a higher tf's trend
    direction, e.g. ('30m','4h') -> 'dch30_4h' (<=10 chars for the version column)."""
    return f"dch{base_tf.rstrip('mh')}_{htf_tf}"


def htf_confirm(signals: list["DonSignal"], base_tf: str, htf_df: pd.DataFrame,
                htf_tf: str, *, n_entry: int = N_ENTRY) -> list["DonSignal"]:
    """Keep only signals whose direction agrees with the HIGHER timeframe trend — HTF
    close on the trade's side of its `n_entry`-bar Donchian midline — as of each signal's
    FIRE time (= base bar close = signal.timestamp + base bar). Causal: only HTF bars that
    have CLOSED by the fire time are consulted (close_time = bar open + htf bar). The
    2026 sweep found this 4h-direction confirmation is the single best filter for the
    30m/15m breakout (it doubles R/trade and rescues 15m from break-even); the HTF ER
    gate, by contrast, hurts. Kept signals are annotated context['htf_confirm']=htf_tf."""
    if htf_df is None or htf_df.empty or not signals:
        return []
    base_bar = pd.Timedelta(minutes=TF_MINUTES[base_tf])
    htf_bar = pd.Timedelta(minutes=TF_MINUTES[htf_tf])
    hi = htf_df["high"].rolling(n_entry).max().shift(1)
    lo = htf_df["low"].rolling(n_entry).min().shift(1)
    mid = ((hi + lo) / 2).values
    close = htf_df["close"].values
    close_time = htf_df.index + htf_bar          # the bar's real availability (close) time
    out: list[DonSignal] = []
    for s in signals:
        fire = s.timestamp + base_bar
        pos = int(close_time.searchsorted(fire, side="right")) - 1
        if pos < 0 or pos >= len(mid):
            continue                              # no closed HTF bar yet -> can't confirm
        m = mid[pos]
        if m != m:                                # NaN midline (warmup) -> skip
            continue
        ok = (close[pos] > m) if s.direction == "long" else (close[pos] < m)
        if ok:
            s.context = {**(s.context or {}), "htf_confirm": htf_tf}
            out.append(s)
    return out

# Full universe — mirrors sync_daily.STATIC_SYMBOLS (the 40-symbol production set), so the
# 2026 backtest and the live emitter both cover every symbol. The strategy was VALIDATED
# on the 5 "temel" core (BTC/ETH/SOL/XAU/XAG, all positive); the rest are unvalidated —
# the per-symbol backtest R surfaces which crypto/stock-perp symbols actually carry a
# trend edge (prune the negatives after reviewing + the 2025 OOS run).
CORE_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XAUUSDT", "XAGUSDT"]
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
    "1000PEPEUSDT", "WIFUSDT", "SUIUSDT",
    "NEARUSDT", "FETUSDT", "ADAUSDT", "SUSDT",
    "ARBUSDT", "ORDIUSDT", "ONDOUSDT",
    "XRPUSDT", "DOGEUSDT", "LINKUSDT", "AVAXUSDT",
    "XAUUSDT", "XAGUSDT",
    "NVDAUSDT", "METAUSDT", "AMZNUSDT", "COINUSDT", "MSTRUSDT",
    "CRCLUSDT", "PLTRUSDT", "TSLAUSDT", "INTCUSDT", "HOODUSDT",
    "MSFTUSDT", "AVGOUSDT", "BABAUSDT", "BXUSDT", "HPEUSDT",
    "AMATUSDT", "CRWDUSDT", "CRDOUSDT", "AAOIUSDT", "IWMUSDT",
]


@dataclass
class DonSignal:
    """Minimal signal object exposing the attributes tsc.build_row / tsc.simulate read."""
    timestamp: pd.Timestamp
    symbol: str
    direction: str            # "long" / "short"
    entry: float
    stop_loss: float
    take_profit_1: float
    er: float = float("nan")  # efficiency ratio at the entry bar (regime evidence)
    strategy: str = STRATEGY
    quality: str = "high"
    confluence_score: int = 0
    expiry_minutes: int = EXPIRY_MINUTES
    context: dict = field(default_factory=dict)


# ---- indicators -------------------------------------------------------------
def atr(df: pd.DataFrame, n: int = ATR_N) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def eff_ratio(close: pd.Series, n: int = ER_N) -> pd.Series:
    """Kaufman efficiency ratio: |net move over n| / sum|bar moves|. ~0 chop, ~1 clean trend."""
    change = close.diff(n).abs()
    vol = close.diff().abs().rolling(n).sum()
    return change / vol.replace(0, np.nan)


# ---- signal generation ------------------------------------------------------
def generate_signals(df: pd.DataFrame, symbol: str,
                     *, n_entry: int = N_ENTRY, er_min: float = ER_MIN,
                     atr_mult: float = ATR_MULT, rr: float = RR) -> list[DonSignal]:
    """Discrete Donchian breakouts on 1h closes, gated to ER >= er_min.

    A signal fires on a FRESH break only — close crosses beyond the prior n_entry-bar
    extreme this bar (so a sustained breakout emits once, not every bar). Entry = bar
    close, stop = atr_mult*ATR away, target = rr*risk. Causal: every input uses bars up
    to and including the signal bar (rolling().shift(1) excludes the current bar from the
    channel). The fired timestamp is the signal bar's OPEN time; downstream resolvers add
    the 1h ltf to reach the bar close (= real fire time), so there is no look-ahead.
    """
    if df is None or len(df) < n_entry + ER_N + 2:
        return []
    a = atr(df)
    er = eff_ratio(df["close"])
    hi = df["high"].rolling(n_entry).max().shift(1)
    lo = df["low"].rolling(n_entry).min().shift(1)
    c = df["close"].values
    idx = df.index
    out: list[DonSignal] = []
    for i in range(n_entry + ER_N, len(df)):
        risk = atr_mult * a.iloc[i]
        if not (risk > 0) or not (er.iloc[i] >= er_min):
            continue
        long_brk = c[i] > hi.iloc[i] and c[i - 1] <= hi.iloc[i - 1]
        short_brk = c[i] < lo.iloc[i] and c[i - 1] >= lo.iloc[i - 1]
        if long_brk:
            entry = float(c[i])
            out.append(DonSignal(idx[i], symbol, "long", entry,
                                 entry - risk, entry + rr * risk, float(er.iloc[i]),
                                 context={"er": round(float(er.iloc[i]), 3),
                                          "channel_n": n_entry, "rr": rr}))
        elif short_brk:
            entry = float(c[i])
            out.append(DonSignal(idx[i], symbol, "short", entry,
                                 entry + risk, entry - rr * risk, float(er.iloc[i]),
                                 context={"er": round(float(er.iloc[i]), 3),
                                          "channel_n": n_entry, "rr": rr}))
    return out
