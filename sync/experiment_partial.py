"""A/B harness: classic single-TP vs the partial-TP + breakeven exit model, on the
SAME main(v1) and impulse(v2) signals over 2026, in memory, NO DB writes.

For each arm we run the engine ONCE (signals don't depend on the exit model — the
partial logic only changes what happens AFTER entry fills), then resolve every 2026
signal's outcome on 1m TWICE: once with ict/config.PARTIAL_TP_ENABLED=False (the
current production lifecycle) and once with it True (scale out half at half the
distance to TP1, pull the stop to breakeven, ride the rest to TP1). Reports resolved-
trade win% / avg R / total R side by side so the exit model is the only variable.

Note: the classic arm reproduces production behaviour verbatim, including the quirk
that a phase-2 TP is credited gross (no fees) while losses pay fees; the partial arm
charges round-trip fees on every leg. So if anything the comparison is conservative
against the partial model. Run needs Binance (set BINANCE_PROXY on a 451 runner).
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

# Production static universe (mirrors sync/sync_daily.py STATIC_SYMBOLS / dag.py SYMBOLS).
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
    "1000PEPEUSDT", "WIFUSDT", "SUIUSDT",
    "NEARUSDT", "FETUSDT", "ADAUSDT", "SUSDT",
    "ARBUSDT", "ORDIUSDT", "ONDOUSDT",
    "XAUUSDT", "XAGUSDT",
    "NVDAUSDT", "METAUSDT",
    "AMZNUSDT", "COINUSDT", "MSTRUSDT",
]
BASE_D_EXCL = {"NVDAUSDT", "NEARUSDT", "AMZNUSDT", "ORDIUSDT"}
WIN_START = pd.Timestamp("2026-01-01", tz="UTC")
now = pd.Timestamp.now(tz="UTC")
WIN_END = now

# arm -> (strategy set, extra D-exclusion) — exactly the live v1 and v2 streams.
ARMS = {
    "main v1 [BCDE]":            ([strategy_b, strategy_c, strategy_d, strategy_e], set()),
    "impulse v2 [BCD]+Dexcl3":   ([strategy_b, strategy_c, strategy_d], {"ADAUSDT", "XAUUSDT", "ETHUSDT"}),
}


def collect_signals(cache, strats, d_excl):
    """Run the engine once per symbol; return [(symbol, ts, dir, entry, sl, tp), ...]
    for every signal whose timestamp falls in the 2026 window."""
    C.D_EXCLUDE_SYMBOLS = BASE_D_EXCL | d_excl
    sigs = []
    for sym, (df, _df1m) in cache.items():
        for s in run_engine(sym, df, strategies=strats):
            if WIN_START <= s.timestamp < WIN_END:
                sigs.append((sym, s.timestamp, s.direction, s.entry, s.stop_loss, s.take_profit_1))
    return sigs


def resolve(cache, sigs, partial):
    """Resolve every signal on 1m under the given exit model. Returns
    (pnl_list, per_month{month: total_r}) over resolved (tp/sl) trades only."""
    C.PARTIAL_TP_ENABLED = partial
    pnls, by_month = [], {}
    for sym, ts, direction, entry, sl, tp in sigs:
        df1m = cache[sym][1]
        o = tsc.simulate(sym, ts, direction, entry, sl, tp, df1m=df1m)
        if o["raw_status"] in ("tp_hit", "sl_hit") and o["pnl_r"] is not None:
            pnls.append(o["pnl_r"])
            m = ts.strftime("%Y-%m")
            by_month[m] = by_month.get(m, 0.0) + o["pnl_r"]
    return pnls, by_month


def stats(pnls):
    n = len(pnls)
    wins = sum(1 for r in pnls if r > 0)
    total = sum(pnls)
    return n, (100 * wins / n if n else 0.0), (total / n if n else 0.0), total


def main():
    warmup = WIN_START - pd.Timedelta(hours=6000)
    cache = {}
    print(f"Fetching {len(SYMBOLS)} symbols (1h + 1m, once)...")
    for sym in SYMBOLS:
        df = tsc.fetch_1h(sym, warmup, WIN_END)
        if df.empty:
            print(f"  {sym}: no data, skip"); continue
        df1m = tsc.fetch_1m(sym, WIN_START - pd.Timedelta(hours=2), WIN_END)
        cache[sym] = (df, df1m)
        print(f"  {sym}: {len(df)} 1h bars cached")

    print("\n=== 2026 EXIT-MODEL A/B (same signals, resolved trades) ===")
    print(f'{"arm / model":<34}{"trd":>5}{"win%":>7}{"avgR":>8}{"totR":>9}')
    monthly = {}
    for arm, (strats, d_excl) in ARMS.items():
        sigs = collect_signals(cache, strats, d_excl)
        cls_pnls, cls_m = resolve(cache, sigs, partial=False)
        par_pnls, par_m = resolve(cache, sigs, partial=True)
        cn, cw, ca, ct = stats(cls_pnls)
        pn, pw, pa, pt = stats(par_pnls)
        print(f'{arm:<34}')
        print(f'{"  classic single-TP":<34}{cn:>5}{cw:>7.1f}{ca:>8.3f}{ct:>9.1f}')
        print(f'{"  partial-TP + breakeven":<34}{pn:>5}{pw:>7.1f}{pa:>8.3f}{pt:>9.1f}')
        print(f'{"  -> delta totR":<34}{"":>5}{"":>7}{"":>8}{pt - ct:>+9.1f}')
        monthly[arm] = (cls_m, par_m)

    print("\n--- monthly totR: classic -> partial (delta) ---")
    for arm, (cls_m, par_m) in monthly.items():
        print(f"  {arm}")
        for m in sorted(set(cls_m) | set(par_m)):
            c, p = cls_m.get(m, 0.0), par_m.get(m, 0.0)
            print(f"    {m}   {c:>7.1f} -> {p:>7.1f}   ({p - c:>+6.1f})")

    # hygiene: restore defaults for any later import in the same process
    C.PARTIAL_TP_ENABLED = False
    C.D_EXCLUDE_SYMBOLS = BASE_D_EXCL


if __name__ == "__main__":
    main()
