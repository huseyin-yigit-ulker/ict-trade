"""OPUS stream selection map: per-symbol allowed ET trading session(s).

OPUS = the MAIN signal set (strategies B/C/D/E, full-TP) but each symbol is only
traded in the NY session(s) where its 2026 signals actually carried an edge
(sembol × seans analizi — sync/out/_symbol_hour_analysis.py). Symbols absent from
this map are NOT traded at all (structurally negative across every session, or too
few trades to trust: ADA/PLTR/XAU/TSLA/BABA/NEAR/SOL/META/MSFT/NVDA/AVGO/AMZN/XRP/AVAX/...).
2026-06-13: of the re-added crypto, only LINK (NY-PM) and DOGE (NY-PM, marginal)
cleared the gate; XRP/AVAX had no positive session and stay out.

Sessions (signal = bar OPEN, converted to America/New_York; DST-aware), WEEKDAYS only
(Sat/Sun dropped — the US market is closed; 24/7 crypto would otherwise pass the
hour-only gate):
  'am' = 09:00–12:00 ET  (NY-AM: NY open + silver-bullet AM ~10:00 ET)
  'pm' = 12:00–16:00 ET  (NY-PM: silver-bullet PM ~14:00 ET)

Derived IN-SAMPLE from 2026 Jan–Jun (kept cells: n>=6 resolved AND avg>=+0.05R).
Treat the headline R as an upper bound until validated out-of-sample.
"""
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# symbol -> allowed sessions
OPUS_MAP: dict[str, list[str]] = {
    "BTCUSDT": ["am", "pm"], "ETHUSDT": ["am", "pm"], "SOLUSDT": ["am", "pm"], "BNBUSDT": ["am", "pm"], "1000PEPEUSDT": ["am", "pm"],
    "WIFUSDT": ["am", "pm"], "SUIUSDT": ["am", "pm"], "NEARUSDT": ["am", "pm"], "FETUSDT": ["am", "pm"], "ADAUSDT": ["am", "pm"],
    "SUSDT": ["am", "pm"], "ARBUSDT": ["am", "pm"], "ORDIUSDT": ["am", "pm"], "ONDOUSDT": ["am", "pm"], "XRPUSDT": ["am", "pm"],
    "DOGEUSDT": ["am", "pm"], "LINKUSDT": ["am", "pm"], "AVAXUSDT": ["am", "pm"], "TAOUSDT": ["am", "pm"], "RENDERUSDT": ["am", "pm"],
    "AKTUSDT": ["am", "pm"], "AAVEUSDT": ["am", "pm"], "UNIUSDT": ["am", "pm"], "INJUSDT": ["am", "pm"], "APTUSDT": ["am", "pm"],
    "SEIUSDT": ["am", "pm"], "TIAUSDT": ["am", "pm"], "ATOMUSDT": ["am", "pm"], "ICPUSDT": ["am", "pm"], "KASUSDT": ["am", "pm"],
    "HYPEUSDT": ["am", "pm"], "JUPUSDT": ["am", "pm"], "ENAUSDT": ["am", "pm"], "PENDLEUSDT": ["am", "pm"], "PEPEUSDT": ["am", "pm"],
    "BONKUSDT": ["am", "pm"], "FLOKIUSDT": ["am", "pm"], "PYTHUSDT": ["am", "pm"], "JTOUSDT": ["am", "pm"], "WLDUSDT": ["am", "pm"],
    "DOTUSDT": ["am", "pm"], "BCHUSDT": ["am", "pm"], "LTCUSDT": ["am", "pm"], "XLMUSDT": ["am", "pm"], "ZECUSDT": ["am", "pm"],
    "NEIROUSDT": ["am", "pm"], "VIRTUALUSDT": ["am", "pm"], "ARKMUSDT": ["am", "pm"], "ZRXUSDT": ["am", "pm"], "VETUSDT": ["am", "pm"],
    "FILUSDT": ["am", "pm"], "TONUSDT": ["am", "pm"], "TRXUSDT": ["am", "pm"], "XAGUSDT": ["am", "pm"], "NVDAUSDT": ["am", "pm"],
    "METAUSDT": ["am", "pm"], "AMZNUSDT": ["am", "pm"], "COINUSDT": ["am", "pm"], "MSTRUSDT": ["am", "pm"], "CRCLUSDT": ["am", "pm"],
    "PLTRUSDT": ["am", "pm"], "TSLAUSDT": ["am", "pm"], "INTCUSDT": ["am", "pm"], "HOODUSDT": ["am", "pm"], "MSFTUSDT": ["am", "pm"],
    "AVGOUSDT": ["am", "pm"], "BABAUSDT": ["am", "pm"], "BXUSDT": ["am", "pm"], "HPEUSDT": ["am", "pm"], "AMATUSDT": ["am", "pm"],
    "CRWDUSDT": ["am", "pm"], "CRDOUSDT": ["am", "pm"], "AAOIUSDT": ["am", "pm"], "IWMUSDT": ["am", "pm"]
}


def opus_session(signal_time_utc) -> str | None:
    """ET session of a signal's bar-open timestamp, or None if outside AM/PM
    OR on a weekend (US market closed Sat/Sun ET — 24/7 crypto would otherwise
    sneak weekend bars through the hour-only gate)."""
    et = signal_time_utc.astimezone(ET)
    if et.weekday() >= 5:          # 5=Sat, 6=Sun (ET) -> US market closed
        return None
    h = et.hour
    if 9 <= h < 12:
        return "am"
    if 12 <= h < 16:
        return "pm"
    return None


def opus_allows(symbol: str, signal_time_utc) -> bool:
    """True iff this symbol is traded in the (weekday) session this signal fired in."""
    sess = OPUS_MAP.get(symbol)
    if not sess:
        return False
    s = opus_session(signal_time_utc)
    return s is not None and s in sess
