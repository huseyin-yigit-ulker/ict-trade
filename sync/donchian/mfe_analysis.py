"""MFE/MAE study — is RR=4 the right target for dch30_4h? EXPERIMENT, no DB write.

For every FILLED 30m+4h breakout (entry = breakout close, risk = |entry-sl| = 2*ATR), walk
the 1m path for HORIZON days from the fill and, in R units (move / risk), record:
  • t+k  : first time the FAVOURABLE excursion reaches +k R (k = 1,2,3,4,5,6,8)
  • t-1  : first time the ADVERSE excursion reaches -1 R (the SL)
  • MFE  : max favourable R reached in the window
From these:
  A) TP trades (reach +4R before -1R): how far did they run BEYOND +4R? (is 4R too early?)
  B) SL trades (reach -1R before +4R): how far positive did they go BEFORE reversing? (did
     losers offer an exit we missed?)
  C) RR sweep: total R + R/trade if the target were 2/3/4/5/6/8 R (first-touch vs the same
     -1R stop) — the direct test of the 1:4 choice.

    python sync/donchian/mfe_analysis.py --start 2026-01-01
"""
from __future__ import annotations

import os
import sys
import pickle
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))
sys.path.insert(0, str(_HERE.parent))
import trade_sync_common as tsc              # noqa: E402
import strategy as strat                     # noqa: E402
from ict import config as C                  # noqa: E402

CACHE = Path(os.environ.get("DONCHIAN_1M_CACHE", "/tmp/donchian1m_cache"))
HORIZON = pd.Timedelta(days=int(os.environ.get("MFE_HORIZON_DAYS", "20")))
LEVELS = [1, 2, 3, 4, 5, 6, 8]
BIG = 10**9


def _warmup(tf): return pd.Timedelta(minutes=strat.TF_MINUTES[tf] * (strat.N_ENTRY + strat.ER_N) * 6)


def _load_1m(sym, start, end):
    cf = CACHE / f"{sym}.pkl"
    if cf.exists():
        return pickle.loads(cf.read_bytes())
    df = tsc.fetch_1m(sym, start - pd.Timedelta(hours=2), end)
    if df is not None and not df.empty:
        CACHE.mkdir(exist_ok=True); cf.write_bytes(pickle.dumps(df))
    return df


