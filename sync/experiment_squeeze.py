"""Throwaway ablation harness for SQUEEZE v4 (strategy G, funding-extreme squeeze
fade) over Jan-Jun 2026 in memory, reusing one kline+funding fetch per symbol,
NO DB writes. Sibling of experiment_v3.py.

Motivation: design the judge panel's runner-up candidate with its missing points
addressed BEFORE the gate run, and measure each guard's contribution:
  - 4h-settled symbols need per-event 8h-normalization (else half as "crowded"),
  - absolute floor vs trailing percentile: either alone is regime-blind,
  - ignition confirmation vs naked funding-extreme entry (knife-catch test),
  - retrace depth / SL / TP / fill-window mechanics.

Engine fidelity without engine cost: strategy G reads NO detectors, so the
harness builds the DetectorBundle once per symbol and replays run_engine's exact
pipeline (close-through-entry filter -> merge_same_bar -> dedup_zone_signals)
for every config. `--verify` cross-checks the clone against the production
strategy_g via the real run_engine.

Variants (same data, same 1m resolution, same fees): one knob at a time around
BASE = abs 0.05%/8h + 95th pctl + ignition 0.25 ATR + retrace 0.35 ATR,
SL 2.0 ATR, TP 2R, expiry 12h, refire 48h.

RESULT 2026-06-10 (Jan-Jun 2026, 21 symbols): every one of the 17 variants is
negative — BASE -52.2R (116 trades, 24.1% win), best 'abs 0.03%' -36.4R, worst
'tp 3R' -82.5R (12% win). Losses concentrate in Mar/Apr and in metals + stock
perps (XAG/XAU/AMZN/NVDA); crypto fades ~flat. No knob flips the sign => the
funding-fade edge is absent in this regime; verdict recorded in
sync/backfill_v4_year.py, stream stays disabled.
"""
from __future__ import annotations
import argparse
import sys
import uuid
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trade_sync_common as tsc
from ict import config as C
from ict.data import fetch_funding
from engine import build_detectors, dedup_zone_signals, run_engine
from ict.confluence import merge_same_bar
from ict.strategies import Signal, strategy_g, set_funding, _floor_stop, _rr

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
WARMUP = WIN_START - pd.Timedelta(hours=6000)          # match backfill warmup
FUND_START = WARMUP - pd.Timedelta(days=45)            # percentile window + slack

BASE = dict(abs_min=0.0005, pctl=0.95, ign=0.25, retr=0.35,
            sl=2.0, tp=2.0, exp=12, refire=48)


def squeeze_features(symbol: str, df: pd.DataFrame, fdf: pd.DataFrame, p: dict) -> dict | None:
    """Clone of ict.strategies._squeeze_features with parametrized knobs."""
    if fdf is None or len(fdf) < 3:
        return None
    rate = fdf["rate"]
    gap_h = rate.index.to_series().diff().dt.total_seconds() / 3600.0
    gap_h = gap_h.where((gap_h > 0) & (gap_h <= 24.0))
    r8 = rate * (8.0 / gap_h)
    prior = r8.shift(1)
    if p["pctl"] is not None:
        q_lo = prior.rolling(C.SQUEEZE_PCTL_WINDOW, min_periods=C.SQUEEZE_MIN_EVENTS) \
                    .quantile(1.0 - p["pctl"])
        q_hi = prior.rolling(C.SQUEEZE_PCTL_WINDOW, min_periods=C.SQUEEZE_MIN_EVENTS) \
                    .quantile(p["pctl"])
    else:
        q_lo = pd.Series(float("inf"), index=r8.index)
        q_hi = pd.Series(float("-inf"), index=r8.index)
    n_prior = prior.rolling(C.SQUEEZE_PCTL_WINDOW, min_periods=1).count()

    bar_dur = df.index[1] - df.index[0] if len(df) > 1 else pd.Timedelta(hours=1)
    closes = df.index + bar_dur
    ev = pd.DataFrame({"t": rate.index, "r8": r8.values, "q_lo": q_lo.values,
                       "q_hi": q_hi.values, "n_prior": n_prior.values,
                       "r8_prev": r8.shift(1).values, "event_time": rate.index})
    al = pd.merge_asof(pd.DataFrame({"t": closes}), ev, on="t", direction="backward")
    al.index = df.index
    age_h = (closes - al["event_time"]).dt.total_seconds() / 3600.0
    age_h.index = df.index

    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(),
                    (low - prev_close).abs()], axis=1).max(axis=1)
    atr24 = tr.rolling(C.SQUEEZE_ATR_PERIOD, min_periods=C.SQUEEZE_ATR_PERIOD).mean()

    valid = (al["n_prior"] >= C.SQUEEZE_MIN_EVENTS) & (age_h <= C.SQUEEZE_STALE_HOURS)
    body = close - df["open"]
    ign_up = body >= p["ign"] * atr24
    ign_dn = -body >= p["ign"] * atr24
    ext_lo = (al["r8"] <= -p["abs_min"]) & (al["r8"] <= al["q_lo"])
    ext_hi = (al["r8"] >= p["abs_min"]) & (al["r8"] >= al["q_hi"])
    return {"atr24": atr24, "r8": al["r8"],
            "trig_long": (valid & ext_lo & ign_up).fillna(False),
            "trig_short": (valid & ext_hi & ign_dn).fillna(False)}


