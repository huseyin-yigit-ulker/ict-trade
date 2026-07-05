"""Run all candidate strategies on XAUUSDT 1m 2026-H1 (market-open only). Compare, IS/OOS, costs."""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import data as D
import fxstrat as S
from engine import Cfg, backtest, stats, split_stats, cost_sweep

pd.set_option("display.width", 200); pd.set_option("display.max_columns", 30)

df = D.add_market_open(D.load_1m())
atr15 = S.atr_tf(df, "15min", 14)

CFG = Cfg(cost_rt=0.50, max_hold_min=240, risk_pct=0.01)

CANDIDATES = {
    "ORB_NY_30_rr2":     lambda: S.orb(df, (8, 0), or_min=30, rr=2.0, stop_mode="range"),
    "ORB_NY_15_rr2":     lambda: S.orb(df, (8, 0), or_min=15, rr=2.0, stop_mode="range"),
    "ORB_LDN_30_rr2":    lambda: S.orb(df, (3, 0), or_min=30, rr=2.0, stop_mode="range"),
    "ORB_NY_30_atr_rr2": lambda: S.orb(df, (8, 0), or_min=30, rr=2.0, stop_mode="atr", atr_mult=1.0, atr=atr15.to_numpy()),
    "VWAP_trend_rr2":    lambda: S.vwap_trend(df, rr=2.0, atr_mult=1.5, atr=atr15),
    "VWAP_fade_k2":      lambda: S.vwap_fade(df, k=2.0, atr_mult=1.0, atr=atr15),
    "BB_fade_asia":      lambda: S.bb_fade(df, win=20, k=2.0, atr=atr15),
    "MOM_break_60":      lambda: S.mom_break(df, lookback=60, rr=2.0, atr_mult=1.5, atr=atr15),
    "MOM_break_120":     lambda: S.mom_break(df, lookback=120, rr=2.0, atr_mult=1.5, atr=atr15),
}


def buy_hold():
    o = df[df.open_mkt]
    first = o["close"].iloc[0]; last = o["close"].iloc[-1]
    return round((last / first - 1) * 100, 1)


def main():
    print(f"Data: {len(df)} bars, open={int(df.open_mkt.sum())}  | Buy&Hold close-to-close: {buy_hold()}%\n")
    rows = []
    trades_by = {}
    for name, fn in CANDIDATES.items():
        side, stop, target = fn()
        tr = backtest(df, side, stop, target, CFG)
        trades_by[name] = tr
        st = stats(tr, CFG, name)
        rows.append(st)
    res = pd.DataFrame(rows).sort_values("totR", ascending=False)
    print("=== ALL CANDIDATES (cost_rt=$0.50, max_hold=240m) ===")
    print(res[["label", "n", "totR", "wr", "avgR", "pf", "maxddR", "ret_pct", "maxdd_pct", "sharpe"]].to_string(index=False))

    # Detail on the top 3 by totR (require n>=30)
    top = res[res.n >= 30].head(3)["label"].tolist()
    for name in top:
        tr = trades_by[name]
        sp = split_stats(tr, CFG)
        print(f"\n### {name} — IS/OOS/long/short")
        for k in ["all", "is", "oos", "long", "short"]:
            s = sp[k]
            print(f"  {s['label']:14s} n={s['n']:4d} totR={s['totR']:7.1f} wr={s['wr']:.2f} avgR={s['avgR']:+.3f} pf={s['pf']:.2f} dd={s['maxddR']:.1f} ret={s['ret_pct']:+.1f}%")
        print("  monthly R:", sp["monthly"])
        print("  cost sweep:")
        cs = cost_sweep(df, *CANDIDATES[name](), CFG)
        print(cs[["cost_rt", "n", "totR", "wr", "avgR", "pf"]].to_string(index=False))


if __name__ == "__main__":
    main()
