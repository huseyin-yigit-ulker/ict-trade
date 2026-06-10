"""ICT Live Signal DAG — STANDALONE.

Self-contained Airflow DAG: requires no sibling Python packages, just drop
this single file into the Airflow DAGs folder. Engine logic for the 5 ICT
strategies (A-E) is inlined below. The same engine ran in the backtest
under backtest/ — this file is the production-deployable mirror.

Hourly at HH:01 UTC: pulls 6000h (~250d) of recent 1h klines per symbol from
Binance Futures (spot fallback), runs the engine ONLY on the last fully-
closed bar, then for any new signal:
  - INSERT into ict_trade.signals (live dashboard table)
  - send Telegram alert
Idempotent on (symbol, signal_time, direction).

Look-ahead safety:
  - Detectors expose `confirmed_at` / `created_at_index` / `mitigation_index`
    so strategies can ask "was this fact known by bar T?"
  - Engine never reads bars after the requested at_index.
  - The open (forming) bar is dropped before engine call (`trim_open_bar`).
  Verified by backtest/test_no_lookahead.py + backtest/test_dag_parity.py.
"""

from __future__ import annotations

# ============================================================================
# AIRFLOW
# ============================================================================
# Airflow is optional: present when deployed as an Airflow DAG, absent when this
# same file is run standalone (e.g. on a GitHub Actions runner via `python dag/dag.py`).
try:
    from airflow.decorators import dag, task
    from airflow.utils.dates import days_ago
    from airflow.timetables.trigger import CronTriggerTimetable
    _AIRFLOW_AVAILABLE = True
except ImportError:
    _AIRFLOW_AVAILABLE = False

# ============================================================================
# STDLIB / THIRD-PARTY
# ============================================================================
import json
import os
import sys
import time
import uuid
import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
import requests
from sqlalchemy import create_engine, text


# ============================================================================
# CONFIG (kept inline so DAG is fully standalone)
# ============================================================================

# Secrets come from the environment (GitHub Actions secrets / Airflow env / local .env).
# NEVER hard-code credentials here — this file is committed to git.
try:
    from dotenv import load_dotenv
    load_dotenv()  # silently loads a local .env if present; no-op in CI
except Exception:
    pass

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

DB_CONNECTION_STRING = os.getenv("DB_CONNECTION_STRING", "")

INTERVAL = "1h"
HTF_RULE = "4h"
WARMUP_HOURS = 6000   # ~250 days; verified ~99% backtest-DAG parity

# Production set — TON, XRP, 1000SHIB, LINK, OP excluded after their negative
# 2025+2026 backtest performance. Strategy A is also disabled in STRATEGIES
# below; both years showed it net negative.
# 2026-06-10: DOGE (-27R), GOOGL (-18R, 0 TP in 18), PLTR (-22R), TSLA (-11R)
# removed after the 2026 Jan-Jun v1 audit — same criterion as the TON/XRP cut.
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
    "1000PEPEUSDT", "WIFUSDT", "SUIUSDT",
    "NEARUSDT", "FETUSDT", "ADAUSDT", "SUSDT",
    "ARBUSDT", "ORDIUSDT", "ONDOUSDT",
    "XAUUSDT", "XAGUSDT",
    # Stock-backed perps (underlying equities)
    "NVDAUSDT", "METAUSDT",
    "AMZNUSDT", "COINUSDT", "MSTRUSDT",
]

# --- dynamic volume-anomaly picks ---
# Each run, IN ADDITION to SYMBOLS, scan up to DYN_MAX_PICKS extra symbols whose
# last-closed 1h bar quote-volume spiked vs their own recent baseline. Written with
# mode='dynamic' (kept out of the main live view + backtest sync).
# RADAR DISABLED (2026-06-10): 2026 backtest net -17R and worsening
# (Apr -12R, May -19R, Jun -5R; 2 TP in last 46 trades). Volume-spike coins
# keep trending, so sweep-reversal logic fights momentum. Re-enable with
# DYN_SYMBOLS=1 only after a positive paper-mode period.
DYN_ENABLED         = os.getenv("DYN_SYMBOLS", "0").strip().lower() not in ("0", "false", "no", "off")
DYN_MAX_PICKS       = 5
DYN_CANDIDATE_CAP   = 50        # top-N by 24h quoteVolume probed with kline fetches
DYN_KLINE_WINDOW    = 50        # bars fetched per candidate
DYN_BASELINE_BARS   = 24        # baseline = median of the N bars before the last closed bar
DYN_SPIKE_RATIO     = 3.0       # last_qv / baseline_median >= this -> anomaly
DYN_MIN_BASELINE_QV = 50_000.0  # USDT: skip dust (baseline median below this)
DYN_TICKER_URL      = "https://fapi.binance.com/fapi/v1/ticker/24hr"
DYN_EXINFO_URL      = "https://fapi.binance.com/fapi/v1/exchangeInfo"
# Drop stablecoin / fiat / wrapped bases (they trade ~1.00 -> nonsense structure).
# NOTE: performance-excluded names (XRP/TON/1000SHIB/LINK/OP) are intentionally NOT
# blocked here — a real volume spike makes them eligible (user decision).
DYN_BASE_BLOCKLIST = {
    "USDC", "FDUSD", "TUSD", "BUSD", "DAI", "USDP", "UST", "USTC", "PAX", "SUSD",
    "USDE", "USDD", "AEUR", "BFUSD", "EUR", "GBP", "TRY", "BRL", "AUD", "JPY",
    "ARS", "PLN", "ZAR", "MXN", "RUB", "UAH",
    "WBTC", "WETH", "WBETH", "BETH", "STETH", "WSTETH",
}

# --- PULSE: high-frequency 15m live pass ---
# A 3rd live stream, run on a 15-minute cadence over the SAME static SYMBOLS but
# kept FULLY SEPARATE from the hourly main/dynamic scan:
#   - DB: mode='pulse' (dedup is mode-aware, so a 15m and a 1h signal on the same
#     symbol/bar-open never collide), ltf='15m', htf='1h'
#   - Telegram: a dedicated chat (TELEGRAM_PULSE_CHAT_ID); if unset, falls back to
#     the main chat but with a distinct ⚡ PULSE banner so it never blends in
# Mirrors the v1-15m backtest exactly: 15m primary, 1h HTF, Strategy C only.
# PULSE DISABLED (2026-06-10): backtest +733R shrank to +245R after zone-dedup,
# and 62% of its wins sat at exactly 13.33R (= TP cap 4.0 ATR / SL buffer 0.3 ATR)
# with median stop distance 0.12% of price — sub-spread stops that live slippage
# would destroy. Cron entry removed; re-enable with PULSE_ENABLED=1 only after a
# friction-adjusted backtest stays positive.
PULSE_ENABLED      = os.getenv("PULSE_ENABLED", "0").strip().lower() not in ("0", "false", "no", "off")
PULSE_INTERVAL     = "15m"
PULSE_HTF          = "1h"
PULSE_WARMUP_HOURS = 3000      # ~125 days of 15m for detector / HTF / liquidity warmup
PULSE_MODE         = "pulse"
TELEGRAM_PULSE_CHAT_ID = os.getenv("TELEGRAM_PULSE_CHAT_ID", "")  # "" -> main chat + banner
PULSE_HEARTBEAT_ENABLED = os.getenv("PULSE_HEARTBEAT", "0").strip().lower() not in ("0", "false", "no", "off")

# --- IMPULSE: live MAIN-v2 stream (refined set from the 2026 audit) ---
# Hourly 1h scan over the SAME static universe as main, but the v2 strategy set:
# drop strategy E (0 signals/yr) and disable D on ADA/XAU/ETH (D net-negative there,
# -48R in 2026 — see sync/backfill_v2_year.py). Kept FULLY SEPARATE from main:
#   - DB: mode='impulse' (dedup is mode-aware, so an 'impulse' and a 'live' signal on
#     the same symbol+bar+direction are DISTINCT rows and never collide).
#   - daily sync (sync/sync_daily.py) resolves mode='impulse' -> backtest version='v2'.
#   - Telegram: DB-only by default (most impulse signals overlap main, so alerting both
#     would double-notify). Set TELEGRAM_IMPULSE_CHAT_ID to alert a dedicated chat.
IMPULSE_ENABLED = os.getenv("IMPULSE_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")
IMPULSE_MODE = "impulse"
IMPULSE_EXTRA_D_EXCLUDE = {"ADAUSDT", "XAUUSDT", "ETHUSDT"}   # v2: D off here too
TELEGRAM_IMPULSE_CHAT_ID = os.getenv("TELEGRAM_IMPULSE_CHAT_ID", "")  # "" -> DB-only (no alert)

# --- RADAR: live v3 stream (vol-compression Donchian breakout, strategy F) ---
# Hourly 1h scan over the SAME static universe as main, running ONLY strategy_f —
# a brand-new trend-continuation algorithm reusing the retired "radar" name (the old
# radar was mode='dynamic'/version='v1-dyn'; fully distinct tags, no collision).
#   - DB: mode='radar' (mode-aware dedup keeps it separate from 'live'/'impulse').
#   - daily sync (sync/sync_daily.py) resolves mode='radar' -> backtest version='v3'.
#   - Telegram: DB-only by default; set TELEGRAM_RADAR_CHAT_ID for a dedicated chat.
# DEFAULT OFF — the 2026 Jan-Jun v3 backtest FAILED its acceptance gates
# (2026-06-10: 133 closed, 15% win, -60R, every month negative after January;
# the entry-mechanics ablation in sync/experiment_v3.py showed market-at-close
# entries do WORSE (-65R), so the edge itself is absent in this regime, not an
# artifact of the retest-limit adaptation). Do NOT enable without a redesign
# that passes the gates; the wiring below stays inert until then.
RADAR_ENABLED = os.getenv("RADAR_ENABLED", "0").strip().lower() not in ("0", "false", "no", "off")
RADAR_MODE = "radar"
TELEGRAM_RADAR_CHAT_ID = os.getenv("TELEGRAM_RADAR_CHAT_ID", "")  # "" -> DB-only (no alert)

# --- SQUEEZE: live v4 stream (funding-extreme squeeze fade, strategy G) ---
# Hourly 1h scan over the SAME static universe as main, running ONLY strategy_g —
# the judge panel's runner-up candidate (2026-06-10), built after v3 failed its
# gates. The signal is DERIVATIVE POSITIONING, not price geometry: extreme perp
# funding marks a crowded side; G fades the crowd on a squeeze-ignition bar.
#   - DB: mode='squeeze' (mode-aware dedup keeps it separate from other streams).
#   - daily sync (sync/sync_daily.py) resolves mode='squeeze' -> backtest version='v4'.
#   - Telegram: DB-only by default; set TELEGRAM_SQUEEZE_CHAT_ID for a dedicated chat.
#   - Needs one extra fetch per symbol (45d of /fapi/v1/fundingRate); symbols without
#     funding history (spot-only fallback names) silently emit nothing.
# DEFAULT OFF — the 2026 Jan-Jun v4 backtest FAILED its acceptance gates
# (2026-06-10: 116 closed, 24.1% win, -52.3R; both directions negative; the
# sync/experiment_squeeze.py ablation found no one-knob variant with a positive
# sign — extreme funding marked positioning that was RIGHT about the trend in
# this regime, so fading it got run over). Do NOT enable without a redesign that
# passes the gates; the wiring below stays inert until then.
SQUEEZE_ENABLED = os.getenv("SQUEEZE_ENABLED", "0").strip().lower() not in ("0", "false", "no", "off")
SQUEEZE_MODE = "squeeze"
TELEGRAM_SQUEEZE_CHAT_ID = os.getenv("TELEGRAM_SQUEEZE_CHAT_ID", "")  # "" -> DB-only (no alert)
SQUEEZE_FUND_FETCH_DAYS = 45   # > 30d percentile window + slack for the shift(1)