def make_strategy_g(p: dict):
    """strategy_g clone with parametrized knobs (features injected per symbol)."""
    label = (f"G_a{p['abs_min']*1e4:g}_p{p['pctl'] if p['pctl'] else 'off'}"
             f"_i{p['ign']:g}_r{p['retr']:g}_sl{p['sl']:g}_tp{p['tp']:g}")
    feats_by_symbol: dict[str, dict] = {}

    def bind(symbol, feats):
        feats_by_symbol[symbol] = feats

    def fn(symbol, df, at_index, atr_series, structure_events,
           liquidity_levels, obs, fvgs, htf_bias_series=None, expiry_bars=None):
        i = at_index
        f = feats_by_symbol.get(symbol)
        if f is None or i < 1 or i >= len(df):
            return None
        a24 = f["atr24"].iloc[i]
        if pd.isna(a24) or a24 <= 0:
            return None
        if f["trig_long"].iloc[i]:
            direction = "long"
        elif f["trig_short"].iloc[i]:
            direction = "short"
        else:
            return None
        lo = max(0, i - p["refire"])
        trig = f["trig_long"] if direction == "long" else f["trig_short"]
        if bool(trig.iloc[lo:i].any()):
            return None
        close = float(df["close"].iloc[i])
        a24 = float(a24)
        entry = close - p["retr"] * a24 if direction == "long" else close + p["retr"] * a24
        stop = entry - p["sl"] * a24 if direction == "long" else entry + p["sl"] * a24
        stop = _floor_stop(entry, stop, direction, a24)
        risk = abs(entry - stop)
        if risk <= 0:
            return None
        tp1 = entry + p["tp"] * risk if direction == "long" else entry - p["tp"] * risk
        return Signal(
            signal_id=str(uuid.uuid4()), timestamp=df.index[i], strategy=label,
            symbol=symbol, direction=direction,
            entry=float(entry), stop_loss=float(stop),
            take_profit_1=float(tp1), take_profit_2=None,
            risk_reward_1=float(_rr(entry, stop, tp1, direction)), risk_reward_2=None,
            quality="medium",
            confluence_factors=["funding_extreme", "crowding_percentile", "squeeze_ignition"],
            context={"funding_8h": float(f["r8"].iloc[i])},
            expires_at_index=i + p["exp"], bar_index=i,
        )

    fn.__name__ = label
    fn.bind = bind
    return fn


def engine_replay(symbol, df, bundle, fn) -> list[Signal]:
    """run_engine's exact post-strategy pipeline, reusing a prebuilt bundle."""
    raw = []
    for i in range(max(C.ATR_PERIOD + 5, C.SWING_N_ITF + 5), len(df)):
        sig = fn(symbol, df, i, bundle.atr, bundle.structure, bundle.liquidity,
                 bundle.order_blocks, bundle.fvgs,
                 htf_bias_series=bundle.htf_bias_series, expiry_bars=bundle.expiry_bars)
        if sig is None:
            continue
        c = float(df["close"].iloc[sig.bar_index])
        if (c <= sig.entry) if sig.direction == "long" else (c >= sig.entry):
            continue
        raw.append(sig)
    return dedup_zone_signals(merge_same_bar(raw), bundle.bar_minutes)


def evaluate(symbol, df, df1m, bundle, fn, exp_bars) -> tuple[list, int]:
    signals = engine_replay(symbol, df, bundle, fn)
    res, unfilled = [], 0
    for s in signals:
        if not (WIN_START <= s.timestamp < WIN_END):
            continue
        o = tsc.simulate(symbol, s.timestamp, s.direction, s.entry, s.stop_loss,
                         s.take_profit_1, df1m=df1m, expiry_minutes=exp_bars * 60)
        if o["raw_status"] in ("tp_hit", "sl_hit") and o["pnl_r"] is not None:
            res.append({"sym": symbol, "ts": s.timestamp, "dir": s.direction,
                        "r": o["pnl_r"]})
        elif o["raw_status"] in ("expired", "invalidated"):
            unfilled += 1
    return res, unfilled


