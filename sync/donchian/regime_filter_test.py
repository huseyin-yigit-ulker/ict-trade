"""dch30_4h FALSE-BREAKOUT filter experiment — crypto+metal, no DB write.

Diagnosis (crypto+metal): the hybrid loses in market-wide FAILED-BREAKOUT regimes — months
where WR drops <20% (RR=4 breakeven), 70-90% of symbols red together, usually right after a
parabolic trend exhausts. Root cause = marginal / false breakouts that the lagging 4h filter
still confirms. This tests two parsimonious filters that attack that directly:

  margin : require the breakout close to CLEAR the 55-bar channel by >= k * ATR (not a
           marginal poke). margin_atr = (close - channel_hi)/ATR  [long]  (>=0 always).
  er30   : require a stronger base-30m Kaufman ER at the breakout bar (cleaner trend).

Each 4h-confirmed signal is resolved on 1m ONCE; every (margin, er30) combo is then a mask.
Reported per combo: total R, WR, n, and the MONTHLY profile (neg-month count + worst month)
— because the goal is cutting the bad regimes, not just lifting total R.

    python sync/donchian/regime_filter_test.py --start 2026-01-01            # short backtest
    python sync/donchian/regime_filter_test.py --start 2024-01-01 --end 2026-01-01   # OOS
"""
from __future__ import annotations

import os
import sys
import pickle
import argparse
from pathlib import Path
from collections import defaultdict

import pandas as pd

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))
sys.path.insert(0, str(_HERE.parent))
import trade_sync_common as tsc              # noqa: E402
import strategy as strat                     # noqa: E402
from ict import config as C                  # noqa: E402

TF_MIN = strat.TF_MINUTES
CACHE = Path(os.environ.get("DONCHIAN_1M_CACHE", "/tmp/donchian1m_cache"))
STOCK = {'NVDAUSDT','METAUSDT','AMZNUSDT','COINUSDT','MSTRUSDT','CRCLUSDT','PLTRUSDT','TSLAUSDT',
         'INTCUSDT','HOODUSDT','MSFTUSDT','AVGOUSDT','BABAUSDT','BXUSDT','HPEUSDT','AMATUSDT',
         'CRWDUSDT','CRDOUSDT','AAOIUSDT','IWMUSDT'}
CRYPTO_METAL = [s for s in strat.SYMBOLS if s not in STOCK]


def _warmup(tf): return pd.Timedelta(minutes=TF_MIN[tf] * (strat.N_ENTRY + strat.ER_N) * 6)
def _kl(sym, tf, a, b): return tsc.fetch_klines(sym, tf, int(a.timestamp()*1000), int(b.timestamp()*1000))


def _load_1m(sym, start, end):
    cf = CACHE / f"{sym}.pkl"
    if cf.exists():
        return pickle.loads(cf.read_bytes())
    df = tsc.fetch_1m(sym, start - pd.Timedelta(hours=2), end)
    if df is not None and not df.empty:
        CACHE.mkdir(exist_ok=True); cf.write_bytes(pickle.dumps(df))
    return df