# --- engine knobs ---
ATR_PERIOD = 14
SWING_N_ITF = 3
SWING_N_HTF = 5
EQUAL_LEVEL_TOL_PCT = 0.0005
EQUAL_LEVEL_TOL_ATR = 0.3
IMPULSE_ATR_MULT = 2.0
IMPULSE_BAR_WINDOW = 5
IMPULSE_CONSEC_BARS = 3
OB_FVG_OVERLAP_MIN = 0.3
STRAT_C_PROXIMITY_ATR = 2.0
ZONE_MAX_AGE_BARS = 100
SWEEP_LOOKBACK_BARS = 5
CHOCH_AFTER_SWEEP_BARS = 5
ENTRY_EXPIRY_BARS = 12
EXPIRY_MINUTES = 180
SL_ATR_BUFFER = 0.2
SL_ATR_BUFFER_C = 0.3
# One zone = one trade — mirrors backtest/ict/config.py (see notes there).
DEDUP_COOLDOWN_MINUTES = 1440
DEDUP_ENTRY_TOL_PCT = 0.0005
# Floor on SL distance: max(pct-of-entry, ATR multiple) — kills sub-spread stops.
MIN_SL_DIST_PCT = 0.0015
MIN_SL_DIST_ATR = 0.5
MIN_RR_DEFAULT = 2.0
MIN_RR_SILVER_BULLET = 3.0
# Strategy D net-negative on these (2026 Jan-Jun audit) — D skips them, C/B/E still run.
D_EXCLUDE_SYMBOLS = {"NVDAUSDT", "NEARUSDT", "AMZNUSDT", "ORDIUSDT"}
TP_MAX_ATR_MULT = 4.0
ASIA_RANGE_MAX_ATR = 3.0
OTE_LOW = 0.62
OTE_HIGH = 0.79
# RADAR / strategy F knobs — mirrors backtest/ict/config.py RADAR_* (see notes there).
# Named RADAR_* (not IMPULSE_*-style) to avoid clashing with the displacement-detector
# IMPULSE_ATR_MULT family above.
RADAR_DONCHIAN_LOOKBACK = 120
RADAR_ATR_PERIOD        = 24
RADAR_COMPRESSION_SMA   = 240
RADAR_COMPRESSION_MAX   = 0.85
RADAR_DEEP_COMPRESSION  = 0.70
RADAR_VOL_MEDIAN_BARS   = 20
RADAR_VOL_SURGE_MIN     = 1.5
RADAR_STRONG_VOLUME     = 2.5
RADAR_EMA_PERIOD        = 200
RADAR_SL_ATR_MULT       = 2.5
RADAR_TP_R_MULT         = 3.0
RADAR_CHASE_MAX_ATR     = 1.2
RADAR_ENTRY_EXPIRY_BARS = 24
RADAR_REFIRE_BARS       = 24
# SQUEEZE / strategy G knobs — mirrors backtest/ict/config.py SQUEEZE_* (see notes there).
SQUEEZE_ATR_PERIOD        = 24
SQUEEZE_ABS_MIN_8H        = 0.0005
SQUEEZE_SEVERE_8H         = 0.0010
SQUEEZE_PCTL_WINDOW       = "30D"
SQUEEZE_PCTL              = 0.95
SQUEEZE_MIN_EVENTS        = 40
SQUEEZE_STALE_HOURS       = 12.0
SQUEEZE_IGNITION_ATR      = 0.25
SQUEEZE_RETRACE_ATR       = 0.35
SQUEEZE_SL_ATR_MULT       = 2.0
SQUEEZE_TP_R_MULT         = 2.0
SQUEEZE_ENTRY_EXPIRY_BARS = 12
SQUEEZE_REFIRE_BARS       = 48

NY_TZ = "America/New_York"

# (start_hour, end_hour) NY local; end exclusive. crosses midnight if start>end.
KILLZONES_NY = {
    "asia_range":       (19, 24),
    "london_open":      (2, 5),
    "ny_open":          (7, 10),
    "silver_bullet_am": (10, 11),
    "london_close":     (10, 12),
    "silver_bullet_pm": (14, 15),
}

CONFLUENCE_WEIGHTS = {
    "htf_aligned":      3, "liquidity_swept":  2, "ltf_choch":        2,
    "discount_premium": 1, "ote_zone":         1, "in_killzone":      1,
    "ob_fvg_overlap":   2, "eqh_eql_swept":    1, "silver_bullet":    2,
    "power_of_three":   2, "multi_strategy":   3,
    # radar / strategy F factors (required trio scores 7 >= publish; both graded
    # extras reach 9 = CONFLUENCE_HIGH -> quality 'high')
    "regime_aligned":   3, "vol_compression":  2, "volume_surge":     2,
    "deep_compression": 1, "strong_volume":    1,
    # squeeze / strategy G factors (same 7-publish / 9-high grading scheme)
    "funding_extreme":     3, "crowding_percentile": 2, "squeeze_ignition": 2,
    "funding_severe":      1, "funding_unwind":      1,
}
CONFLUENCE_MIN_PUBLISH = 6
CONFLUENCE_HIGH = 9
CONFLUENCE_MAX = 12

OHLCV_COLS = ["open", "high", "low", "close", "volume"]
BINANCE_FAPI = "https://fapi.binance.com/fapi/v1/klines"
BINANCE_API  = "https://api.binance.com/api/v3/klines"

# Optional outbound proxy for Binance. US-based runners (e.g. GitHub-hosted)
# get HTTP 451 from Binance; routing through a proxy in an allowed region (TR/EU)
# fixes it. Set BINANCE_PROXY to a full proxy URL, e.g.:
#   http://user:pass@host:port   or   socks5://host:port   (socks needs PySocks)
BINANCE_PROXY = os.getenv("BINANCE_PROXY", "").strip()
_PROXIES = {"http": BINANCE_PROXY, "https": BINANCE_PROXY} if BINANCE_PROXY else None


# ============================================================================
# DATA FETCH (Binance Futures with Spot fallback) + MTF aggregation
# ============================================================================

def fetch_klines(symbol: str, interval: str, start_ms: int, end_ms: int,
                 futures: bool = True, limit: int = 1500) -> pd.DataFrame:
    base = BINANCE_FAPI if futures else BINANCE_API
    rows: list = []
    cursor = start_ms
    while cursor < end_ms:
        params = {"symbol": symbol, "interval": interval,
                  "startTime": cursor, "endTime": end_ms, "limit": limit}
        try:
            r = requests.get(base, params=params, timeout=20, proxies=_PROXIES)
            r.raise_for_status()
            chunk = r.json()
        except Exception as e:
            print(f"  fetch error ({base}): {e}")
            break  # let the spot fallback below run (e.g. on a 451 from futures)
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < limit:
            break
        cursor = chunk[-1][0] + 1
        time.sleep(0.1)

    if not rows and futures:
        return fetch_klines(symbol, interval, start_ms, end_ms, futures=False, limit=limit)
    if not rows:
        return pd.DataFrame(columns=OHLCV_COLS)

    df = pd.DataFrame(rows, columns=[
        "ts", "open", "high", "low", "close", "volume",
        "_ct", "_qv", "_n", "_tbb", "_tbq", "_i"
    ])
    df["timestamp"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("timestamp")[OHLCV_COLS].astype(float)
    return df[~df.index.duplicated(keep="last")].sort_index()


BINANCE_FUNDING = "https://fapi.binance.com/fapi/v1/fundingRate"


def fetch_funding(symbol: str, start_ms: int, end_ms: int,
                  limit: int = 1000) -> pd.DataFrame:
    """Settled perp funding events (mirrors backtest/ict/data.py fetch_funding).

    DataFrame indexed by fundingTime (UTC) with a single `rate` column. Each rate
    is FINAL and public at its fundingTime — consuming it at any bar close >=
    fundingTime is causally safe. No spot fallback: spot-only symbols return an
    empty frame and strategy_g stays silent for them."""
    rows: list = []
    cursor = start_ms
    while cursor < end_ms:
        params = {"symbol": symbol, "startTime": cursor,
                  "endTime": end_ms, "limit": limit}
        try:
            r = requests.get(BINANCE_FUNDING, params=params, timeout=20, proxies=_PROXIES)
            r.raise_for_status()
            chunk = r.json()
        except Exception as e:
            print(f"  funding fetch error ({symbol}): {e}")
            break
        if not isinstance(chunk, list) or not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < limit:
            break
        cursor = chunk[-1]["fundingTime"] + 1
        time.sleep(0.1)

    if not rows:
        return pd.DataFrame(columns=["rate"])
    fdf = pd.DataFrame(rows)
    fdf["timestamp"] = pd.to_datetime(fdf["fundingTime"], unit="ms", utc=True)
    fdf["rate"] = fdf["fundingRate"].astype(float)
    fdf = fdf.set_index("timestamp")[["rate"]]
    return fdf[~fdf.index.duplicated(keep="last")].sort_index()


_AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}

def aggregate(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    return df.resample(rule, label="right", closed="right").agg(_AGG).dropna()


# ============================================================================
# DYNAMIC VOLUME-ANOMALY SYMBOL PICKS
# Picks up to DYN_MAX_PICKS symbols (outside the static SYMBOLS) whose last closed
# 1h bar quote-volume spiked vs their own recent baseline. All Binance calls reuse
# the existing _PROXIES; every function fails closed so the core scan never breaks.
# ============================================================================

def _fetch_24h_tickers() -> list:
    """Market-wide 24h ticker: [{symbol, quoteVolume, ...}, ...]. [] on any error."""
    try:
        r = requests.get(DYN_TICKER_URL, timeout=20, proxies=_PROXIES)
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"  [dyn] 24h ticker fetch failed: {e}")
        return []


def _active_usdt_perps() -> Optional[set]:
    """Active PERPETUAL USDT contracts. None on error (caller falls back to suffix filter)."""
    try:
        r = requests.get(DYN_EXINFO_URL, timeout=20, proxies=_PROXIES)
        r.raise_for_status()
        syms = r.json().get("symbols", [])
        return {s["symbol"] for s in syms
                if s.get("contractType") == "PERPETUAL"
                and s.get("status") == "TRADING"
                and s.get("quoteAsset") == "USDT"}
    except Exception as e:
        print(f"  [dyn] exchangeInfo fetch failed: {e}; using suffix filter")
        return None


def _shortlist_candidates(tickers: list, exclude: set, active: Optional[set]) -> list:
    """USDT-perps outside `exclude`, ranked by 24h quoteVolume, top DYN_CANDIDATE_CAP."""
    rows = []
    for t in tickers:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT") or sym in exclude:
            continue
        if active is not None and sym not in active:
            continue
        if "_" in sym or sym.endswith(("UPUSDT", "DOWNUSDT", "BULLUSDT", "BEARUSDT")):
            continue
        if sym[:-4] in DYN_BASE_BLOCKLIST:
            continue
        try:
            qv = float(t.get("quoteVolume", 0.0))
        except (TypeError, ValueError):
            continue
        if qv > 0:
            rows.append((sym, qv))
    rows.sort(key=lambda x: x[1], reverse=True)
    return [s for s, _ in rows[:DYN_CANDIDATE_CAP]]


def _volume_anomaly_score(symbol: str) -> Optional[tuple]:
    """Score the last CLOSED 1h bar's quote-volume vs the median of the prior
    DYN_BASELINE_BARS bars. quote-volume approximated as volume*close. Returns
    (ratio, last_qv) or None if unscoreable."""
    end = pd.Timestamp.now(tz="UTC")
    start = end - pd.Timedelta(hours=DYN_KLINE_WINDOW + 2)
    df = fetch_klines(symbol, INTERVAL,
                      int(start.timestamp() * 1000), int(end.timestamp() * 1000))
    if df.empty:
        return None
    df = trim_open_bar(df)
    if len(df) < DYN_BASELINE_BARS + 1:
        return None
    qv = df["volume"] * df["close"]
    last_qv = float(qv.iloc[-1])
    baseline = float(qv.iloc[-(DYN_BASELINE_BARS + 1):-1].median())
    if baseline < DYN_MIN_BASELINE_QV or baseline <= 0:
        return None
    return (last_qv / baseline, last_qv)


def pick_volume_anomaly_symbols(exclude: set, k: int = DYN_MAX_PICKS) -> list:
    """Up to k symbols (outside `exclude`) whose last-closed 1h bar quote-volume
    spiked >= DYN_SPIKE_RATIO vs their own baseline, ranked by spike desc.
    Scores the WHOLE shortlist (ordered by liquidity) then takes global top-k.
    Fails closed: returns [] on any infra error; quiet hours may return < k."""
    if not DYN_ENABLED or k <= 0:
        return []
    tickers = _fetch_24h_tickers()
    if not tickers:
        return []
    active = _active_usdt_perps()
    candidates = _shortlist_candidates(tickers, exclude, active)
    scored = []
    seen = set(exclude)
    for sym in candidates:
        if sym in seen:
            continue
        try:
            res = _volume_anomaly_score(sym)
        except Exception as e:
            print(f"  [dyn] score error {sym}: {e}")
            continue
        if res and res[0] >= DYN_SPIKE_RATIO:
            scored.append((res[0], sym))
            seen.add(sym)
    scored.sort(key=lambda x: x[0], reverse=True)
    picks = [s for _, s in scored[:k]]
    if picks:
        print("  [dyn] volume-anomaly picks: "
              + ", ".join(f"{s}({r:.1f}x)" for r, s in scored[:k]))
    return picks


# ============================================================================
# INDICATORS
# ============================================================================

def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


# ============================================================================
# DETECTOR DATACLASSES
# ============================================================================

@dataclass
class Swing:
    type: str
    index: int
    timestamp: pd.Timestamp
    price: float
    confirmed_at: int

@dataclass
class StructureEvent:
    type: str
    direction: str
    broken_level: float
    broken_at_index: int
    broken_at_ts: pd.Timestamp
    trend_before: str
    trend_after: str

@dataclass
class LiquidityLevel:
    type: str
    level: float
    created_at_index: int
    swept: bool = False
    swept_at_index: Optional[int] = None
    sweep_extreme: Optional[float] = None

@dataclass
class OrderBlock:
    type: str
    top: float
    bottom: float
    created_at_index: int
    impulse_size_atr: float
    confirmed_at_index: int = 0
    mitigated: bool = False
    mitigation_index: Optional[int] = None

