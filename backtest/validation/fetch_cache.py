"""Fetch & cache Binance futures klines for BTC/ETH (1h for parity, 15m for outcomes)."""
from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]   # backtest/
sys.path.insert(0, str(ROOT))
from ict.data import fetch_klines  # noqa: E402

CACHE = Path(__file__).resolve().parent / "klines"
CACHE.mkdir(exist_ok=True)

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
# 1h: need ~250d warmup before earliest signal (2026-02-07) -> start mid-2025
SPECS = {
    "1h":  "2025-06-01",
    "15m": "2026-01-20",
}
END = "2026-06-04"


def get(symbol: str, interval: str, start: str, end: str) -> pd.DataFrame:
    fp = CACHE / f"{symbol}_{interval}.pkl"
    if fp.exists():
        df = pd.read_pickle(fp)
        print(f"  cached {symbol} {interval}: {len(df)} bars {df.index[0]} -> {df.index[-1]}")
        return df
    s = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    e = int(pd.Timestamp(end, tz="UTC").timestamp() * 1000)
    print(f"  fetching {symbol} {interval} {start} -> {end} ...")
    df = fetch_klines(symbol, interval, s, e)
    if df.empty:
        raise SystemExit(f"no data for {symbol} {interval}")
    df.to_pickle(fp)
    print(f"    -> {len(df)} bars {df.index[0]} -> {df.index[-1]}")
    return df


if __name__ == "__main__":
    for interval, start in SPECS.items():
        for sym in SYMBOLS:
            get(sym, interval, start, END)
    print("done.")
