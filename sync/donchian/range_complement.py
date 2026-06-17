"""Is the RANGE book a diversifier for dch30_4h? — EXPERIMENT, no DB write.

Re-runs the RANGE stream (sync/backfill_range.py production config: RANGE_DEV fade, ensemble
TREND gate, full-TP) on crypto+metal, buckets its monthly R, and correlates with dch30_4h's
monthly R (crypto+metal). Negative/low correlation + RANGE positive = a genuine diversifier
that flattens the combined curve (unlike Turtle Soup, which just took the losing side of
dch30_4h's own momentum edge). Imports backfill_range.run_symbol — no DB write.

    python sync/donchian/range_complement.py --years 2026
    python sync/donchian/range_complement.py --years 2024 2025 2026
"""
from __future__ import annotations

import sys
import argparse
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))
import trade_sync_common as tsc           # noqa: E402
import regime_ensemble as RE              # noqa: E402
import backfill_range as BR               # noqa: E402

STOCK = {'NVDAUSDT','METAUSDT','AMZNUSDT','COINUSDT','MSTRUSDT','CRCLUSDT','PLTRUSDT','TSLAUSDT',
         'INTCUSDT','HOODUSDT','MSFTUSDT','AVGOUSDT','BABAUSDT','BXUSDT','HPEUSDT','AMATUSDT',
         'CRWDUSDT','CRDOUSDT','AAOIUSDT','IWMUSDT'}
RANGE_CM = [s for s in BR.SYMBOLS if s not in STOCK]   # RANGE's crypto+metal universe

# RANGE production config (mirror backfill_range main() defaults)
BR.GATE_VERDICTS = {"trend"}
BR.VERSION = "range"
BR.MIN_SCORE = 0.0
BR.MIN_RR = 0.0
BR.DROP_BAND = None


def range_monthly(year):
    w_start = pd.Timestamp(f"{year}-01-01", tz="UTC")
    w_end = min(pd.Timestamp(f"{year+1}-01-01", tz="UTC"), pd.Timestamp.now(tz="UTC"))
    ens_start = int((w_start - pd.Timedelta(days=BR.ENSEMBLE_WARMUP_DAYS)).timestamp() * 1000)
    mo = defaultdict(float); n = 0; tot = 0.0
    for sym in RANGE_CM:
        try:
            kl = BR.fetch_4h(sym, ens_start)
            roll = RE.build_rolling(kl) if len(kl) >= 80 else None
            rows = BR.run_symbol(sym, w_start, w_end, roll)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {sym}: {e}", flush=True); continue
        for r in rows:
            if r["status"] in ("closed_tp", "closed_sl") and r["pnl_r"] is not None:
                ts = pd.Timestamp(r["signal_time"])
                mo[f"{ts.year}-{ts.month:02d}"] += float(r["pnl_r"]); n += 1; tot += float(r["pnl_r"])
    print(f"  RANGE {year}: {n} trades, total {tot:+.0f}R")
    return mo


def dch_monthly(years):
    c = tsc.backtest_conn(); cur = c.cursor()
    lo = pd.Timestamp(f"{min(years)}-01-01", tz="UTC"); hi = pd.Timestamp(f"{max(years)+1}-01-01", tz="UTC")
    cur.execute("""SELECT symbol, signal_time, pnl_r FROM ict_trade.trading_signals
        WHERE version='dch30_4h' AND status IN ('closed_tp','closed_sl') AND pnl_r IS NOT NULL
          AND signal_time >= %s AND signal_time < %s""", (lo.to_pydatetime(), hi.to_pydatetime()))
    mo = defaultdict(float)
    for sym, ts, r in cur.fetchall():
        if sym not in STOCK:
            mo[f"{ts.year}-{ts.month:02d}"] += float(r)
    c.close()
    return mo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", nargs="*", type=int, default=[2026])
    args = ap.parse_args()
    print(f"=== RANGE-as-complement [{args.years}] | {len(RANGE_CM)} crypto+metal ===", flush=True)

    rng = defaultdict(float)
    for y in args.years:
        for k, v in range_monthly(y).items():
            rng[k] += v
    dch = dch_monthly(args.years)

    months = sorted(set(rng) | set(dch))
    d = np.array([dch.get(m, 0.0) for m in months])
    r = np.array([rng.get(m, 0.0) for m in months])
    comb = d + r
    corr = float(np.corrcoef(d, r)[0, 1]) if len(months) > 1 and d.std() > 0 and r.std() > 0 else float("nan")

    print(f"\n=== aylık R: dch30_4h vs RANGE (crypto+metal) ===")
    print(f"  korelasyon = {corr:+.2f}   (negatif/düşük = iyi tamamlayıcı)")
    print(f"  toplam R:  dch30_4h {d.sum():+.0f}   RANGE {r.sum():+.0f}   birleşik {comb.sum():+.0f}")
    print(f"  negatif ay: dch {sum(v<0 for v in d)}/{len(months)} -> birleşik {sum(v<0 for v in comb)}/{len(months)}")
    print(f"  en kötü ay: dch {d.min():+.0f} -> birleşik {comb.min():+.0f}")
    # volatility of monthly R (lower = smoother) — the real diversification payoff
    print(f"  aylık R std: dch {d.std():.0f} -> birleşik {comb.std():.0f}")
    print("\n  ay        dch30_4h    RANGE   birleşik")
    for m, dv, rv, cv in zip(months, d, r, comb):
        flag = "  <<<" if dv < 0 else ""
        print(f"  {m}  {dv:>+9.0f}{rv:>+9.0f}{cv:>+9.0f}{flag}")


if __name__ == "__main__":
    main()