def run_symbol(sym, w_start, w_end):
    df = _kl(sym, "30m", w_start - _warmup("30m"), w_end)
    if df is None or df.empty:
        return []
    sigs = [s for s in strat.generate_signals(df, sym) if w_start <= s.timestamp < w_end]
    if not sigs:
        return []
    hdf = _kl(sym, "4h", w_start - _warmup("4h"), w_end)
    sigs = strat.htf_confirm(sigs, "30m", hdf, "4h")           # 4h-direction confirmed only
    if not sigs:
        return []
    df1m = _load_1m(sym, w_start, w_end)
    if df1m is None or df1m.empty:
        return []
    # recompute the 30m channel + ATR + ER to annotate each signal with breakout margin
    a = strat.atr(df); er = strat.eff_ratio(df["close"])
    hi = df["high"].rolling(strat.N_ENTRY).max().shift(1)
    lo = df["low"].rolling(strat.N_ENTRY).min().shift(1)
    # VOLUME expansion: breakout-bar volume vs the trailing 20-bar avg (causal, shift(1)).
    # vol_ratio>1 => the break fired on rising volume (higher-conviction, less likely false).
    vol_sma = df["volume"].rolling(20).mean().shift(1)
    pos = {ts: i for i, ts in enumerate(df.index)}

    prev = C.PARTIAL_TP_ENABLED; C.PARTIAL_TP_ENABLED = False
    out = []
    try:
        for s in sigs:
            i = pos.get(s.timestamp)
            if i is None or not (a.iloc[i] > 0):
                continue
            margin = ((s.entry - hi.iloc[i]) if s.direction == "long"
                      else (lo.iloc[i] - s.entry)) / a.iloc[i]   # ATR units, >=0 on a real break
            vsma = vol_sma.iloc[i]
            vratio = float(df["volume"].iloc[i] / vsma) if vsma and vsma > 0 else float("nan")
            res = tsc.simulate(sym, s.timestamp, s.direction, s.entry, s.stop_loss,
                               s.take_profit_1, df1m=df1m, ltf_minutes=30,
                               expiry_minutes=s.expiry_minutes)
            if res["status"] not in ("closed_tp", "closed_sl") or res["pnl_r"] is None:
                continue
            out.append({"month": f"{s.timestamp.year}-{s.timestamp.month:02d}",
                        "r": float(res["pnl_r"]), "win": res["status"] == "closed_tp",
                        "margin": float(margin), "er30": float(er.iloc[i]), "vol": vratio})
    finally:
        C.PARTIAL_TP_ENABLED = prev
    return out


def _v(r):  # NaN-safe volume ratio
    x = r.get("vol"); return x if x == x else 0.0


COMBOS = {
    "baseline":          lambda r: True,
    "vol>=1.0":          lambda r: _v(r) >= 1.0,
    "vol>=1.25":         lambda r: _v(r) >= 1.25,
    "vol>=1.5":          lambda r: _v(r) >= 1.5,
    "vol>=2.0":          lambda r: _v(r) >= 2.0,
    "margin>=0.50":      lambda r: r["margin"] >= 0.50,
    "er30>=0.55":        lambda r: r["er30"] >= 0.55,
    "vol>=1.5 & er>=0.45": lambda r: _v(r) >= 1.5 and r["er30"] >= 0.45,
    "vol>=1.5 & m>=0.5": lambda r: _v(r) >= 1.5 and r["margin"] >= 0.5,
}


def evaluate(rows):
    base_n = len(rows)
    print(f"\n=== PANEL (crypto+metal, {base_n} 4h-confirmed trades) ===")
    print(f"{'combo':<19}{'n':>5}{'%kept':>6}{'WR':>5}{'totR':>8}{'R/tr':>7}"
          f"{'negAy':>6}{'enKötüAy':>10}")
    print("-" * 66)
    for name, pred in COMBOS.items():
        sel = [r for r in rows if pred(r)]
        if not sel:
            print(f"{name:<19}{0:>5}"); continue
        n = len(sel); tot = sum(r["r"] for r in sel)
        wr = 100 * sum(r["win"] for r in sel) / n
        mo = defaultdict(float)
        for r in sel:
            mo[r["month"]] += r["r"]
        negc = sum(1 for v in mo.values() if v < 0)
        worst = min(mo.values()) if mo else 0.0
        print(f"{name:<19}{n:>5}{100*n/base_n:>5.0f}%{wr:>4.0f}%{tot:>+8.0f}"
              f"{tot/n:>+7.3f}{negc:>4}/{len(mo):<2}{worst:>+9.0f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-01-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--symbols", nargs="*", default=CRYPTO_METAL)
    args = ap.parse_args()
    w_start = pd.Timestamp(args.start, tz="UTC")
    w_end = pd.Timestamp(args.end, tz="UTC") if args.end else pd.Timestamp.now(tz="UTC")
    print(f"=== dch30_4h regime-filter test [{w_start.date()}..{w_end.date()}) "
          f"| {len(args.symbols)} crypto+metal ===", flush=True)
    allrows = []
    for sym in args.symbols:
        try:
            rs = run_symbol(sym, w_start, w_end); allrows += rs
            print(f"  {sym:<10} {len(rs):>4} trades", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {sym}: {e}", flush=True)
    evaluate(allrows)


if __name__ == "__main__":
    main()
