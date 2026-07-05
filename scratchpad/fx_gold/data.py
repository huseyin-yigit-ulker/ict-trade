"""Download + cache Binance XAUUSDT 1m for 2026-H1, plus a real FX-gold market-hours filter.

Binance Futures lists a XAUUSDT perpetual (price tracks spot gold ~$3000-4000). It trades 24/7,
but the *real* gold/FX market is closed on weekends and during the daily rollover. For an
FX-realistic bot we only trade when the spot-gold/FX market is open:

    Open : Sunday 18:00 ET  ->  Friday 17:00 ET
    Daily break (rollover) : 17:00-18:00 ET, Mon-Thu (and the Fri close / Sun open)

America/New_York via zoneinfo handles US DST automatically (EST Jan 1-Mar 8 2026, EDT after).
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "backtest" / "ict"))
import data as bdata  # repo's robust paginated Binance fetcher

SYMBOL = "XAUUSDT"
CACHE = HERE / "xauusdt_1m_2026h1.pkl"
START = "2026-01-01"
END   = "2026-07-01"   # exclusive upper edge for the fetch; today is 2026-06-30


def load_1m(refresh: bool = False) -> pd.DataFrame:
    if CACHE.exists() and not refresh:
        return pd.read_pickle(CACHE)
    s = bdata.to_unix_ms(START)
    e = bdata.to_unix_ms(END)
    df = bdata.fetch_klines(SYMBOL, "1m", s, e, futures=True, limit=1500)
    df = df.loc[(df.index >= pd.Timestamp(START, tz="UTC")) & (df.index < pd.Timestamp(END, tz="UTC"))]
    df.to_pickle(CACHE)
    return df


def add_market_open(df: pd.DataFrame) -> pd.DataFrame:
    """Add boolean `open` column = real FX-gold market open at that minute (bar close time, UTC)."""
    et = df.index.tz_convert("America/New_York")
    dow = et.dayofweek          # Mon=0 .. Sun=6
    hour = et.hour
    is_open = pd.Series(True, index=df.index)
    is_open &= ~(dow == 5)                       # Saturday closed
    is_open &= ~((dow == 6) & (hour < 18))       # Sunday opens 18:00 ET
    is_open &= ~((dow == 4) & (hour >= 17))      # Friday closes 17:00 ET
    is_open &= ~((dow <= 3) & (hour == 17))      # Mon-Thu daily 17:00-18:00 break
    out = df.copy()
    out["open_mkt"] = is_open.values
    # session tags (ET local) for session strategies
    out["et_hour"] = hour
    out["et_min"] = et.minute
    out["et_date"] = et.date
    out["dow"] = dow
    return out


if __name__ == "__main__":
    refresh = "--refresh" in sys.argv
    df = load_1m(refresh=refresh)
    df = add_market_open(df)
    n = len(df)
    op = int(df["open_mkt"].sum())
    print(f"XAUUSDT 1m 2026-H1: {n} bars  {df.index.min()} -> {df.index.max()}")
    print(f"  market-open bars: {op} ({op/n:.1%})   closed: {n-op}")
    print(f"  price range: {df['close'].min():.2f} - {df['close'].max():.2f}")
    # sanity: open-bar fraction by day-of-week
    g = df.groupby("dow")["open_mkt"].mean().round(3)
    print("  open-fraction by dow (Mon=0..Sun=6):"); print(g.to_string())
    # daily bar counts (gaps?)
    perday = df.groupby(df.index.tz_convert("UTC").date).size()
    print(f"  bars/day: median={perday.median():.0f} min={perday.min()} max={perday.max()}")