@dataclass
class FVG:
    type: str
    top: float
    bottom: float
    created_at_index: int
    fill_status: str = "open"
    fill_pct: float = 0.0
    filled_at_index: Optional[int] = None
    partial_at_index: Optional[int] = None

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
        size = self.high - self.low
        if direction == "bullish":
            return (self.high - OTE_HIGH * size, self.high - OTE_LOW * size)
        return (self.low + OTE_LOW * size, self.low + OTE_HIGH * size)


# ============================================================================
# DETECTORS
# ============================================================================

def detect_swings(df: pd.DataFrame, n: int = SWING_N_ITF) -> list[Swing]:
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


def detect_structure(df: pd.DataFrame, swings: list[Swing]) -> list[StructureEvent]:
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
            last_high = None
        elif last_low and c < last_low.price:
            new_trend = "down"
            evt_type = "BOS" if trend == "down" else "CHoCH"
            events.append(StructureEvent(evt_type, "bearish", last_low.price, i, idx[i], trend, new_trend))
            trend = new_trend
            last_low = None
    return events


def htf_bias_lookup(structure_events: list[StructureEvent], at_index: int) -> str:
    last = None
    for e in structure_events:
        if e.broken_at_index > at_index:
            break
        last = e
    if not last:
        return "range"
    return "bullish" if last.trend_after == "up" else ("bearish" if last.trend_after == "down" else "range")


def _level_tolerance(price: float, atr_value: float) -> float:
    return max(EQUAL_LEVEL_TOL_PCT * price, EQUAL_LEVEL_TOL_ATR * atr_value)


def detect_persistent_liquidity(df: pd.DataFrame) -> list[LiquidityLevel]:
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
    high = df["high"].values
    low = df["low"].values
    close = df["close"].values
    for lvl in levels:
        if lvl.swept:
            continue
        is_high_level = lvl.type in ("PDH", "PWH", "EQH")
        for i in range(lvl.created_at_index, len(df)):
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


def _is_impulse(df: pd.DataFrame, start: int, end: int, atr_value: float) -> Optional[str]:
    if end <= start or atr_value <= 0:
        return None
    move = df["close"].iloc[end] - df["close"].iloc[start]
    if abs(move) >= IMPULSE_ATR_MULT * atr_value:
        return "bullish" if move > 0 else "bearish"
    direction = None
    streak = 0
    for i in range(start + 1, end + 1):
        d = "bullish" if df["close"].iloc[i] > df["open"].iloc[i] else "bearish"
        if d == direction:
            streak += 1
        else:
            direction = d
            streak = 1
        if streak >= IMPULSE_CONSEC_BARS:
            return direction
    return None


def detect_order_blocks(df: pd.DataFrame, atr_series: pd.Series) -> list[OrderBlock]:
    out: list[OrderBlock] = []
    n = len(df)
    o = df["open"].values
    c = df["close"].values
    i = IMPULSE_BAR_WINDOW
    while i < n:
        a_val = atr_series.iloc[i] if not pd.isna(atr_series.iloc[i]) else 0
        impulse = _is_impulse(df, i - IMPULSE_BAR_WINDOW, i, float(a_val))
        if impulse:
            base_dir = "bullish" if impulse == "bearish" else "bearish"
            ob_idx = None
            for j in range(i - 1, max(i - IMPULSE_BAR_WINDOW - 5, -1), -1):
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
                    abs(c[i] - c[i - IMPULSE_BAR_WINDOW]) / max(float(a_val), 1e-9),
                    confirmed_at_index=i,
                ))
            i += IMPULSE_BAR_WINDOW
        else:
            i += 1
    _mark_ob_mitigation(df, out)
    return out


def _mark_ob_mitigation(df: pd.DataFrame, obs: list[OrderBlock]) -> None:
    """An OB is mitigated only after price has moved ≥ body away then returned."""
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


def detect_fvgs(df: pd.DataFrame) -> list[FVG]:
    out: list[FVG] = []
    high = df["high"].values
    low = df["low"].values
    for i in range(1, len(df) - 1):
        if low[i + 1] > high[i - 1]:
            out.append(FVG("bullish_fvg", float(low[i + 1]), float(high[i - 1]), i + 1))
        if high[i + 1] < low[i - 1]:
            out.append(FVG("bearish_fvg", float(low[i - 1]), float(high[i + 1]), i + 1))
    _update_fvg_fill(df, out)
    return out


def _update_fvg_fill(df: pd.DataFrame, fvgs: list[FVG]) -> None:
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


def killzone_at(ts: pd.Timestamp) -> list[str]:
    if ts.tz is None:
        ts = ts.tz_localize("UTC")
    ny = ts.tz_convert(NY_TZ)
    h = ny.hour
    active = []
    for name, (start_h, end_h) in KILLZONES_NY.items():
        if start_h <= end_h:
            if start_h <= h < end_h:
                active.append(name)
        else:
            if h >= start_h or h < end_h:
                active.append(name)
    return active


def in_killzones(ts: pd.Timestamp, names: list[str]) -> bool:
    a = killzone_at(ts)
    return any(n in a for n in names)


def in_ote(zone: PDZone, price: float, direction: str) -> bool:
    lo, hi = zone.ote(direction)
    return lo <= price <= hi


# ============================================================================
# SIGNAL + STRATEGY HELPERS
# ============================================================================

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


def _atr_at(atr_series: pd.Series, idx: int) -> float:
    if idx >= len(atr_series):
        return 0.0
    val = atr_series.iloc[idx]
    return float(val) if not pd.isna(val) else 0.0


def _next_opposite_liquidity(price, direction, levels, at_index):
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


def _next_persistent_liquidity(price, direction, levels, at_index):
    persistent = [l for l in levels if l.type in ("PDH", "PDL", "PWH", "PWL")]
    return _next_opposite_liquidity(price, direction, persistent, at_index)


def _cap_tp(entry, tp, direction, atr_value):
    if tp is None or atr_value <= 0 or TP_MAX_ATR_MULT <= 0:
        return tp
    max_dist = TP_MAX_ATR_MULT * atr_value
    if direction == "long":
        return min(tp, entry + max_dist)
    return max(tp, entry - max_dist)


def _floor_stop(entry, stop, direction, atr_value):
    """Minimum SL distance = max(MIN_SL_DIST_PCT * entry, MIN_SL_DIST_ATR * ATR).
    Identical to backtest/ict/strategies._floor_stop."""
    min_dist = max(MIN_SL_DIST_PCT * abs(entry), MIN_SL_DIST_ATR * atr_value)
    if direction == "long":
        return min(stop, entry - min_dist)
    return max(stop, entry + min_dist)


def _resolve_bias(structure_events, at_index, htf_bias_series):
    if htf_bias_series is not None and at_index < len(htf_bias_series):
        v = htf_bias_series.iloc[at_index]
        if isinstance(v, str):
            return v
    return htf_bias_lookup(structure_events, at_index)


def _expiry(at_index, expiry_bars):
    return at_index + (expiry_bars if expiry_bars is not None else ENTRY_EXPIRY_BARS)


def _ob_alive_at(ob, at_index):
    if ob.confirmed_at_index > at_index:
        return False
    if not ob.mitigated:
        return True
    return ob.mitigation_index is None or ob.mitigation_index > at_index


def _fvg_alive_at(fvg, at_index):
    return fvg.filled_at_index is None or fvg.filled_at_index > at_index


def _rr(entry, stop, target, direction):
    risk = abs(entry - stop)
    reward = abs(target - entry)
    if risk == 0:
        return 0.0
    valid = (direction == "long" and target > entry) or (direction == "short" and target < entry)
    return reward / risk if valid else 0.0


def build_geometry(df, bar_index, direction, entry,
                   structure_events, liquidity_levels, obs, fvgs, lookback=80):
    """Reconstruct the ICT decision geometry active at the signal bar so the UI
    can draw the FVG / Order-Block / swept-liquidity / BOS that framed the entry.

    READ-ONLY: never affects signal generation (called after a Signal is built).
    Returns a JSON-serializable dict; bar indices are resolved to unix seconds.
    Identical to backtest/engine.build_geometry (same detector dataclasses)."""
    idx = bar_index
    want_bull = direction == "long"

    def _ts(i):
        if i is None or i < 0 or i >= len(df.index):
            return None
        try:
            return int(df.index[i].timestamp())
        except Exception:
            return None

    geo = {}

    # entry zone: OB/FVG alive at idx, matching bias, that brackets (or is nearest to) entry
    cand = []
    for o in obs:
        if o.created_at_index > idx:
            continue
        if o.mitigated and o.mitigation_index is not None and o.mitigation_index <= idx:
            continue
        if (o.type == "bullish_ob") != want_bull:
            continue
        cand.append(("OB", float(o.top), float(o.bottom), o.created_at_index))
    for f in fvgs:
        if f.created_at_index > idx:
            continue
        if f.filled_at_index is not None and f.filled_at_index <= idx:
            continue
        if (f.type == "bullish_fvg") != want_bull:
            continue
        cand.append(("FVG", float(f.top), float(f.bottom), f.created_at_index))
    if cand:
        def _score(z):
            _, top, bot, _i = z
            contains = 0 if (bot <= entry <= top) else 1
            return (contains, abs((top + bot) / 2 - entry))
        kind, top, bot, cidx = min(cand, key=_score)
        geo["entry_zone"] = {"kind": kind, "top": top, "bottom": bot, "from": _ts(cidx)}

    # swept liquidity: most recent sweep within lookback before idx
    swept = [l for l in liquidity_levels
             if l.swept and l.swept_at_index is not None
             and idx - lookback <= l.swept_at_index <= idx]
    if swept:
        s = max(swept, key=lambda l: l.swept_at_index)
        geo["swept"] = {"type": s.type, "price": float(s.level),
                        "created": _ts(s.created_at_index), "swept": _ts(s.swept_at_index)}

    # structure break (CHoCH/BOS) most recent at/before idx
    sev = [e for e in structure_events
           if e.broken_at_index <= idx and idx - e.broken_at_index <= lookback]
    if sev:
        e = max(sev, key=lambda ev: ev.broken_at_index)
        geo["structure"] = {"type": e.type, "direction": e.direction,
                            "level": float(e.broken_level), "at": _ts(e.broken_at_index)}

    # nearest unswept opposite liquidity (the draw / TP target)
    tgt = None
    for l in liquidity_levels:
        if l.created_at_index > idx:
            continue
        if l.swept and l.swept_at_index is not None and l.swept_at_index <= idx:
            continue
        if direction == "long" and l.level > entry:
            tgt = l.level if tgt is None else min(tgt, l.level)
        elif direction == "short" and l.level < entry:
            tgt = l.level if tgt is None else max(tgt, l.level)
    if tgt is not None:
        geo["target_liquidity"] = float(tgt)

    return geo


def _overlap_pct(a_top, a_bot, b_top, b_bot):
    inter = max(0.0, min(a_top, b_top) - max(a_bot, b_bot))
    union = max(a_top, b_top) - min(a_bot, b_bot)
    return inter / union if union > 0 else 0.0


# ============================================================================
# STRATEGIES (A-E)
# ============================================================================

def strategy_a(symbol, df, at_index, atr_series, structure_events,
               liquidity_levels, obs, fvgs,
               htf_bias_series=None, expiry_bars=None):
    ts = df.index[at_index]
    if not in_killzones(ts, ["london_open", "ny_open", "silver_bullet_am", "silver_bullet_pm"]):
        return None
    bias = _resolve_bias(structure_events, at_index, htf_bias_series)
    if bias == "range":
        return None
    recent = [
        l for l in liquidity_levels
        if l.swept and l.swept_at_index is not None
        and at_index - SWEEP_LOOKBACK_BARS <= l.swept_at_index <= at_index
    ]
    if not recent:
        return None
    swept = recent[-1]

    choch = next(
        (e for e in structure_events
         if e.type == "CHoCH"
         and e.broken_at_index <= at_index
         and swept.swept_at_index <= e.broken_at_index <= swept.swept_at_index + CHOCH_AFTER_SWEEP_BARS
         and ((bias == "bullish" and e.direction == "bullish") or (bias == "bearish" and e.direction == "bearish"))),
        None
    )
    if not choch:
        return None

    impulse_window = range(swept.swept_at_index, choch.broken_at_index + 1)
    candidate_obs = [o for o in obs if o.created_at_index in impulse_window
                     and _ob_alive_at(o, at_index)
                     and ((bias == "bullish" and o.type == "bullish_ob") or (bias == "bearish" and o.type == "bearish_ob"))]
    candidate_fvgs = [f for f in fvgs if f.created_at_index in impulse_window
                      and _fvg_alive_at(f, at_index)
                      and ((bias == "bullish" and f.type == "bullish_fvg") or (bias == "bearish" and f.type == "bearish_fvg"))]
    if not candidate_obs and not candidate_fvgs:
        return None

    if candidate_obs:
        zone_top, zone_bot = candidate_obs[-1].top, candidate_obs[-1].bottom
    else:
        zone_top, zone_bot = candidate_fvgs[-1].top, candidate_fvgs[-1].bottom

    direction = "long" if bias == "bullish" else "short"
    entry = (zone_top + zone_bot) / 2
    a = _atr_at(atr_series, at_index)
    stop = (swept.sweep_extreme - SL_ATR_BUFFER * a) if direction == "long" else (swept.sweep_extreme + SL_ATR_BUFFER * a)
    stop = _floor_stop(entry, stop, direction, a)

    tp1 = _next_opposite_liquidity(entry, direction, liquidity_levels, at_index)
    tp1 = _cap_tp(entry, tp1, direction, a)
    tp2 = _next_persistent_liquidity(entry, direction, liquidity_levels, at_index)
    if tp1 is None:
        return None
    rr1 = _rr(entry, stop, tp1, direction)
    if rr1 < MIN_RR_DEFAULT:
        return None
    rr2 = _rr(entry, stop, tp2, direction) if tp2 is not None else None

    leg_high = max(swept.sweep_extreme, df["high"].iloc[choch.broken_at_index])
    leg_low = min(swept.sweep_extreme, df["low"].iloc[choch.broken_at_index])
    zone = PDZone(leg_high, leg_low)
    ote = in_ote(zone, entry, "bullish" if direction == "long" else "bearish")

    factors = ["htf_aligned", "liquidity_swept", "ltf_choch", "in_killzone"]
    if ote:
        factors.append("ote_zone")
    if (direction == "long" and zone.is_discount(entry)) or (direction == "short" and zone.is_premium(entry)):
        factors.append("discount_premium")

    return Signal(
        signal_id=str(uuid.uuid4()), timestamp=ts, strategy="A_liquidity_sweep_reversal",
        symbol=symbol, direction=direction,
        entry=float(entry), stop_loss=float(stop),
        take_profit_1=float(tp1), take_profit_2=float(tp2) if tp2 is not None else None,
        risk_reward_1=float(rr1), risk_reward_2=float(rr2) if rr2 is not None else None,
        quality="high" if ote else "medium", confluence_factors=factors,
        context={"htf_bias": bias, "swept_liquidity": swept.type, "ote_zone": ote, "killzone": killzone_at(ts)},
        expires_at_index=_expiry(at_index, expiry_bars), bar_index=at_index,
    )


