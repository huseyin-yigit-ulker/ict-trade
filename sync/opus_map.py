"""OPUS stream selection map: per-symbol allowed ET trading session(s).

OPUS = the MAIN signal set (strategies B/C/D/E, full-TP) but each symbol is only
traded in the NY session(s) where its 2026 signals actually carried an edge
(sembol × seans analizi — sync/out/_symbol_hour_analysis.py). Symbols absent from
this map are NOT traded at all (structurally negative across every session, or too
few trades to trust: ADA/PLTR/XAU/TSLA/BABA/NEAR/SOL/META/MSFT/NVDA/AVGO/AMZN/...).

Sessions (signal = bar OPEN, converted to America/New_York; DST-aware):
  'am' = 09:00–12:00 ET  (NY-AM: NY open + silver-bullet AM ~10:00 ET)
  'pm' = 12:00–16:00 ET  (NY-PM: silver-bullet PM ~14:00 ET)

Derived IN-SAMPLE from 2026 Jan–Jun (kept cells: n>=6 resolved AND avg>=+0.05R).
Treat the headline R as an upper bound until validated out-of-sample.
"""
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# symbol -> allowed sessions
OPUS_MAP: dict[str, list[str]] = {
    # NY-AM only
    "BTCUSDT":  ["am"],
    "ETHUSDT":  ["am"],
    "BNBUSDT":  ["am"],
    "SUSDT":    ["am"],
    "CRCLUSDT": ["am"],
    "ONDOUSDT": ["am"],
    "XAGUSDT":  ["am"],
    "SUIUSDT":  ["am"],
    "INTCUSDT": ["am"],
    # both sessions
    "MSTRUSDT": ["am", "pm"],
    "ARBUSDT":  ["am", "pm"],
    "FETUSDT":  ["am", "pm"],
    # NY-PM only
    "WIFUSDT":      ["pm"],
    "1000PEPEUSDT": ["pm"],
    "COINUSDT":     ["pm"],
    "HOODUSDT":     ["pm"],
}


def opus_session(signal_time_utc) -> str | None:
    """ET session of a signal's bar-open timestamp, or None if outside AM/PM."""
    h = signal_time_utc.astimezone(ET).hour
    if 9 <= h < 12:
        return "am"
    if 12 <= h < 16:
        return "pm"
    return None


def opus_allows(symbol: str, signal_time_utc) -> bool:
    """True iff this symbol is traded in the session this signal fired in."""
    sess = OPUS_MAP.get(symbol)
    if not sess:
        return False
    s = opus_session(signal_time_utc)
    return s is not None and s in sess