def run_symbol(sym, w_start, w_end):
    df = tsc.fetch_klines(sym, "30m", int((w_start - _warmup("30m")).timestamp() * 1000),
                          int(w_end.timestamp() * 1000))
    if df is None or df.empty:
        return []
    sigs = [s for s in strat.generate_signals(df, sym) if w_start <= s.timestamp < w_end]
    hdf = tsc.fetch_klines(sym, "4h", int((w_start - _warmup("4h")).timestamp() * 1000),
                           int(w_end.timestamp() * 1000))
    sigs = strat.htf_confirm(sigs, "30m", hdf, "4h")
    if not sigs:
        return []
    df1m = _load_1m(sym, w_start, w_end)
    if df1m is None or df1m.empty:
        return []
    idx = df1m.index
    if idx.tz is None:
        df1m = df1m.copy(); df1m.index = idx = idx.tz_localize("UTC")
    H = df1m["high"].values; L = df1m["low"].values; Cl = df1m["close"].values

    prev = C.PARTIAL_TP_ENABLED; C.PARTIAL_TP_ENABLED = False
    out = []
    try:
        for s in sigs:
            res = tsc.simulate(sym, s.timestamp, s.direction, s.entry, s.stop_loss,
                               s.take_profit_1, df1m=df1m, ltf_minutes=30, expiry_minutes=180)
            ft = res["real_entry_time"]
            if ft is None:                                 # entry never filled -> not a trade
                continue
            ft = pd.Timestamp(ft); ft = ft.tz_localize("UTC") if ft.tz is None else ft.tz_convert("UTC")
            p0 = int(idx.searchsorted(ft))
            if p0 >= len(idx):
                continue
            p1 = int(idx.searchsorted(ft + HORIZON))
            risk = abs(float(s.entry) - float(s.stop_loss))
            if risk <= 0 or p1 <= p0:
                continue
            entry = float(s.entry); lng = s.direction == "long"
            hi = H[p0:p1]; lo = L[p0:p1]
            fav = ((hi - entry) if lng else (entry - lo)) / risk     # favourable R per bar (using extreme)
            adv = ((entry - lo) if lng else (hi - entry)) / risk     # adverse R per bar
            favcum = np.maximum.accumulate(fav)
            advcum = np.maximum.accumulate(adv)
            t_sl = int(np.argmax(advcum >= 1.0)) if (advcum >= 1.0).any() else BIG
            tk = {k: (int(np.argmax(favcum >= k)) if (favcum >= k).any() else BIG) for k in LEVELS}
            out.append({"dir": s.direction, "mfe": float(favcum[-1]), "t_sl": t_sl, "tk": tk,
                        "last": (float(Cl[p1 - 1]) - entry) / risk * (1 if lng else -1)})
    finally:
        C.PARTIAL_TP_ENABLED = prev
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-01-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--symbols", nargs="*", default=strat.SYMBOLS)
    args = ap.parse_args()
    w_start = pd.Timestamp(args.start, tz="UTC")
    w_end = pd.Timestamp(args.end, tz="UTC") if args.end else pd.Timestamp.now(tz="UTC")
    print(f"=== dch30_4h MFE study [{w_start.date()}..{w_end.date()}) | {len(args.symbols)} symbols "
          f"| horizon={HORIZON.days}d ===", flush=True)
    rows = []
    for sym in args.symbols:
        try:
            r = run_symbol(sym, w_start, w_end); rows += r
            print(f"  {sym:<10} {len(r):>3} filled", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {sym}: {e}", flush=True)
    n = len(rows)
    if not n:
        print("no trades"); return

    # outcome under RR=4: TP if +4R reached before -1R
    def is_tp(r, k): return r["tk"][k] < r["t_sl"]
    tp4 = [r for r in rows if is_tp(r, 4)]
    sl4 = [r for r in rows if r["t_sl"] < r["tk"][4]]    # hit -1R before +4R
    print(f"\n=== {n} filled trades | RR=4 outcome: {len(tp4)} TP, {len(sl4)} SL, "
          f"{n-len(tp4)-len(sl4)} neither-in-{HORIZON.days}d ===")

    # A) TP trades: how far BEYOND +4R did they run (MFE - 4)?
    beyond = np.array([r["mfe"] - 4 for r in tp4])
    print(f"\n[A] TP işlemleri — +4R SONRASI ne kadar gitti (MFE-4R):")
    print(f"    medyan +{np.median(beyond):.1f}R  ort +{beyond.mean():.1f}R  | "
          f">+1R: {100*np.mean(beyond>=1):.0f}%  >+2R: {100*np.mean(beyond>=2):.0f}%  >+4R: {100*np.mean(beyond>=4):.0f}%")
    print(f"    => TP işlemlerinin MFE medyanı toplam +{np.median([r['mfe'] for r in tp4]):.1f}R")

    # B) SL trades: highest favourable R level reached BEFORE the -1R stop
    favpre = np.array([max((k for k in LEVELS if r["tk"][k] < r["t_sl"]), default=0) for r in sl4])
    print(f"\n[B] SL işlemleri — STOP'tan ÖNCE en çok kaç R pozitife gitti:")
    print(f"    +1R'ye değen: {100*np.mean(favpre>=1):.0f}%  +2R: {100*np.mean(favpre>=2):.0f}%  "
          f"+3R: {100*np.mean(favpre>=3):.0f}%  | medyan ulaşılan kademe +{np.median(favpre):.0f}R")

    # C) RR sweep: first-touch +T vs -1R; unresolved -> mark-to-market at horizon
    print(f"\n[C] RR-sweep (aynı -1R stop, hedef T değişiyor):")
    print(f"    {'hedef':>6}{'TP%':>6}{'totR(gross)':>13}{'R/işlem':>9}")
    for T in [2, 3, 4, 5, 6, 8]:
        tot = 0.0
        for r in rows:
            tT = r["tk"].get(T, BIG)
            if tT < r["t_sl"]:
                tot += T
            elif r["t_sl"] < BIG:
                tot += -1
            else:
                tot += r["last"]                          # neither hit -> mark to market
        wr = 100 * np.mean([1 if r["tk"].get(T, BIG) < r["t_sl"] else 0 for r in rows])
        print(f"    {T:>5}R{wr:>6.0f}%{tot:>+13.0f}{tot/n:>+9.3f}")

    # D) time-to-resolution (days) at targets 4R and 6R
    print(f"\n[D] ÇÖZÜLME SÜRESİ (gün) — ufuk={HORIZON.days}g:")
    print(f"    {'hedef':>6}  {'TP medyan/ort':>16}  {'SL medyan/ort':>16}  {'ufukta çözülen':>15}")
    for T in [4, 6]:
        tps = np.array([r["tk"][T] / 1440 for r in rows if r["tk"][T] < r["t_sl"] and r["tk"][T] < BIG])
        sls = np.array([r["t_sl"] / 1440 for r in rows if r["t_sl"] < r["tk"][T] and r["t_sl"] < BIG])
        res = (len(tps) + len(sls))
        tpd = f"{np.median(tps):.1f} / {tps.mean():.1f}g" if len(tps) else "-"
        sld = f"{np.median(sls):.2f} / {sls.mean():.2f}g" if len(sls) else "-"
        print(f"    {T:>5}R  {tpd:>16}  {sld:>16}  {100*res/n:>13.0f}% ({len(tps)}TP/{len(sls)}SL)")


if __name__ == "__main__":
    main()