def _asia_range_for(df, at_index):
    ts = df.index[at_index]
    ny = ts.tz_convert(NY_TZ) if ts.tz is not None else ts.tz_localize("UTC").tz_convert(NY_TZ)
    ny_today = ny.normalize()
    asia_start_ny = ny_today - pd.Timedelta(days=1) + pd.Timedelta(hours=19)
    asia_end_ny = ny_today
    asia_start = asia_start_ny.tz_convert("UTC")
    asia_end = asia_end_ny.tz_convert("UTC")
    mask = (df.index >= asia_start) & (df.index < asia_end)
    sub = df.loc[mask]
    if sub.empty:
        return None
    return float(sub["high"].max()), float(sub["low"].min()), df.index.get_loc(sub.index[0]), df.index.get_loc(sub.index[-1])


def strategy_b(symbol, df, at_index, atr_series, structure_events,
               liquidity_levels, obs, fvgs,
               htf_bias_series=None, expiry_bars=None):
    ts = df.index[at_index]
    if not in_killzones(ts, ["london_open", "ny_open"]):
        return None
    rng = _asia_range_for(df, at_index)
    if not rng:
        return None
    a_hi, a_lo, _, asia_end_i = rng
    a = _atr_at(atr_series, at_index)
    if a <= 0:
        return None
    if (a_hi - a_lo) > ASIA_RANGE_MAX_ATR * a:
        return None

    sweep_dir = None
    sweep_idx = None
    for j in range(asia_end_i + 1, at_index + 1):
        if df["high"].iloc[j] > a_hi and df["close"].iloc[j] < a_hi:
            sweep_dir, sweep_idx = "above", j
            break
        if df["low"].iloc[j] < a_lo and df["close"].iloc[j] > a_lo:
            sweep_dir, sweep_idx = "below", j
            break
    if sweep_dir is None:
        return None

    direction = "short" if sweep_dir == "above" else "long"
    choch = next(
        (e for e in structure_events
         if e.type == "CHoCH" and sweep_idx <= e.broken_at_index <= at_index
         and ((direction == "short" and e.direction == "bearish") or (direction == "long" and e.direction == "bullish"))),
        None
    )
    if not choch:
        return None

    impulse_range = range(sweep_idx, choch.broken_at_index + 1)
    candidate_obs = [o for o in obs if o.created_at_index in impulse_range
                     and _ob_alive_at(o, at_index)
                     and ((direction == "long" and o.type == "bullish_ob") or (direction == "short" and o.type == "bearish_ob"))]
    candidate_fvgs = [f for f in fvgs if f.created_at_index in impulse_range
                      and _fvg_alive_at(f, at_index)
                      and ((direction == "long" and f.type == "bullish_fvg") or (direction == "short" and f.type == "bearish_fvg"))]
    if not candidate_obs and not candidate_fvgs:
        return None

    if candidate_obs:
        zone_top, zone_bot = candidate_obs[-1].top, candidate_obs[-1].bottom
    else:
        zone_top, zone_bot = candidate_fvgs[-1].top, candidate_fvgs[-1].bottom

    entry = (zone_top + zone_bot) / 2
    sweep_extreme = float(df["high"].iloc[sweep_idx]) if sweep_dir == "above" else float(df["low"].iloc[sweep_idx])
    stop = (sweep_extreme + SL_ATR_BUFFER * a) if direction == "short" else (sweep_extreme - SL_ATR_BUFFER * a)
    stop = _floor_stop(entry, stop, direction, a)

    tp1 = a_lo if direction == "short" else a_hi
    tp1 = _cap_tp(entry, tp1, direction, a)
    tp2 = _next_persistent_liquidity(entry, direction, liquidity_levels, at_index)
    rr1 = _rr(entry, stop, tp1, direction)
    if rr1 < MIN_RR_DEFAULT:
        return None
    rr2 = _rr(entry, stop, tp2, direction) if tp2 is not None else None

    factors = ["liquidity_swept", "ltf_choch", "in_killzone", "power_of_three"]
    bias_now = _resolve_bias(structure_events, at_index, htf_bias_series)
    if (direction == "long" and bias_now == "bullish") or (direction == "short" and bias_now == "bearish"):
        factors.append("htf_aligned")

    return Signal(
        signal_id=str(uuid.uuid4()), timestamp=ts, strategy="B_power_of_three",
        symbol=symbol, direction=direction,
        entry=float(entry), stop_loss=float(stop),
        take_profit_1=float(tp1), take_profit_2=float(tp2) if tp2 is not None else None,
        risk_reward_1=float(rr1), risk_reward_2=float(rr2) if rr2 is not None else None,
        quality="medium", confluence_factors=factors,
        context={"asia_high": a_hi, "asia_low": a_lo, "sweep_dir": sweep_dir, "killzone": killzone_at(ts)},
        expires_at_index=_expiry(at_index, expiry_bars), bar_index=at_index,
    )


def strategy_c(symbol, df, at_index, atr_series, structure_events,
               liquidity_levels, obs, fvgs,
               htf_bias_series=None, expiry_bars=None):
    bias = _resolve_bias(structure_events, at_index, htf_bias_series)
    if bias == "range":
        return None
    bos_seq = [e for e in structure_events if e.type == "BOS" and e.broken_at_index <= at_index]
    if len(bos_seq) < 2 or bos_seq[-1].direction != bos_seq[-2].direction:
        return None

    direction = "long" if bias == "bullish" else "short"
    side = "bullish" if direction == "long" else "bearish"
    a = _atr_at(atr_series, at_index)
    if a <= 0:
        return None
    price = float(df["close"].iloc[at_index])
    age_floor = at_index - ZONE_MAX_AGE_BARS
    valid_obs = [o for o in obs if age_floor <= o.created_at_index <= at_index
                 and _ob_alive_at(o, at_index) and o.type == f"{side}_ob"]
    valid_fvgs = [f for f in fvgs if age_floor <= f.created_at_index <= at_index
                  and _fvg_alive_at(f, at_index) and f.type == f"{side}_fvg"]

    best = None
    for o in valid_obs:
        for f in valid_fvgs:
            ovl = _overlap_pct(o.top, o.bottom, f.top, f.bottom)
            if ovl >= OB_FVG_OVERLAP_MIN:
                top = max(o.top, f.top)
                bot = min(o.bottom, f.bottom)
                mid = (top + bot) / 2
                dist = abs(price - mid)
                if best is None or dist < best[0]:
                    best = (dist, ovl, top, bot)
    if not best:
        return None
    dist, _, top, bot = best
    if dist > STRAT_C_PROXIMITY_ATR * a:
        return None

    entry = bot if direction == "long" else top
    stop = (bot - SL_ATR_BUFFER_C * a) if direction == "long" else (top + SL_ATR_BUFFER_C * a)
    stop = _floor_stop(entry, stop, direction, a)
    tp1 = _next_opposite_liquidity(entry, direction, liquidity_levels, at_index)
    tp1 = _cap_tp(entry, tp1, direction, a)
    tp2 = _next_persistent_liquidity(entry, direction, liquidity_levels, at_index)
    if tp1 is None:
        return None
    rr1 = _rr(entry, stop, tp1, direction)
    if rr1 < MIN_RR_DEFAULT:
        return None
    rr2 = _rr(entry, stop, tp2, direction) if tp2 is not None else None

    factors = ["htf_aligned", "ob_fvg_overlap"]
    if in_killzones(df.index[at_index], ["london_open", "ny_open"]):
        factors.append("in_killzone")

    return Signal(
        signal_id=str(uuid.uuid4()), timestamp=df.index[at_index], strategy="C_fvg_ob_confluence",
        symbol=symbol, direction=direction,
        entry=float(entry), stop_loss=float(stop),
        take_profit_1=float(tp1), take_profit_2=float(tp2) if tp2 is not None else None,
        risk_reward_1=float(rr1), risk_reward_2=float(rr2) if rr2 is not None else None,
        quality="high", confluence_factors=factors,
        context={"htf_bias": bias, "killzone": killzone_at(df.index[at_index])},
        expires_at_index=_expiry(at_index, expiry_bars), bar_index=at_index,
    )


def strategy_d(symbol, df, at_index, atr_series, structure_events,
               liquidity_levels, obs, fvgs,
               htf_bias_series=None, expiry_bars=None):
    if symbol in D_EXCLUDE_SYMBOLS:
        return None
    ts = df.index[at_index]
    if not in_killzones(ts, ["silver_bullet_am", "silver_bullet_pm"]):
        return None
    bias = _resolve_bias(structure_events, at_index, htf_bias_series)
    if bias == "range":
        return None
    direction = "long" if bias == "bullish" else "short"
    side = "bullish" if direction == "long" else "bearish"

    sweep = next(
        (l for l in liquidity_levels
         if l.swept and l.swept_at_index is not None
         and at_index - 60 <= l.swept_at_index <= at_index),
        None
    )
    if not sweep:
        return None

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
    stop = (fvg.bottom - SL_ATR_BUFFER * a) if direction == "long" else (fvg.top + SL_ATR_BUFFER * a)
    stop = _floor_stop(entry, stop, direction, a)

    tp1 = _next_opposite_liquidity(entry, direction, liquidity_levels, at_index)
    tp1 = _cap_tp(entry, tp1, direction, a)
    tp2 = _next_persistent_liquidity(entry, direction, liquidity_levels, at_index)
    if tp1 is None:
        return None
    rr1 = _rr(entry, stop, tp1, direction)
    if rr1 < MIN_RR_SILVER_BULLET:
        return None
    rr2 = _rr(entry, stop, tp2, direction) if tp2 is not None else None

    return Signal(
        signal_id=str(uuid.uuid4()), timestamp=ts, strategy="D_silver_bullet",
        symbol=symbol, direction=direction,
        entry=float(entry), stop_loss=float(stop),
        take_profit_1=float(tp1), take_profit_2=float(tp2) if tp2 is not None else None,
        risk_reward_1=float(rr1), risk_reward_2=float(rr2) if rr2 is not None else None,
        quality="high",
        confluence_factors=["htf_aligned", "liquidity_swept", "silver_bullet", "in_killzone"],
        context={"htf_bias": bias, "killzone": killzone_at(ts), "sweep_type": sweep.type},
        expires_at_index=_expiry(at_index, expiry_bars), bar_index=at_index,
    )


