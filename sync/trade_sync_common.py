"""Shared helpers for the trading_signals sync jobs (backfill + daily ETL).

Single source of truth for:
  - DB connections (special-char-safe DSN parsing — passwords contain %, £, backticks)
  - 1h kline fetch (reuses the backtest engine's fetch_klines: futures + spot fallback)
  - outcome simulation (reuses backtest/backtester.py: simulate_signal)
  - status mapping (backtester TradeStatus -> trading_signals.status vocabulary)
  - row mapping + idempotent upsert into ict_trade.trading_signals

Schema/contract is the LIVE one verified on the restored backtest DB:
  trading_signals(symbol, trade_type, direction, signal_time, signal_price,
    entry_price, sl_price, tp_price, status, real_entry_time, exit_time,
    exit_price, pnl_r, version, strategy, quality, confluence_score, created_at, id)
Dashboard filters version='v1' and excludes status in (cancelled, canceled).
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

REPO = Path(__file__).resolve().parents[1]
BT = REPO / "backtest"
sys.path.insert(0, str(BT))

from ict.data import fetch_klines          # noqa: E402  (futures+spot fallback)
from backtester import simulate_signal     # noqa: E402

ENV_PATH = REPO / ".env"
INTERVAL = "1h"             # signal-generation / engine timeframe (fetch_1h feeds run_engine)
EXPIRY_MINUTES = 180        # entry-fill window in minutes (= 180 bars on the 1m resolver)
RESOLUTION_INTERVAL = "1m"  # outcome resolution timeframe — intrabar entry vs TP/SL order
RESOLUTION_HORIZON = pd.Timedelta(days=10)  # per-signal 1m fetch span when df1m not passed
VERSION = "v1"
TABLE = "ict_trade.trading_signals"

# backtester.TradeStatus.value  ->  trading_signals.status
STATUS_MAP = {
    "tp_hit": "closed_tp",
    "sl_hit": "closed_sl",
    "expired": "cancelled",       # limit never filled -> no trade
    "invalidated": "cancelled",   # TP/SL hit before entry -> no trade taken
    "active": "active",           # filled, not yet resolved (re-checked next run)
    "pending": "pending",
}

# ---------------------------------------------------------------- connections
def _read_env() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        out[k.strip()] = v
    return out


def parse_dsn(dsn: str) -> dict:
    """Parse a postgres URL whose password may contain special chars (no urllib)."""
    body = dsn.split("://", 1)[1]
    creds, hostpart = body.rsplit("@", 1)
    user, password = creds.split(":", 1)
    hostport, db = hostpart.split("/", 1)
    host, port = hostport.rsplit(":", 1)
    return {"user": user, "password": password, "host": host,
            "port": int(port), "dbname": db}


def _connect(env_key: str):
    env = _read_env()
    dsn = env.get(env_key) or os.getenv(env_key)
    if not dsn:
        raise SystemExit(f"{env_key} not set in {ENV_PATH} or environment.")
    return psycopg2.connect(connect_timeout=20, **parse_dsn(dsn))


def live_conn():
    """LIVE signals DB (ict_trade.signals)."""
    return _connect("DB_CONNECTION_STRING")


def backtest_conn():
    """BACKTEST results DB (ict_trade.trading_signals)."""
    return _connect("BACKTESTING_DB_CONNECTION_STRING")


# ---------------------------------------------------------------- klines
def fetch_1h(symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    return fetch_klines(symbol, INTERVAL,
                        int(start.timestamp() * 1000),
                        int(end.timestamp() * 1000))


def fetch_1m(symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """1-minute klines for intrabar-accurate outcome resolution (paginated by fetch_klines)."""
    return fetch_klines(symbol, RESOLUTION_INTERVAL,
                        int(start.timestamp() * 1000),
                        int(end.timestamp() * 1000))


# ---------------------------------------------------------------- outcome
class _StubSignal:
    """Minimal object exposing the attributes backtester.simulate_signal reads."""
    __slots__ = ("direction", "entry", "stop_loss", "take_profit_1",
                 "bar_index", "expires_at_index", "strategy")

    def __init__(self, direction, entry, sl, tp, bar_index, expires_at_index, strategy=""):
        self.direction = direction
        self.entry = entry
        self.stop_loss = sl
        self.take_profit_1 = tp
        self.bar_index = bar_index
        self.expires_at_index = expires_at_index
        self.strategy = strategy


def _pending() -> dict:
    return {"status": STATUS_MAP["pending"], "real_entry_time": None, "exit_time": None,
            "exit_price": None, "pnl_r": None, "raw_status": "pending"}


def _resolve(df1m: pd.DataFrame, close_ts: pd.Timestamp, direction: str,
             entry: float, sl: float, tp: float) -> dict:
    """Resolve one trade on 1m bars from the signal close; return trading_signals fields.

    Reuses backtester.simulate_signal: entry must FILL before TP/SL or the trade is
    INVALIDATED (no trade taken); same-bar tie -> SL. Entry-fill window = EXPIRY_MINUTES
    (= 180 bars on 1m). On 1m the intrabar order of entry vs TP/SL is essentially
    unambiguous — unlike 1h, where one bar's high+low can falsely register entry-then-TP."""
    idx = df1m.index
    if idx.tz is None:
        df1m = df1m.copy()
        df1m.index = idx = idx.tz_localize("UTC")
    pos = int(idx.searchsorted(close_ts))       # first 1m bar at/after the signal close
    if pos >= len(df1m):
        return _pending()                        # not enough data yet -> re-checked later
    bar_index = pos - 1                           # simulate_signal scans from bar_index+1
    sig = _StubSignal(direction.lower(), float(entry), float(sl), float(tp),
                      bar_index, bar_index + EXPIRY_MINUTES)
    res = simulate_signal(sig, df1m)
    bar_dur = pd.Timedelta(minutes=1)

    def close_at(i):
        return (df1m.index[i] + bar_dur).to_pydatetime() if i is not None else None

    return {
        "status": STATUS_MAP.get(res.status.value, res.status.value),
        "real_entry_time": close_at(res.entry_index),
        "exit_time": close_at(res.exit_index),
        "exit_price": float(res.exit_price) if res.exit_price is not None else None,
        "pnl_r": float(res.pnl_r) if res.pnl_r is not None else None,
        "raw_status": res.status.value,
    }