CONFIGS: dict[str, dict] = {
    "BASE":        BASE,
    "abs 0.03%":   {**BASE, "abs_min": 0.0003},
    "abs 0.10%":   {**BASE, "abs_min": 0.0010},
    "pctl off":    {**BASE, "pctl": None},
    "pctl 0.90":   {**BASE, "pctl": 0.90},
    "ign off":     {**BASE, "ign": 0.0},
    "ign 0.50":    {**BASE, "ign": 0.50},
    "retr 0.20":   {**BASE, "retr": 0.20},
    "retr 0.50":   {**BASE, "retr": 0.50},
    "tp 1.5R":     {**BASE, "tp": 1.5},
    "tp 2.5R":     {**BASE, "tp": 2.5},
    "tp 3R":       {**BASE, "tp": 3.0},
    "sl 1.5":      {**BASE, "sl": 1.5},
    "sl 2.5":      {**BASE, "sl": 2.5},
    "exp 6h":      {**BASE, "exp": 6},
    "exp 24h":     {**BASE, "exp": 24},
    "refire 24h":  {**BASE, "refire": 24},
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="*", default=SYMBOLS)
    ap.add_argument("--configs", nargs="*", default=None,
                    help="subset of config labels (default: all)")
    ap.add_argument("--verify", action="store_true",
                    help="cross-check clone vs production strategy_g via run_engine")
    ap.add_argument("--detail", action="store_true",
                    help="per-month and per-symbol breakdown for BASE-family configs")
    args = ap.parse_args()

    cache = {}
    print(f"Fetching {len(args.symbols)} symbols (1h + 1m + funding, once)...")
    for sym in args.symbols:
        df = tsc.fetch_1h(sym, WARMUP, now)
        if df.empty:
            print(f"  {sym}: no klines, skip"); continue
        fdf = fetch_funding(sym, int(FUND_START.timestamp() * 1000),
                            int(now.timestamp() * 1000))
        if fdf.empty:
            print(f"  {sym}: no funding history, skip"); continue
        df1m = tsc.fetch_1m(sym, WIN_START - pd.Timedelta(hours=2), WIN_END)
        bundle = build_detectors(df)
        cache[sym] = (df, df1m, fdf, bundle)
        print(f"  {sym}: {len(df)} 1h bars, {len(fdf)} funding events cached")

    if args.verify:
        print("\n=== VERIFY clone vs production strategy_g (run_engine) ===")
        for sym, (df, _df1m, fdf, bundle) in cache.items():
            set_funding(sym, fdf)
            prod = run_engine(sym, df, strategies=[strategy_g])
            fn = make_strategy_g(BASE)
            fn.bind(sym, squeeze_features(sym, df, fdf, BASE))
            clone = engine_replay(sym, df, bundle, fn)
            pk = {(str(s.timestamp), s.direction, round(s.entry, 8)) for s in prod}
            ck = {(str(s.timestamp), s.direction, round(s.entry, 8)) for s in clone}
            tag = "OK" if pk == ck else f"MISMATCH prod={len(pk)} clone={len(ck)}"
            print(f"  {sym:<14} {len(pk):>3} signals -> {tag}")
        return

    labels = args.configs or list(CONFIGS)
    print("\n=== 2026 SQUEEZE v4 ABLATION (resolved trades, same data) ===")
    print(f'{"config":<14}{"trd":>5}{"unfl":>6}{"win%":>7}{"avgR":>8}{"totR":>9}')
    detail_rows = {}
    for label in labels:
        p = CONFIGS[label]
        fn = make_strategy_g(p)
        rs, unfilled = [], 0
        for sym, (df, df1m, fdf, bundle) in cache.items():
            fn.bind(sym, squeeze_features(sym, df, fdf, p))
            r, u = evaluate(sym, df, df1m, bundle, fn, p["exp"])
            rs += r; unfilled += u
        n = len(rs)
        wins = sum(1 for x in rs if x["r"] > 0)
        total = sum(x["r"] for x in rs)
        print(f'{label:<14}{n:>5}{unfilled:>6}{100*wins/n if n else 0:>7.1f}'
              f'{total/n if n else 0:>8.3f}{total:>9.1f}')
        detail_rows[label] = rs

    if args.detail:
        for label in labels:
            rs = detail_rows[label]
            if not rs:
                continue
            print(f"\n--- {label}: monthly ---")
            bym = {}
            for x in rs:
                bym.setdefault(str(x["ts"])[:7], []).append(x["r"])
            for m in sorted(bym):
                v = bym[m]
                print(f"  {m}  n={len(v):<4} totR={sum(v):>7.1f}")
            print(f"--- {label}: per symbol ---")
            bys = {}
            for x in rs:
                bys.setdefault(x["sym"], []).append(x["r"])
            for s_ in sorted(bys, key=lambda k: -sum(bys[k])):
                v = bys[s_]
                print(f"  {s_:<14} n={len(v):<4} totR={sum(v):>7.1f}")


if __name__ == "__main__":
    main()