def strategy_e(symbol, df, at_index, atr_series, structure_events,
               liquidity_levels, obs, fvgs,
               htf_bias_series=None, expiry_bars=None):
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
    candidate_obs = [o for o in obs if o.created_at_index in impulse_range
                     and _ob_alive_at(o, at_index) and o.type == f"{side}_ob"]
    candidate_fvgs = [f for f in fvgs if f.created_at_index in impulse_range
                      and _fvg_alive_at(f, at_index) and f.type == f"{side}_fvg"]
    if not candidate_obs and not candidate_fvgs:
        return None

    if candidate_obs:
        zone_top, zone_bot = candidate_obs[-1].top, candidate_obs[-1].bottom
    else:
        zone_top, zone_bot = candidate_fvgs[-1].top, candidate_fvgs[-1].bottom

    entry = (zone_top + zone_bot) / 2
    a = _atr_at(atr_series, at_index)
    if a <= 0:
        return None
    stop = (swept.sweep_extreme - SL_ATR_BUFFER * a) if direction == "long" else (swept.sweep_extreme + SL_ATR_BUFFER * a)
    stop = _floor_stop(entry, stop, direction, a)

    tp1 = _next_opposite_liquidity(entry, direction, liquidity_levels, at_index)
    tp1 = _cap_tp(entry, tp1, direction, a)
    tp2 = _next_persistent_liquidity(entry, direction, liquidity_levels, at_index)
    if tp1 is None:
        return None
    rr1 = _rr(entry, stop, tp1, direction)
    if rr1 < MIN_RR_DEFAULT:
        return None
    rr2 = _rr(entry, stop, tp2, direction) if tp2 is not None else None

    return Signal(
        signal_id=str(uuid.uuid4()), timestamp=ts, strategy="E_eqh_eql_run",
        symbol=symbol, direction=direction,
        entry=float(entry), stop_loss=float(stop),
        take_profit_1=float(tp1), take_profit_2=float(tp2) if tp2 is not None else None,
        risk_reward_1=float(rr1), risk_reward_2=float(rr2) if rr2 is not None else None,
        quality="medium",
        confluence_factors=["htf_aligned", "eqh_eql_swept", "in_killzone"],
        context={"htf_bias": bias, "killzone": killzone_at(ts), "swept": swept.type},
        expires_at_index=_expiry(at_index, expiry_bars), bar_index=at_index,
    )


# ------------- Strategy F: Vol-Compression Donchian Breakout (RADAR / v3) -------------
# Mirrors backtest/ict/strategies.py strategy_f 1:1 (keep the two bodies textually
# aligned like A-E). Trend-continuation: LONG when a 1h close breaks the prior-120-bar
# Donchian high out of below-average volatility (SHORT mirrored), entered as a RETEST
# LIMIT at the broken channel level — run_engine only accepts retrace-limit entries.
# Ignores the ICT detectors entirely; the signature is kept for run_engine compatibility.

_RADAR_CACHE: dict = {}
_RADAR_CACHE_MAX = 8   # bounded: live scan churns ~21 dfs per pass


def _radar_features(df: pd.DataFrame) -> dict:
    """All rolling series strategy_f needs, computed once per DataFrame.

    Every window is CAUSAL (shift(1) before rolling for the channel / volume median;
    ATR at i uses only the closed bar i) so test_no_lookahead passes by construction,
    and the raw breakout series depend only on df — never on which signals survived
    dedup — so the re-fire cooldown is window-stable (test_dag_parity)."""
    key = (id(df), len(df), int(df.index[0].value), int(df.index[-1].value))
    feats = _RADAR_CACHE.get(key)
    if feats is not None:
        return feats
    high, low, close, vol = df["high"], df["low"], df["close"], df["volume"]
    L = RADAR_DONCHIAN_LOOKBACK
    # Channel of the PRIOR L bars [i-L, i-1] — shift(1) excludes the fire bar.
    dc_hi = high.shift(1).rolling(L, min_periods=L).max()
    dc_lo = low.shift(1).rolling(L, min_periods=L).min()
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(),
                    (low - prev_close).abs()], axis=1).max(axis=1)  # same TR as atr()
    atr24 = tr.rolling(RADAR_ATR_PERIOD, min_periods=RADAR_ATR_PERIOD).mean()
    atr24_sma = atr24.rolling(RADAR_COMPRESSION_SMA, min_periods=RADAR_COMPRESSION_SMA).mean()
    ema200 = close.ewm(span=RADAR_EMA_PERIOD, adjust=False).mean()
    vol_med = vol.shift(1).rolling(RADAR_VOL_MEDIAN_BARS, min_periods=RADAR_VOL_MEDIAN_BARS).median()
    # Raw trigger series for the re-fire cooldown (NaN channel compares False).
    brk_up = close > dc_hi
    brk_dn = close < dc_lo
    feats = {"dc_hi": dc_hi, "dc_lo": dc_lo, "atr24": atr24, "atr24_sma": atr24_sma,
             "ema200": ema200, "vol_med": vol_med, "brk_up": brk_up, "brk_dn": brk_dn}
    if len(_RADAR_CACHE) >= _RADAR_CACHE_MAX:
        _RADAR_CACHE.pop(next(iter(_RADAR_CACHE)))
    _RADAR_CACHE[key] = feats
    return feats


def strategy_f(symbol, df, at_index, atr_series, structure_events,
               liquidity_levels, obs, fvgs,
               htf_bias_series=None, expiry_bars=None):
    """F: 120-bar Donchian breakout from volatility compression, retest-limit entry.

    `expiry_bars` (engine default = 3) is deliberately IGNORED: a retest limit
    needs RADAR_ENTRY_EXPIRY_BARS (24h) to fill."""
    i = at_index
    if i < 1 or i >= len(df):
        return None
    f = _radar_features(df)
    dc_hi, dc_lo = f["dc_hi"].iloc[i], f["dc_lo"].iloc[i]
    a24 = f["atr24"].iloc[i]
    a24_prev, sma_prev = f["atr24"].iloc[i - 1], f["atr24_sma"].iloc[i - 1]
    vmed = f["vol_med"].iloc[i]
    ema = f["ema200"].iloc[i]
    if any(pd.isna(x) for x in (dc_hi, dc_lo, a24, a24_prev, sma_prev, vmed)):
        return None   # warmup: first valid fire bar needs ~264 bars of history
    if a24 <= 0 or sma_prev <= 0 or vmed <= 0:
        return None

    close = float(df["close"].iloc[i])
    volume = float(df["volume"].iloc[i])

    # --- trigger: close breaks the prior-120-bar channel ---
    if close > float(dc_hi):
        direction, level = "long", float(dc_hi)
    elif close < float(dc_lo):
        direction, level = "short", float(dc_lo)
    else:
        return None

    # --- filter 1: compression — breakout must emerge from below-average vol ---
    comp_ratio = float(a24_prev) / float(sma_prev)
    if not (comp_ratio < RADAR_COMPRESSION_MAX):
        return None
    # --- filter 2: volume surge on the breakout bar ---
    vol_ratio = volume / float(vmed)
    if not (vol_ratio > RADAR_VOL_SURGE_MIN):
        return None
    # --- filter 3: regime — trade only with the EMA200 side ---
    if direction == "long" and not (close > float(ema)):
        return None
    if direction == "short" and not (close < float(ema)):
        return None
    # --- anti-chase: runaway bars won't retest the broken level ---
    if abs(close - level) > RADAR_CHASE_MAX_ATR * float(a24):
        return None
    # --- re-fire cooldown on the RAW trigger series: after a breakout the channel
    # ratchets with price, so dedup's 0.05% entry tolerance alone would not
    # suppress consecutive-bar breakouts at new levels. ---
    lo = max(0, i - RADAR_REFIRE_BARS)
    trig = f["brk_up"] if direction == "long" else f["brk_dn"]
    if bool(trig.iloc[lo:i].any()):
        return None

    entry = level
    stop = entry - RADAR_SL_ATR_MULT * float(a24) if direction == "long" \
        else entry + RADAR_SL_ATR_MULT * float(a24)
    stop = _floor_stop(entry, stop, direction, float(a24))   # floor never binds at 2.5 ATR
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    tp1 = entry + RADAR_TP_R_MULT * risk if direction == "long" \
        else entry - RADAR_TP_R_MULT * risk
    # Deliberately NOT _cap_tp(): 3R = 7.5xATR24 exceeds TP_MAX_ATR_MULT(4)xATR and
    # would be clipped to ~1.6R. The target is ATR-scaled by construction.

    factors = ["regime_aligned", "vol_compression", "volume_surge"]   # 3+2+2 = 7 >= publish(6)
    if comp_ratio < RADAR_DEEP_COMPRESSION:
        factors.append("deep_compression")    # +1
    if vol_ratio >= RADAR_STRONG_VOLUME:
        factors.append("strong_volume")       # +1 -> 9 = CONFLUENCE_HIGH

    return Signal(
        signal_id=str(uuid.uuid4()), timestamp=df.index[i], strategy="F_compression_breakout",
        symbol=symbol, direction=direction,
        entry=float(entry), stop_loss=float(stop),
        take_profit_1=float(tp1), take_profit_2=None,
        risk_reward_1=float(_rr(entry, stop, tp1, direction)), risk_reward_2=None,
        quality="medium",                      # merge_same_bar re-derives from the score
        confluence_factors=factors,
        context={
            "donchian_high": float(dc_hi), "donchian_low": float(dc_lo),
            "atr24": float(a24),
            "compression_ratio": round(comp_ratio, 4),
            "volume_ratio": round(vol_ratio, 2),
            "ema200": float(ema),
            "regime_dist_atr": round(abs(close - float(ema)) / float(a24), 2),
            "breakout_ext_atr": round(abs(close - level) / float(a24), 2),
        },
        expires_at_index=i + RADAR_ENTRY_EXPIRY_BARS,   # 24h retest window
        bar_index=i,
    )


# ------------- Strategy G: Funding-Extreme Squeeze Fade (SQUEEZE / v4) -------------
# Mirrors backtest/ict/strategies.py strategy_g 1:1 (keep the two bodies textually
# aligned like A-F). Derivative-positioning stream: extreme perp funding marks a
# CROWDED side; G fades the crowd once price ignites against it (very negative
# funding = crowded shorts -> LONG on an up-ignition bar; positive extreme mirrored
# SHORT). Entry is a retrace limit RETRACE_ATR inside the ignition close — engine-
# compatible by construction. Ignores the ICT detectors entirely.
# Funding plumbing: run_squeeze_scan registers each symbol's settled funding via
# set_funding() BEFORE run_engine; without a registration G stays silent.

_FUNDING: dict = {}          # symbol -> df(index=fundingTime, col 'rate')
_SQUEEZE_CACHE: dict = {}
_SQUEEZE_CACHE_MAX = 8   # bounded: live scan churns ~21 dfs per pass


def set_funding(symbol: str, fdf: pd.DataFrame) -> None:
    """Register settled funding events for `symbol` (index=UTC fundingTime, col 'rate').
    Replaces any prior registration and invalidates cached squeeze features."""
    if fdf is None or fdf.empty:
        _FUNDING.pop(symbol, None)
    else:
        f = fdf.copy()
        if f.index.tz is None:
            f.index = f.index.tz_localize("UTC")
        _FUNDING[symbol] = f.sort_index()
    for k in [k for k in _SQUEEZE_CACHE if k[0] == symbol]:
        _SQUEEZE_CACHE.pop(k, None)


def _squeeze_features(symbol: str, df: pd.DataFrame) -> Optional[dict]:
    """Funding + ATR series strategy_g needs, aligned to df bars, computed once per
    (symbol, df). All funding-derived values at bar i use only events SETTLED by
    bar i's close, and each event's percentile rank uses only PRIOR events
    (shift(1) before the time-window rolling), so test_no_lookahead passes by
    construction. The raw ignition/extreme trigger series depend only on df +
    the registered funding — never on which signals survived dedup — so the
    re-fire cooldown is window-stable (test_dag_parity)."""
    fdf = _FUNDING.get(symbol)
    if fdf is None or len(fdf) < 3:
        return None
    key = (symbol, id(df), len(df), int(df.index[0].value), int(df.index[-1].value))
    feats = _SQUEEZE_CACHE.get(key)
    if feats is not None:
        return feats

    rate = fdf["rate"]
    # Normalize each event to an 8h-equivalent using its ACTUAL spacing (4h-settled
    # symbols would otherwise look half as crowded). First event has no spacing ->
    # NaN -> excluded from triggers and the percentile distribution alike.
    gap_h = rate.index.to_series().diff().dt.total_seconds() / 3600.0
    gap_h = gap_h.where((gap_h > 0) & (gap_h <= 24.0))
    r8 = rate * (8.0 / gap_h)
    # Crowding percentile of PRIOR events in the trailing window. shift(1) moves
    # event k-1's value onto event k's timestamp, so the time-window rolling at
    # event k sees exactly the events in (t_k - window, t_k) — current excluded.
    prior = r8.shift(1)
    q_lo = prior.rolling(SQUEEZE_PCTL_WINDOW, min_periods=SQUEEZE_MIN_EVENTS) \
                .quantile(1.0 - SQUEEZE_PCTL)
    q_hi = prior.rolling(SQUEEZE_PCTL_WINDOW, min_periods=SQUEEZE_MIN_EVENTS) \
                .quantile(SQUEEZE_PCTL)
    n_prior = prior.rolling(SQUEEZE_PCTL_WINDOW, min_periods=1).count()
    r8_prev = r8.shift(1)

    # As-of alignment onto BAR CLOSES (bar i fires at its close = open + bar dur).
    bar_dur = df.index[1] - df.index[0] if len(df) > 1 else pd.Timedelta(hours=1)
    closes = df.index + bar_dur
    ev = pd.DataFrame({
        "t": rate.index, "r8": r8.values, "q_lo": q_lo.values, "q_hi": q_hi.values,
        "n_prior": n_prior.values, "r8_prev": r8_prev.values,
        "event_time": rate.index,
    })
    al = pd.merge_asof(pd.DataFrame({"t": closes}), ev, on="t", direction="backward")
    al.index = df.index
    age_h = (closes - al["event_time"]).dt.total_seconds() / 3600.0
    age_h.index = df.index

    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(),
                    (low - prev_close).abs()], axis=1).max(axis=1)
    atr24 = tr.rolling(SQUEEZE_ATR_PERIOD, min_periods=SQUEEZE_ATR_PERIOD).mean()

    # Raw per-bar trigger series for the re-fire cooldown (NaNs compare False).
    valid = (al["n_prior"] >= SQUEEZE_MIN_EVENTS) & (age_h <= SQUEEZE_STALE_HOURS)
    body = close - df["open"]
    ign_up = body >= SQUEEZE_IGNITION_ATR * atr24
    ign_dn = -body >= SQUEEZE_IGNITION_ATR * atr24
    ext_lo = (al["r8"] <= -SQUEEZE_ABS_MIN_8H) & (al["r8"] <= al["q_lo"])
    ext_hi = (al["r8"] >= SQUEEZE_ABS_MIN_8H) & (al["r8"] >= al["q_hi"])
    trig_long = (valid & ext_lo & ign_up).fillna(False)
    trig_short = (valid & ext_hi & ign_dn).fillna(False)

    feats = {"r8": al["r8"], "q_lo": al["q_lo"], "q_hi": al["q_hi"],
             "n_prior": al["n_prior"], "r8_prev": al["r8_prev"], "age_h": age_h,
             "atr24": atr24, "trig_long": trig_long, "trig_short": trig_short}
    if len(_SQUEEZE_CACHE) >= _SQUEEZE_CACHE_MAX:
        _SQUEEZE_CACHE.pop(next(iter(_SQUEEZE_CACHE)))
    _SQUEEZE_CACHE[key] = feats
    return feats