def simulate(symbol: str, signal_ts, direction: str, entry: float, sl: float, tp: float,
             *, df1m: pd.DataFrame | None = None, ltf_minutes: int = 60) -> dict:
    """Resolve a signal's TP/SL outcome on 1m klines (intrabar-accurate).

    Signal generation stays on 1h; only the OUTCOME is resolved on 1m. The signal fires
    at its bar close (signal_ts + ltf), where the 1m scan begins. Pass df1m to reuse a
    per-symbol 1m frame (backfill); omit it to fetch a per-signal window (daily sync)."""
    ts = pd.Timestamp(signal_ts)
    if ts.tz is None:
        ts = ts.tz_localize("UTC")
    close_ts = ts + pd.Timedelta(minutes=ltf_minutes)
    if df1m is None:
        df1m = fetch_1m(symbol, close_ts, close_ts + RESOLUTION_HORIZON)
    if df1m is None or df1m.empty:
        return _pending()
    return _resolve(df1m, close_ts, direction, entry, sl, tp)


# ---------------------------------------------------------------- row mapping
def _norm(direction: str) -> tuple[str, str]:
    d = (direction or "").upper()
    if d in ("LONG", "BUY"):
        return "BUY", "LONG"
    return "SELL", "SHORT"


def build_row(symbol: str, signal_time, direction: str, entry: float, sl: float,
              tp: float, outcome: dict, *, strategy=None, quality=None,
              confluence_score=None) -> dict:
    trade_type, dir_norm = _norm(direction)
    st = signal_time.to_pydatetime() if isinstance(signal_time, pd.Timestamp) else signal_time
    return {
        "symbol": symbol, "trade_type": trade_type, "direction": dir_norm,
        "signal_time": st, "signal_price": float(entry), "entry_price": float(entry),
        "sl_price": float(sl), "tp_price": float(tp),
        "status": outcome["status"], "real_entry_time": outcome["real_entry_time"],
        "exit_time": outcome["exit_time"], "exit_price": outcome["exit_price"],
        "pnl_r": outcome["pnl_r"], "version": VERSION,
        "strategy": strategy, "quality": quality,
        "confluence_score": int(confluence_score) if confluence_score is not None else None,
    }


_COLS = ["symbol", "trade_type", "direction", "signal_time", "signal_price",
         "entry_price", "sl_price", "tp_price", "status", "real_entry_time",
         "exit_time", "exit_price", "pnl_r", "version", "strategy", "quality",
         "confluence_score"]

_UPSERT = f"""
INSERT INTO {TABLE} ({", ".join(_COLS)}) VALUES %s
ON CONFLICT (symbol, signal_time, trade_type, version) DO UPDATE SET
  status = EXCLUDED.status,
  real_entry_time = EXCLUDED.real_entry_time,
  exit_time = EXCLUDED.exit_time,
  exit_price = EXCLUDED.exit_price,
  pnl_r = EXCLUDED.pnl_r,
  signal_price = EXCLUDED.signal_price,
  entry_price = EXCLUDED.entry_price,
  sl_price = EXCLUDED.sl_price,
  tp_price = EXCLUDED.tp_price,
  strategy = EXCLUDED.strategy,
  quality = EXCLUDED.quality,
  confluence_score = EXCLUDED.confluence_score
"""


def upsert_rows(conn, rows: list[dict]) -> int:
    if not rows:
        return 0
    vals = [tuple(r[c] for c in _COLS) for r in rows]
    cur = conn.cursor()
    execute_values(cur, _UPSERT, vals, page_size=500)
    conn.commit()
    cur.close()
    return len(rows)
