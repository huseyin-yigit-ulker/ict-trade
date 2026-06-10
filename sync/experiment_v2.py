"""Throwaway ablation harness: evaluate several main-strategy CONFIGS over 2026 in
memory, reusing one kline fetch per symbol, NO DB writes. Used to design main v2.

Each config = (strategy set, extra D-exclusion). We run the engine, simulate every
2026 signal's TP/SL on 1m, and report resolved-trade win% / avg R / total R so the
configs are directly comparable on the SAME data.
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trade_sync_common as tsc
from ict import config as C
from engine import run_engine
from ict.strategies import strategy_b, strategy_c, strategy_d, strategy_e

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT",
    "1000PEPEUSDT", "WIFUSDT", "SUIUSDT", "NEARUSDT", "FETUSDT",
    "ADAUSDT", "SUSDT", "ARBUSDT", "ORDIUSDT", "ONDOUSDT", "XAUUSDT", "XAGUSDT",
    "TSLAUSDT", "NVDAUSDT", "METAUSDT", "GOOGLUSDT", "AMZNUSDT",
    "COINUSDT", "PLTRUSDT", "MSTRUSDT",
]
BASE_D_EXCL = {"NVDAUSDT", "NEARUSDT", "AMZNUSDT", "ORDIUSDT"}
WIN_START = pd.Timestamp("2026-01-01", tz="UTC")
now = pd.Timestamp.now(tz="UTC")
WIN_END = now

# label -> (strategy list, extra D-exclusion set)
CONFIGS = {
    "A v1-base [BCDE]":            ([strategy_b, strategy_c, strategy_d, strategy_e], set()),
    "B [BCDE]+Dexcl ADA/XAU/ETH":  ([strategy_b, strategy_c, strategy_d, strategy_e], {"ADAUSDT", "XAUUSDT", "ETHUSDT"}),
    "C [BCD] dropE":               ([strategy_b, strategy_c, strategy_d], set()),
    "D [BCDE]+Dexcl ADA/XAU":      ([strategy_b, strategy_c, strategy_d, strategy_e], {"ADAUSDT", "XAUUSDT"}),
    "E [BCDE]+Dexcl ADA":          ([strategy_b, strategy_c, strategy_d, strategy_e], {"ADAUSDT"}),
}


def evaluate(df, df1m, symbol, strats, win_start, win_end):
    """Return list of pnl_r for resolved trades (TP/SL) of 2026 signals."""
    signals = run_engine(symbol, df, strategies=strats)
    out = []
    for s in signals:
        if not (win_start <= s.timestamp < win_end):
            continue
        o = tsc.simulate(symbol, s.timestamp, s.direction, s.entry,
                         s.stop_loss, s.take_profit_1, df1m=df1m)
        if o["raw_status"] in ("tp_hit", "sl_hit") and o["pnl_r"] is not None:
            out.append(o["pnl_r"])
    return out


def main():
    end = now
    warmup = WIN_START - pd.Timedelta(hours=6000)
    cache = {}
    print(f"Fetching {len(SYMBOLS)} symbols (1h + 1m, once)...")
    for sym in SYMBOLS:
        df = tsc.fetch_1h(sym, warmup, end)
        if df.empty:
            print(f"  {sym}: no data, skip"); continue
        df1m = tsc.fetch_1m(sym, WIN_START - pd.Timedelta(hours=2), min(WIN_END, end))
        cache[sym] = (df, df1m)
        print(f"  {sym}: {len(df)} 1h bars cached")

    results = {}
    for label, (strats, extra_excl) in CONFIGS.items():
        C.D_EXCLUDE_SYMBOLS = BASE_D_EXCL | extra_excl
        rs = []
        for sym, (df, df1m) in cache.items():
            rs += evaluate(df, df1m, sym, strats, WIN_START, WIN_END)
        n = len(rs)
        wins = sum(1 for r in rs if r > 0)
        total = sum(rs)
        avg = total / n if n else 0
        win = 100 * wins / n if n else 0
        results[label] = (n, win, avg, total)

    print("\n=== 2026 ABLATION (resolved trades, same data) ===")
    print(f'{"config":<30}{"trd":>5}{"win%":>7}{"avgR":>8}{"totR":>9}')
    for label, (n, win, avg, total) in results.items():
        print(f'{label:<30}{n:>5}{win:>7.1f}{avg:>8.3f}{total:>9.1f}')


if __name__ == "__main__":
    main()