def strategy_g(symbol, df, at_index, atr_series, structure_events,
               liquidity_levels, obs, fvgs,
               htf_bias_series=None, expiry_bars=None):
    """G: fade extreme funding (crowded positioning) on a squeeze-ignition bar.

    `expiry_bars` (engine default = 3) is deliberately IGNORED: the retrace limit
    gets SQUEEZE_ENTRY_EXPIRY_BARS (12h) to fill."""
    i = at_index
    if i < 1 or i >= len(df):
        return None
    f = _squeeze_features(symbol, df)
    if f is None:
        return None
    a24 = f["atr24"].iloc[i]
    r8 = f["r8"].iloc[i]
    if pd.isna(a24) or a24 <= 0 or pd.isna(r8):
        return None
    if f["trig_long"].iloc[i]:
        direction = "long"
    elif f["trig_short"].iloc[i]:
        direction = "short"
    else:
        return None
    # --- re-fire cooldown on the RAW trigger series: funding stays extreme for
    # many consecutive bars, so dedup's entry tolerance alone can't suppress the
    # same crowding episode re-firing at drifting prices. ---
    lo = max(0, i - SQUEEZE_REFIRE_BARS)
    trig = f["trig_long"] if direction == "long" else f["trig_short"]
    if bool(trig.iloc[lo:i].any()):
        return None

    close = float(df["close"].iloc[i])
    a24 = float(a24)
    entry = close - SQUEEZE_RETRACE_ATR * a24 if direction == "long" \
        else close + SQUEEZE_RETRACE_ATR * a24
    stop = entry - SQUEEZE_SL_ATR_MULT * a24 if direction == "long" \
        else entry + SQUEEZE_SL_ATR_MULT * a24
    stop = _floor_stop(entry, stop, direction, a24)   # floor never binds at 2.0 ATR
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    tp1 = entry + SQUEEZE_TP_R_MULT * risk if direction == "long" \
        else entry - SQUEEZE_TP_R_MULT * risk
    # Deliberately NOT _cap_tp(): 2R = 4.7xATR24 in entry terms; the target is
    # ATR-scaled by construction, the generic 4xATR14 clip would distort it.

    r8f = float(r8)
    factors = ["funding_extreme", "crowding_percentile", "squeeze_ignition"]  # 3+2+2=7
    if abs(r8f) >= SQUEEZE_SEVERE_8H:
        factors.append("funding_severe")     # +1
    r8_prev = f["r8_prev"].iloc[i]
    if not pd.isna(r8_prev) and abs(r8f) < abs(float(r8_prev)):
        factors.append("funding_unwind")     # +1 -> 9 = CONFLUENCE_HIGH

    return Signal(
        signal_id=str(uuid.uuid4()), timestamp=df.index[i], strategy="G_funding_squeeze_fade",
        symbol=symbol, direction=direction,
        entry=float(entry), stop_loss=float(stop),
        take_profit_1=float(tp1), take_profit_2=None,
        risk_reward_1=float(_rr(entry, stop, tp1, direction)), risk_reward_2=None,
        quality="medium",                      # merge_same_bar re-derives from the score
        confluence_factors=factors,
        context={
            "funding_8h": round(r8f, 6),
            "funding_prev_8h": None if pd.isna(r8_prev) else round(float(r8_prev), 6),
            "crowding_q_lo": None if pd.isna(f["q_lo"].iloc[i]) else round(float(f["q_lo"].iloc[i]), 6),
            "crowding_q_hi": None if pd.isna(f["q_hi"].iloc[i]) else round(float(f["q_hi"].iloc[i]), 6),
            "funding_age_h": round(float(f["age_h"].iloc[i]), 2),
            "atr24": a24,
            "ignition_atr": round(float(df["close"].iloc[i] - df["open"].iloc[i]) / a24, 2),
        },
        expires_at_index=i + SQUEEZE_ENTRY_EXPIRY_BARS,   # 12h fill window
        bar_index=i,
    )


# Production: strategy_a (liquidity sweep reversal) excluded — backtest
# showed it consistently net-negative on both 2025 (-37R) and 2026 (-11R).
# All function definitions stay above so they can be re-enabled by simply
# adding `strategy_a` back to this list.
STRATEGIES = [strategy_b, strategy_c, strategy_d, strategy_e]

# PULSE (15m) runs Strategy C only — the lone strategy with a real edge on 15m
# (2026 v1-15m backtest: +754R, +0.64R/trade; B/D were net-flat-to-negative).
PULSE_STRATEGIES = [strategy_c]

# IMPULSE (v2) runs B/C/D — strategy E dropped (0 signals in all of 2026, verified
# inert by ablation). The extra D symbol-exclusion is applied process-locally in
# run_impulse_scan (impulse runs as its own process, so main is unaffected).
IMPULSE_STRATEGIES = [strategy_b, strategy_c, strategy_d]

# RADAR (v3) runs ONLY strategy F (vol-compression Donchian breakout).
RADAR_STRATEGIES = [strategy_f]

# SQUEEZE (v4) runs ONLY strategy G (funding-extreme squeeze fade).
SQUEEZE_STRATEGIES = [strategy_g]


# ============================================================================
# CONFLUENCE
# ============================================================================

def _score(sig: Signal) -> int:
    return sum(CONFLUENCE_WEIGHTS.get(f, 0) for f in sig.confluence_factors)


def merge_same_bar(signals: list[Signal]) -> list[Signal]:
    if not signals:
        return []
    by_key = defaultdict(list)
    for s in signals:
        by_key[(s.symbol, s.bar_index)].append(s)

    out = []
    for (symbol, bar_idx), group in by_key.items():
        longs = [s for s in group if s.direction == "long"]
        shorts = [s for s in group if s.direction == "short"]
        for direction_group in (longs, shorts):
            if not direction_group:
                continue
            scored = [(_score(s) + (CONFLUENCE_WEIGHTS["multi_strategy"] if len(direction_group) > 1 else 0), s)
                      for s in direction_group]
            scored.sort(key=lambda x: x[0], reverse=True)
            top_score = scored[0][0]
            top_signal = scored[0][1]
            top_signal.confluence_score = min(top_score, CONFLUENCE_MAX)
            if len(direction_group) > 1:
                top_signal.strategy = "composite"
                top_signal.context["composing_strategies"] = [s.strategy for s in direction_group]
                if "multi_strategy" not in top_signal.confluence_factors:
                    top_signal.confluence_factors.append("multi_strategy")
            if top_signal.confluence_score >= CONFLUENCE_HIGH:
                top_signal.quality = "high"
            elif top_signal.confluence_score >= CONFLUENCE_MIN_PUBLISH:
                top_signal.quality = "medium"
            else:
                continue
            out.append(top_signal)

        if longs and shorts:
            l_top = max((_score(s) for s in longs), default=0)
            s_top = max((_score(s) for s in shorts), default=0)
            if l_top == s_top:
                out = [o for o in out if not (o.symbol == symbol and o.bar_index == bar_idx)]
    return out


# ============================================================================
# ENGINE
# ============================================================================

def dedup_zone_signals(signals: list, bar_minutes: float) -> list:
    """One zone = one trade: drop a signal when another signal with the same
    direction and ~the same entry fired within the previous cooldown window.

    Window-stable: the verdict at bar i depends only on RAW emissions in
    [i - cooldown, i) — dropped ones included — so the live scan (which covers
    the cooldown window before the last bar) reproduces the full-history
    backtest result exactly. Identical to backtest/engine.dedup_zone_signals."""
    if not signals or DEDUP_COOLDOWN_MINUTES <= 0 or bar_minutes <= 0:
        return signals
    cooldown = max(1, int(DEDUP_COOLDOWN_MINUTES / bar_minutes))
    out = []
    seen = []
    for s in sorted(signals, key=lambda x: x.bar_index):
        dup = any(
            d == s.direction and 0 < s.bar_index - b <= cooldown
            and abs(s.entry - e) <= DEDUP_ENTRY_TOL_PCT * abs(e)
            for (b, d, e) in seen
        )
        seen.append((s.bar_index, s.direction, s.entry))
        if not dup:
            out.append(s)
    return out


@dataclass
class DetectorBundle:
    df: pd.DataFrame
    atr: pd.Series
    swings: list = field(default_factory=list)
    structure: list = field(default_factory=list)
    liquidity: list = field(default_factory=list)
    order_blocks: list = field(default_factory=list)
    fvgs: list = field(default_factory=list)
    htf_bias_series: Optional[pd.Series] = None
    expiry_bars: int = ENTRY_EXPIRY_BARS


def _bar_minutes(df: pd.DataFrame) -> float:
    if len(df) < 2:
        return 60.0
    return float((df.index[1] - df.index[0]).total_seconds()) / 60.0


def _compute_htf_bias_series(df: pd.DataFrame, htf_rule: str = HTF_RULE) -> pd.Series:
    df_htf = aggregate(df, htf_rule)
    if df_htf.empty:
        return pd.Series(["range"] * len(df), index=df.index)
    htf_swings = detect_swings(df_htf, n=SWING_N_HTF)
    htf_structure = detect_structure(df_htf, htf_swings)
    bias_per_htf_bar = [htf_bias_lookup(htf_structure, i) for i in range(len(df_htf))]
    htf_bias_at_htf = pd.Series(bias_per_htf_bar, index=df_htf.index)
    return htf_bias_at_htf.reindex(df.index, method="ffill").fillna("range")


def build_detectors(df: pd.DataFrame, htf_rule: str = HTF_RULE) -> DetectorBundle:
    a = atr(df, ATR_PERIOD)
    sw = detect_swings(df, n=SWING_N_ITF)
    st = detect_structure(df, sw)
    pl = detect_persistent_liquidity(df)
    eq = detect_equal_levels(sw, a)
    levels = pl + eq
    mark_sweeps(df, levels)
    obs = detect_order_blocks(df, a)
    fv = detect_fvgs(df)
    htf_series = _compute_htf_bias_series(df, htf_rule)
    bm = _bar_minutes(df)
    expiry = max(2, int(EXPIRY_MINUTES / bm)) if bm > 0 else ENTRY_EXPIRY_BARS
    return DetectorBundle(df=df, atr=a, swings=sw, structure=st,
                          liquidity=levels, order_blocks=obs, fvgs=fv,
                          htf_bias_series=htf_series, expiry_bars=expiry)


def run_engine(symbol: str, df: pd.DataFrame, *,
               start_index: Optional[int] = None,
               end_index: Optional[int] = None,
               strategies: Optional[list] = None,
               htf_rule: str = HTF_RULE) -> list[Signal]:
    bundle = build_detectors(df, htf_rule=htf_rule)
    strats = strategies if strategies is not None else STRATEGIES
    n = len(df)
    if start_index is None:
        start_index = max(ATR_PERIOD + 5, SWING_N_ITF + 5)
    if end_index is None:
        end_index = n - 1
    raw: list[Signal] = []
    for i in range(start_index, end_index + 1):
        for strat_fn in strats:
            try:
                sig = strat_fn(symbol, df, i, bundle.atr, bundle.structure,
                               bundle.liquidity, bundle.order_blocks, bundle.fvgs,
                               htf_bias_series=bundle.htf_bias_series,
                               expiry_bars=bundle.expiry_bars)
            except Exception:
                continue
            if sig is not None:
                # Pending-limit validity: at fire (bar CLOSE) price must be on the
                # retrace side of the entry limit (LONG: close>entry, SHORT: close<entry).
                # Drop "already-passed" setups where price is already through the entry.
                try:
                    _c = float(df["close"].iloc[sig.bar_index])
                    if (_c <= sig.entry) if sig.direction == "long" else (_c >= sig.entry):
                        continue
                except Exception:
                    pass
                try:
                    sig.context["geometry"] = build_geometry(
                        df, sig.bar_index, sig.direction, sig.entry,
                        bundle.structure, bundle.liquidity, bundle.order_blocks, bundle.fvgs)
                except Exception:
                    pass
                raw.append(sig)
    return dedup_zone_signals(merge_same_bar(raw), _bar_minutes(df))


