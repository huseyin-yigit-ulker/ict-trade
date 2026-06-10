"""Throwaway ablation harness for RADAR v3 (strategy F) entry/TP design, over 2026
in memory, reusing one kline fetch per symbol, NO DB writes. Sibling of
experiment_v2.py.

Motivation: the first full v3 dry-run showed the RETEST-limit adaptation losing
(fills cluster ~1.3h after the breakout = we are systematically filled on FAILED
breakouts, the exact trap the ICT engine fades). The literature design enters AT
the breakout (market/stop), which the engine's close-through-entry filter forbids
for entry==close — but entry = close -/+ eps passes the filter and fills on the
next 1m bar, i.e. an honest taker-at-close approximation.

Variants (same data, same 1m resolution, same fees):
  entry in {retest (broken channel level), market (close -/+ 0.05%)}
  tp_r  in {3.0, 2.0}
"""
from __future__ import annotations
import sys
import uuid
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trade_sync_common as tsc
from ict import config as C
from engine import run_engine
from ict.strategies import Signal, _radar_features, _floor_stop, _rr

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
    "1000PEPEUSDT", "WIFUSDT", "SUIUSDT",
    "NEARUSDT", "FETUSDT", "ADAUSDT", "SUSDT",
    "ARBUSDT", "ORDIUSDT", "ONDOUSDT",
    "XAUUSDT", "XAGUSDT",
    "NVDAUSDT", "METAUSDT", "AMZNUSDT", "COINUSDT", "MSTRUSDT",
]
WIN_START = pd.Timestamp("2026-01-01", tz="UTC")
now = pd.Timestamp.now(tz="UTC")
WIN_END = now
MKT_EPS = 0.0005   # market-entry approximation: limit 0.05% inside the close


def make_strategy_f(entry_mode: str, tp_r: float):
    """strategy_f clone with parametrized entry mechanics + TP multiple.
    Mirrors ict.strategies.strategy_f exactly except the two knobs."""
    label = f"F_{entry_mode}_{tp_r:g}R"

    def fn(symbol, df, at_index, atr_series, structure_events,
           liquidity_levels, obs, fvgs, htf_bias_series=None, expiry_bars=None):
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
            return None
        if a24 <= 0 or sma_prev <= 0 or vmed <= 0:
            return None
        close = float(df["close"].iloc[i])
        volume = float(df["volume"].iloc[i])
        if close > float(dc_hi):
            direction, level = "long", float(dc_hi)
        elif close < float(dc_lo):
            direction, level = "short", float(dc_lo)
        else:
            return None
        comp_ratio = float(a24_prev) / float(sma_prev)
        if not (comp_ratio < C.RADAR_COMPRESSION_MAX):
            return None
        vol_ratio = volume / float(vmed)
        if not (vol_ratio > C.RADAR_VOL_SURGE_MIN):
            return None
        if direction == "long" and not (close > float(ema)):
            return None
        if direction == "short" and not (close < float(ema)):
            return None
        if abs(close - level) > C.RADAR_CHASE_MAX_ATR * float(a24):
            return None
        lo = max(0, i - C.RADAR_REFIRE_BARS)
        trig = f["brk_up"] if direction == "long" else f["brk_dn"]
        if bool(trig.iloc[lo:i].any()):
            return None

        if entry_mode == "retest":
            entry = level
        else:  # market-at-close approximation
            entry = close * (1 - MKT_EPS) if direction == "long" else close * (1 + MKT_EPS)
        stop = entry - C.RADAR_SL_ATR_MULT * float(a24) if direction == "long" \
            else entry + C.RADAR_SL_ATR_MULT * float(a24)
        stop = _floor_stop(entry, stop, direction, float(a24))
        risk = abs(entry - stop)
        if risk <= 0:
            return None
        tp1 = entry + tp_r * risk if direction == "long" else entry - tp_r * risk

        return Signal(
            signal_id=str(uuid.uuid4()), timestamp=df.index[i], strategy=label,
            symbol=symbol, direction=direction,
            entry=float(entry), stop_loss=float(stop),
            take_profit_1=float(tp1), take_profit_2=None,
            risk_reward_1=float(_rr(entry, stop, tp1, direction)), risk_reward_2=None,
            quality="medium",
            confluence_factors=["regime_aligned", "vol_compression", "volume_surge"],
            context={}, expires_at_index=i + C.RADAR_ENTRY_EXPIRY_BARS, bar_index=i,
        )

    fn.__name__ = label
    return fn


CONFIGS = {
    "retest 3R (prod)": make_strategy_f("retest", 3.0),
    "market 3R":        make_strategy_f("market", 3.0),
    "retest 2R":        make_strategy_f("retest", 2.0),
    "market 2R":        make_strategy_f("market", 2.0),
}


def evaluate(df, df1m, symbol, fn):
    signals = run_engine(symbol, df, strategies=[fn])
    res, unfilled = [], 0
    for s in signals:
        if not (WIN_START <= s.timestamp < WIN_END):
            continue
        o = tsc.simulate(symbol, s.timestamp, s.direction, s.entry,
                         s.stop_loss, s.take_profit_1, df1m=df1m,
                         expiry_minutes=C.RADAR_ENTRY_EXPIRY_BARS * 60)
        if o["raw_status"] in ("tp_hit", "sl_hit") and o["pnl_r"] is not None:
            res.append(o["pnl_r"])
        elif o["raw_status"] in ("expired", "invalidated"):
            unfilled += 1
    return res, unfilled


def main():
    warmup = WIN_START - pd.Timedelta(hours=6000)
    cache = {}
    print(f"Fetching {len(SYMBOLS)} symbols (1h + 1m, once)...")
    for sym in SYMBOLS:
        df = tsc.fetch_1h(sym, warmup, now)
        if df.empty:
            print(f"  {sym}: no data, skip"); continue
        df1m = tsc.fetch_1m(sym, WIN_START - pd.Timedelta(hours=2), WIN_END)
        cache[sym] = (df, df1m)
        print(f"  {sym}: {len(df)} 1h bars cached")

    print("\n=== 2026 RADAR v3 ABLATION (resolved trades, same data) ===")
    print(f'{"config":<20}{"trd":>5}{"unfl":>6}{"win%":>7}{"avgR":>8}{"totR":>9}')
    for label, fn in CONFIGS.items():
        rs, unfilled = [], 0
        for sym, (df, df1m) in cache.items():
            r, u = evaluate(df, df1m, sym, fn)
            rs += r; unfilled += u
        n = len(rs)
        wins = sum(1 for r in rs if r > 0)
        total = sum(rs)
        avg = total / n if n else 0
        win = 100 * wins / n if n else 0
        print(f'{label:<20}{n:>5}{unfilled:>6}{win:>7.1f}{avg:>8.3f}{total:>9.1f}')


if __name__ == "__main__":
    main()
