"""Data loading and multi-timeframe aggregation."""

from __future__ import annotations
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

BINANCE_FAPI = "https://fapi.binance.com/fapi/v1/klines"
BINANCE_API = "https://api.binance.com/api/v3/klines"
BINANCE_FUNDING = "https://fapi.binance.com/fapi/v1/fundingRate"

OHLCV_COLS = ["open", "high", "low", "close", "volume"]


def fetch_klines(symbol: str, interval: str, start_ms: int, end_ms: int,
                 futures: bool = True, limit: int = 1500) -> pd.DataFrame:
    """Pull OHLCV from Binance with simple pagination. Falls back to spot if futures empty."""
    base = BINANCE_FAPI if futures else BINANCE_API
    rows: list = []
    cursor = start_ms
    while cursor < end_ms:
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": cursor,
            "endTime": end_ms,
            "limit": limit,
        }
        try:
            r = requests.get(base, params=params, timeout=20)
            r.raise_for_status()
            chunk = r.json()
        except requests.exceptions.RequestException as e:
            print(f"  fetch error ({base} {symbol}): {e}")
            return pd.DataFrame(columns=OHLCV_COLS)
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
        "_close_t", "_quote_v", "_trades", "_tbb", "_tbq", "_ignore"
    ])
    df["timestamp"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("timestamp")[OHLCV_COLS].astype(float)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def fetch_funding(symbol: str, start_ms: int, end_ms: int,
                  limit: int = 1000) -> pd.DataFrame:
    """Settled perp funding events from Binance futures, paginated.

    Returns a DataFrame indexed by fundingTime (UTC) with a single `rate` column.
    Each rate is FINAL and public at its fundingTime, so consuming it at any
    bar close >= fundingTime is causally safe (no look-ahead). Spot-only symbols
    return an empty frame — callers must treat that as 'strategy inactive'."""
    rows: list = []
    cursor = start_ms
    while cursor < end_ms:
        params = {"symbol": symbol, "startTime": cursor,
                  "endTime": end_ms, "limit": limit}
        try:
            r = requests.get(BINANCE_FUNDING, params=params, timeout=20)
            r.raise_for_status()
            chunk = r.json()
        except requests.exceptions.RequestException as e:
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
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["fundingTime"], unit="ms", utc=True)
    df["rate"] = df["fundingRate"].astype(float)
    df = df.set_index("timestamp")[["rate"]]
    return df[~df.index.duplicated(keep="last")].sort_index()


def load_csv(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["timestamp"])
    df = df.set_index("timestamp")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df[OHLCV_COLS].astype(float).sort_index()


_AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}


def aggregate(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample a 1m frame to a higher timeframe (e.g. '5min', '15min', '1h', '4h', '1D')."""
    out = df.resample(rule, label="right", closed="right").agg(_AGG).dropna()
    return out


def to_unix_ms(dt_str: str) -> int:
    dt = pd.Timestamp(dt_str, tz="UTC") if "T" in dt_str or " " in dt_str else pd.Timestamp(dt_str + " 00:00:00", tz="UTC")
    return int(dt.timestamp() * 1000)