# ============================================================================
# AIRFLOW INFRASTRUCTURE — DB + Telegram + per-symbol runner
# ============================================================================

def send_telegram_message(text_msg: str, chat_id: Optional[str] = None):
    cid = chat_id or TELEGRAM_CHAT_ID
    if not (TELEGRAM_BOT_TOKEN and cid):
        print("  telegram skipped (TELEGRAM_BOT_TOKEN/CHAT_ID not set)")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": cid, "text": text_msg, "parse_mode": "HTML"}
    try:
        response = requests.post(url, json=payload, timeout=15)
        if not response.ok:
            print("Telegram error:", response.text[:200])
    except Exception as e:
        print("Telegram exception:", e)


def get_db_engine():
    return create_engine(DB_CONNECTION_STRING)


def signal_already_exists(conn, symbol: str, signal_time, direction: str, mode: str) -> bool:
    # mode-aware: a 15m 'pulse' signal and a 1h 'live' signal on the same symbol +
    # bar-open + direction are DISTINCT signals and must not dedup against each other.
    q = text("""
        SELECT 1 FROM ict_trade.signals
        WHERE symbol = :symbol AND signal_time = :signal_time
          AND direction = :direction AND mode = :mode
        LIMIT 1
    """)
    return conn.execute(q, {
        "symbol": symbol, "signal_time": signal_time, "direction": direction, "mode": mode,
    }).fetchone() is not None


def save_signal_to_db(sig: Signal, is_dynamic: bool = False, *,
                      mode: Optional[str] = None, ltf: Optional[str] = None,
                      htf: Optional[str] = None) -> bool:
    """Returns True only when a new row is inserted.

    Uses ``engine.begin()`` so the transaction is committed on context-exit;
    this works on SQLAlchemy 1.4 (Airflow's typical version) where
    ``Connection.commit`` is not exposed, as well as on 2.x.

    ``mode``/``ltf``/``htf`` override the stream tag; defaults preserve the legacy
    behaviour (dynamic vs live on the 1h INTERVAL). PULSE passes mode='pulse',
    ltf='15m', htf='1h'.
    """
    mode_val = mode or ("dynamic" if is_dynamic else "live")
    ltf_val = ltf or INTERVAL
    htf_val = htf or HTF_RULE
    direction = sig.direction.upper()
    sig_time = sig.timestamp.to_pydatetime()
    try:
        engine = get_db_engine()
        with engine.begin() as conn:
            if signal_already_exists(conn, sig.symbol, sig_time, direction, mode_val):
                print(f"  dup {sig.symbol} {direction} @ {sig_time} [{mode_val}] (skipped)")
                return False
            q = text("""
                INSERT INTO ict_trade.signals
                (symbol, direction, entry, sl, tp, signal_time,
                 mode, ltf_timeframe, htf_timeframe,
                 strategy, quality, confluence_score)
                VALUES
                (:symbol, :direction, :entry, :sl, :tp, :signal_time,
                 :mode, :ltf, :htf,
                 :strategy, :quality, :confluence_score)
            """)
            conn.execute(q, {
                "symbol": sig.symbol, "direction": direction,
                "entry": float(sig.entry), "sl": float(sig.stop_loss),
                "tp": float(sig.take_profit_1) if sig.take_profit_1 is not None else None,
                "signal_time": sig_time, "mode": mode_val,
                "ltf": ltf_val, "htf": htf_val,
                "strategy": sig.strategy,
                "quality": sig.quality,
                "confluence_score": int(sig.confluence_score),
            })
        # best-effort: attach decision geometry in a SEPARATE tx so a missing
        # `context` column (pre-migration) can never block the signal insert.
        try:
            with engine.begin() as conn:
                # mode-aware: without `AND mode` a radar row's geometry would clobber
                # main's on a same-symbol/bar/direction collision (different algorithms
                # -> different entry/SL/TP -> different charts).
                conn.execute(text("""
                    UPDATE ict_trade.signals SET context = CAST(:c AS JSONB)
                    WHERE symbol = :s AND signal_time = :t AND direction = :d AND mode = :m
                """), {"c": json.dumps(getattr(sig, "context", {}) or {}),
                       "s": sig.symbol, "t": sig_time, "d": direction, "m": mode_val})
        except Exception as ce:
            print(f"  (context skipped: {ce})")
        print(f"  ✅ saved {sig.symbol} {direction} @ {sig_time}")
        return True
    except Exception as e:
        print(f"  ❌ DB save error: {e}")
        return False


def format_telegram_message(sig: Signal, is_dynamic: bool = False, pulse: bool = False,
                            impulse: bool = False, radar: bool = False,
                            squeeze: bool = False) -> str:
    arrow = "🟢 LONG" if sig.direction == "long" else "🔴 SHORT"
    rr = sig.risk_reward_1 if sig.risk_reward_1 else 0
    risk_pct = abs(sig.entry - sig.stop_loss) / sig.entry * 100
    target_pct = (abs(sig.take_profit_1 - sig.entry) / sig.entry * 100
                  if sig.take_profit_1 is not None else 0)
    quality_emoji = "⭐" if sig.quality == "high" else "✓"
    if pulse:
        banner = "⚡ <b>PULSE 15m</b> (FVG+OB confluence)\n\n"
    elif impulse:
        banner = "✨ <b>IMPULSE (v2)</b>\n\n"
    elif radar:
        banner = "📡 <b>RADAR (v3)</b> (compression breakout)\n\n"
    elif squeeze:
        banner = "🧲 <b>SQUEEZE (v4)</b> (funding-extreme fade)\n\n"
    elif is_dynamic:
        banner = "🔥 <b>DİNAMİK HACİM PICK</b> (vetlenmemiş sembol)\n\n"
    else:
        banner = ""
    return (
        banner +
        f"<b>{arrow} {sig.symbol}</b>\n"
        f"📋 {sig.strategy}\n"
        f"⏰ {sig.timestamp.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
        f"🎯 Entry: <code>{sig.entry:.6g}</code>\n"
        f"✅ TP: <code>{sig.take_profit_1:.6g}</code>  (+{target_pct:.2f}%)\n"
        f"🛑 SL: <code>{sig.stop_loss:.6g}</code>  (-{risk_pct:.2f}%)\n\n"
        f"📊 RR <b>1:{rr:.2f}</b>  |  {quality_emoji} {sig.quality}  |  score {sig.confluence_score}"
    )


def trim_open_bar(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or len(df) < 2:
        return df
    bm = _bar_minutes(df)
    last_open = df.index[-1]
    expected_close = last_open + pd.Timedelta(minutes=bm)
    if pd.Timestamp.now(tz="UTC") < expected_close:
        return df.iloc[:-1]
    return df


def process_symbol(symbol: str, is_dynamic: bool = False, *, pulse: bool = False,
                   impulse: bool = False, radar: bool = False, squeeze: bool = False,
                   defer_alerts: bool = False) -> list:
    if pulse:
        interval, warmup, strategies, htf_rule, mode = (
            PULSE_INTERVAL, PULSE_WARMUP_HOURS, PULSE_STRATEGIES, PULSE_HTF, PULSE_MODE)
        # PULSE -> its own chat when configured; else the main chat (⚡ banner).
        chat = TELEGRAM_PULSE_CHAT_ID or None
    elif impulse:
        interval, warmup, strategies, htf_rule, mode = (
            INTERVAL, WARMUP_HOURS, IMPULSE_STRATEGIES, HTF_RULE, IMPULSE_MODE)
        # IMPULSE -> dedicated chat only (DB-only when unset; never the main chat).
        chat = TELEGRAM_IMPULSE_CHAT_ID or None
    elif radar:
        interval, warmup, strategies, htf_rule, mode = (
            INTERVAL, WARMUP_HOURS, RADAR_STRATEGIES, HTF_RULE, RADAR_MODE)
        # RADAR -> dedicated chat only (DB-only when unset; never the main chat).
        chat = TELEGRAM_RADAR_CHAT_ID or None
    elif squeeze:
        interval, warmup, strategies, htf_rule, mode = (
            INTERVAL, WARMUP_HOURS, SQUEEZE_STRATEGIES, HTF_RULE, SQUEEZE_MODE)
        # SQUEEZE -> dedicated chat only (DB-only when unset; never the main chat).
        chat = TELEGRAM_SQUEEZE_CHAT_ID or None
    else:
        interval, warmup, strategies, htf_rule = INTERVAL, WARMUP_HOURS, None, HTF_RULE
        mode = "dynamic" if is_dynamic else "live"
        chat = None
    # Suppress alerts entirely for impulse/radar/squeeze without a dedicated chat
    # (impulse overlaps main; radar/squeeze must never blend into the main chat).
    silent = (impulse and not TELEGRAM_IMPULSE_CHAT_ID) or \
             (radar and not TELEGRAM_RADAR_CHAT_ID) or \
             (squeeze and not TELEGRAM_SQUEEZE_CHAT_ID)

    end = pd.Timestamp.now(tz="UTC")
    start = end - pd.Timedelta(hours=warmup)
    df = fetch_klines(symbol, interval,
                      int(start.timestamp() * 1000),
                      int(end.timestamp() * 1000))
    if df.empty:
        print(f"  {symbol}: no data")
        return []
    df = trim_open_bar(df)
    if len(df) < 60:
        print(f"  {symbol}: only {len(df)} bars after trim, skipping")
        return []

    if squeeze:
        # strategy_g reads settled funding from the registry; 45d covers the 30d
        # percentile window + the shift(1) predecessor of every event it can use.
        fund_start = end - pd.Timedelta(days=SQUEEZE_FUND_FETCH_DAYS)
        fdf = fetch_funding(symbol, int(fund_start.timestamp() * 1000),
                            int(end.timestamp() * 1000))
        set_funding(symbol, fdf)
        if fdf.empty:
            print(f"  {symbol}: no funding history — squeeze inactive")
            return []

    last_idx = len(df) - 1
    # Scan back over the dedup cooldown window (not just the last bar) so
    # dedup_zone_signals can see whether the same zone already fired on an
    # earlier bar; only last-bar signals are emitted. DB idempotency on
    # (symbol, signal_time, direction, mode) keeps earlier bars out anyway.
    bm = _bar_minutes(df)
    cooldown_bars = max(1, int(DEDUP_COOLDOWN_MINUTES / bm)) if (DEDUP_COOLDOWN_MINUTES > 0 and bm > 0) else 0
    scan_start = max(ATR_PERIOD + 5, last_idx - cooldown_bars)
    signals = run_engine(symbol, df, start_index=scan_start, end_index=last_idx,
                         strategies=strategies, htf_rule=htf_rule)
    signals = [s for s in signals if s.bar_index == last_idx]

    saved = []
    for sig in signals:
        if save_signal_to_db(sig, mode=mode, ltf=interval, htf=htf_rule):
            saved.append(sig)
            if not defer_alerts and not silent:
                send_telegram_message(
                    format_telegram_message(sig, is_dynamic=is_dynamic, pulse=pulse,
                                            impulse=impulse, radar=radar, squeeze=squeeze),
                    chat_id=chat)
    if not signals:
        print(f"  {symbol}: no signal at last closed bar ({df.index[-1]})")
    return saved


# ============================================================================
# SCAN LOOP (shared by Airflow task and standalone runner)
# ============================================================================

# Per-run heartbeat: confirms the hourly cron actually fired even on hours that
# emit no new signal (most hours do). Without it, Telegram silence is ambiguous
# — "no setup" vs "bot is down". Toggle off with HEARTBEAT=0 in the environment.
HEARTBEAT_ENABLED = os.getenv("HEARTBEAT", "1").strip().lower() not in ("0", "false", "no", "off")


def send_heartbeat(new_signals: int, n_symbols: int, errors: int = 0,
                   n_dynamic: int = 0, suppressed: int = 0) -> None:
    if not HEARTBEAT_ENABLED:
        return
    now = pd.Timestamp.now(tz="UTC")
    warn = f"\n⚠️ {errors} sembolde hata" if errors else ""
    dyn = f"\n🔥 {n_dynamic} dinamik sembol (hacim anomalisi)" if n_dynamic else ""
    sup = (f"\n🧯 {suppressed} sinyal DB'ye yazıldı ama alarm bastırıldı "
           f"(yön başına max {MAX_ALERTS_PER_DIRECTION})" if suppressed else "")
    msg = (
        f"🤖 <b>ICT Saatlik Tarama</b>\n"
        f"⏰ {now.strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"📊 {n_symbols} sembol tarandı{dyn}\n"
        f"✅ {new_signals} yeni sinyal{warn}{sup}"
    )
    send_telegram_message(msg)


# Portfolio risk gate: N same-direction signals on the same hourly bar are ONE
# macro position, not N independent trades (2026-06-10 run: 8 of 9 signals LONG).
# Every signal is still saved to DB (keeps backtest/live parity auditable); only
# the strongest per direction get a Telegram alert.
MAX_ALERTS_PER_DIRECTION = 3


def run_scan() -> int:
    """Walk every symbol once at its last closed bar. Used by both Airflow and CLI."""
    errors = 0

    # Dynamic volume-anomaly picks (best-effort; can never break the core scan).
    try:
        dynamic = pick_volume_anomaly_symbols(set(SYMBOLS), DYN_MAX_PICKS)
    except Exception as e:
        print(f"  [dyn] selection failed, scanning static set only: {e}")
        dynamic = []
    dyn_set = set(dynamic)
    scan_list = list(SYMBOLS) + dynamic
    print(f"Toplam Taranacak Sembol Sayısı: {len(scan_list)} "
          f"({len(SYMBOLS)} sabit + {len(dynamic)} dinamik)")

    saved_all: list = []
    for sym in scan_list:
        print(f"=== {sym}{' 🔥' if sym in dyn_set else ''} ===")
        try:
            saved_all += process_symbol(sym, is_dynamic=(sym in dyn_set), defer_alerts=True)
        except Exception as e:
            errors += 1
            print(f"  ERROR analyzing {sym}: {e}")
    total = len(saved_all)

    # Alerts: rank per direction by confluence then RR; suppress the tail.
    suppressed = 0
    by_dir = defaultdict(list)
    for s in saved_all:
        by_dir[s.direction].append(s)
    for direction, group in by_dir.items():
        group.sort(key=lambda s: (s.confluence_score, s.risk_reward_1 or 0), reverse=True)
        for rank, s in enumerate(group):
            if rank < MAX_ALERTS_PER_DIRECTION:
                send_telegram_message(
                    format_telegram_message(s, is_dynamic=(s.symbol in dyn_set)))
            else:
                suppressed += 1
                print(f"  🧯 alarm bastırıldı (portföy kapısı): {s.symbol} {direction} "
                      f"score={s.confluence_score} rr={s.risk_reward_1:.2f}")

    print(f"\nDone. {total} new signal(s) emitted, {suppressed} alert(s) suppressed.")
    send_heartbeat(total, len(scan_list), errors, n_dynamic=len(dynamic), suppressed=suppressed)
    return total


def run_pulse_scan() -> int:
    """PULSE 15m C-only pass over the static SYMBOLS. Separate cadence (every 15m),
    separate DB tag (mode='pulse') and separate Telegram chat — never mixes with the
    hourly main/dynamic scan. No dynamic picks here (curated set only)."""
    total = 0
    errors = 0
    print(f"⚡ PULSE 15m taraması: {len(SYMBOLS)} sembol (C-only)")
    for sym in SYMBOLS:
        print(f"=== ⚡ {sym} ===")
        try:
            total += len(process_symbol(sym, pulse=True))
        except Exception as e:
            errors += 1
            print(f"  ERROR analyzing {sym}: {e}")
    print(f"\nPULSE done. {total} yeni 15m sinyal.")
    if PULSE_HEARTBEAT_ENABLED:
        now = pd.Timestamp.now(tz="UTC")
        warn = f"\n⚠️ {errors} sembolde hata" if errors else ""
        send_telegram_message(
            f"⚡ <b>PULSE 15m Tarama</b>\n⏰ {now.strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"📊 {len(SYMBOLS)} sembol\n✅ {total} yeni sinyal{warn}",
            chat_id=(TELEGRAM_PULSE_CHAT_ID or None))
    return total


def run_impulse_scan() -> int:
    """IMPULSE (v2) hourly pass: B/C/D over the static SYMBOLS, with strategy E
    dropped and D additionally disabled on ADA/XAU/ETH. Same 1h cadence as main but
    a separate DB tag (mode='impulse') and no dynamic picks — daily sync resolves it
    to backtest version='v2'. The extra D-exclusion is applied here (process-local):
    impulse runs as its own process, so main's D scope is untouched."""
    D_EXCLUDE_SYMBOLS.update(IMPULSE_EXTRA_D_EXCLUDE)
    total = 0
    errors = 0
    print(f"✨ IMPULSE v2 taraması: {len(SYMBOLS)} sembol (B/C/D, D-excl={sorted(D_EXCLUDE_SYMBOLS)})")
    for sym in SYMBOLS:
        print(f"=== ✨ {sym} ===")
        try:
            total += len(process_symbol(sym, impulse=True))
        except Exception as e:
            errors += 1
            print(f"  ERROR analyzing {sym}: {e}")
    print(f"\nIMPULSE done. {total} yeni v2 sinyal.")
    # Heartbeat only to a dedicated chat (never the main chat — impulse overlaps main).
    if TELEGRAM_IMPULSE_CHAT_ID:
        now = pd.Timestamp.now(tz="UTC")
        warn = f"\n⚠️ {errors} sembolde hata" if errors else ""
        send_telegram_message(
            f"✨ <b>IMPULSE v2 Tarama</b>\n⏰ {now.strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"📊 {len(SYMBOLS)} sembol\n✅ {total} yeni sinyal{warn}",
            chat_id=TELEGRAM_IMPULSE_CHAT_ID)
    return total


def run_radar_scan() -> int:
    """RADAR (v3) hourly pass: strategy F only (vol-compression Donchian breakout)
    over the static SYMBOLS. Same 1h cadence as main but a separate DB tag
    (mode='radar') and no dynamic picks — daily sync resolves it to backtest
    version='v3'. DB-only unless TELEGRAM_RADAR_CHAT_ID is set."""
    total = 0
    errors = 0
    print(f"📡 RADAR v3 taraması: {len(SYMBOLS)} sembol (F-only)")
    for sym in SYMBOLS:
        print(f"=== 📡 {sym} ===")
        try:
            total += len(process_symbol(sym, radar=True))
        except Exception as e:
            errors += 1
            print(f"  ERROR analyzing {sym}: {e}")
    print(f"\nRADAR done. {total} yeni v3 sinyal.")
    # Heartbeat only to a dedicated chat (never the main chat).
    if TELEGRAM_RADAR_CHAT_ID:
        now = pd.Timestamp.now(tz="UTC")
        warn = f"\n⚠️ {errors} sembolde hata" if errors else ""
        send_telegram_message(
            f"📡 <b>RADAR v3 Tarama</b>\n⏰ {now.strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"📊 {len(SYMBOLS)} sembol\n✅ {total} yeni sinyal{warn}",
            chat_id=TELEGRAM_RADAR_CHAT_ID)
    return total


def run_squeeze_scan() -> int:
    """SQUEEZE (v4) hourly pass: strategy G only (funding-extreme squeeze fade)
    over the static SYMBOLS. Same 1h cadence as main but a separate DB tag
    (mode='squeeze') and no dynamic picks — daily sync resolves it to backtest
    version='v4'. DB-only unless TELEGRAM_SQUEEZE_CHAT_ID is set."""
    total = 0
    errors = 0
    print(f"🧲 SQUEEZE v4 taraması: {len(SYMBOLS)} sembol (G-only)")
    for sym in SYMBOLS:
        print(f"=== 🧲 {sym} ===")
        try:
            total += len(process_symbol(sym, squeeze=True))
        except Exception as e:
            errors += 1
            print(f"  ERROR analyzing {sym}: {e}")
    print(f"\nSQUEEZE done. {total} yeni v4 sinyal.")
    # Heartbeat only to a dedicated chat (never the main chat).
    if TELEGRAM_SQUEEZE_CHAT_ID:
        now = pd.Timestamp.now(tz="UTC")
        warn = f"\n⚠️ {errors} sembolde hata" if errors else ""
        send_telegram_message(
            f"🧲 <b>SQUEEZE v4 Tarama</b>\n⏰ {now.strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"📊 {len(SYMBOLS)} sembol\n✅ {total} yeni sinyal{warn}",
            chat_id=TELEGRAM_SQUEEZE_CHAT_ID)
    return total


# ============================================================================
# AIRFLOW DAG (only built when Airflow is installed)
# ============================================================================

if _AIRFLOW_AVAILABLE:
    default_args = {
        'owner': 'airflow',
        'depends_on_past': False,
        'start_date': days_ago(1),
        'email_on_failure': False,
        'email_on_retry': False,
        'retries': 1,
        'retry_delay': dt.timedelta(minutes=2),
    }

    @dag(
        dag_id="huseyin_llm_hybrid_ict",
        default_args=default_args,
        schedule=CronTriggerTimetable("1 * * * *", timezone="UTC"),
        catchup=False,
        tags=['trading', 'ict', 'crypto', 'mtf'],
    )
    def ict_dag():

        @task()
        def scan_market():
            time.sleep(2)
            run_scan()

        scan_market()

    dag = ict_dag()

    @dag(
        dag_id="huseyin_llm_hybrid_ict_pulse",
        default_args=default_args,
        schedule=CronTriggerTimetable("*/15 * * * *", timezone="UTC"),
        catchup=False,
        tags=['trading', 'ict', 'crypto', 'pulse', '15m'],
    )
    def ict_pulse_dag():

        @task()
        def scan_pulse():
            time.sleep(2)
            run_pulse_scan()

        scan_pulse()

    if PULSE_ENABLED:  # pulse stream disabled 2026-06-10 — see PULSE_ENABLED note above
        pulse_dag = ict_pulse_dag()

    @dag(
        dag_id="huseyin_llm_hybrid_ict_impulse",
        default_args=default_args,
        schedule=CronTriggerTimetable("2 * * * *", timezone="UTC"),
        catchup=False,
        tags=['trading', 'ict', 'crypto', 'impulse', 'v2'],
    )
    def ict_impulse_dag():

        @task()
        def scan_impulse():
            time.sleep(2)
            run_impulse_scan()

        scan_impulse()

    if IMPULSE_ENABLED:
        impulse_dag = ict_impulse_dag()

    @dag(
        dag_id="huseyin_llm_hybrid_ict_radar",
        default_args=default_args,
        schedule=CronTriggerTimetable("4 * * * *", timezone="UTC"),
        catchup=False,
        tags=['trading', 'ict', 'crypto', 'radar', 'v3'],
    )
    def ict_radar_dag():

        @task()
        def scan_radar():
            time.sleep(2)
            run_radar_scan()

        scan_radar()

    if RADAR_ENABLED:  # default OFF until the v3 backtest passes its gates
        radar_dag = ict_radar_dag()

    @dag(
        dag_id="huseyin_llm_hybrid_ict_squeeze",
        default_args=default_args,
        schedule=CronTriggerTimetable("6 * * * *", timezone="UTC"),
        catchup=False,
        tags=['trading', 'ict', 'crypto', 'squeeze', 'v4', 'funding'],
    )
    def ict_squeeze_dag():

        @task()
        def scan_squeeze():
            time.sleep(2)
            run_squeeze_scan()

        scan_squeeze()

    if SQUEEZE_ENABLED:  # default tracks the v4 gate verdict (see config note)
        squeeze_dag = ict_squeeze_dag()


# ============================================================================
# STANDALONE ENTRY POINT (GitHub Actions / cron / local)
#   python dag/dag.py
# Reads DB_CONNECTION_STRING, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID from env.
# ============================================================================

def main() -> None:
    if not DB_CONNECTION_STRING:
        raise SystemExit("DB_CONNECTION_STRING ortam değişkeni eksik.")
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        print("UYARI: Telegram env (TOKEN/CHAT_ID) yok — sinyaller DB'ye yazılır ama mesaj atılmaz.")
    # Dispatch: `python dag/dag.py pulse|impulse|radar` (or SCAN_MODE=...) runs that
    # stream's pass; anything else runs the hourly main/dynamic scan.
    scan_mode = (sys.argv[1] if len(sys.argv) > 1 else os.getenv("SCAN_MODE", "")).strip().lower()
    if scan_mode == "pulse":
        if not PULSE_ENABLED:
            print("PULSE devre dışı (2026-06-10) — açmak için PULSE_ENABLED=1 ver.")
            return
        run_pulse_scan()
    elif scan_mode == "impulse":
        if not IMPULSE_ENABLED:
            print("IMPULSE devre dışı — açmak için IMPULSE_ENABLED=1 ver.")
            return
        run_impulse_scan()
    elif scan_mode == "radar":
        if not RADAR_ENABLED:
            print("RADAR devre dışı (default) — açmak için RADAR_ENABLED=1 ver.")
            return
        run_radar_scan()
    elif scan_mode == "squeeze":
        if not SQUEEZE_ENABLED:
            print("SQUEEZE devre dışı — açmak için SQUEEZE_ENABLED=1 ver.")
            return
        run_squeeze_scan()
    else:
        run_scan()


if __name__ == "__main__":
    main()
