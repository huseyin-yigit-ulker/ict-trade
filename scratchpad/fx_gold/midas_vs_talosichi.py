"""MIDAS vs TALOS-ICHI head-to-head — the two live gold PAPER streams.

Same audited MIDAS walk ($0.50/oz FX), 2026 XAU (Jan-Jul) + PAXG 2024/2025 OOS. Reports each stream
side by side (totR/avgR/WR/PF/maxDD/IS-OOS/taker), their daily-R correlation (diversifier or clone?),
and the equal-weight COMBINED portfolio (both books merged, independent — the real question for a
gold portfolio). Run: .venv/bin/python scratchpad/fx_gold/midas_vs_talosichi.py
"""
from __future__ import annotations
import sys
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "sync" / "midas"))
import strategy as M                    # noqa: E402
_spec = importlib.util.spec_from_file_location("talos_ichi_strategy", REPO / "sync" / "talos_ichi" / "strategy.py")
TI = importlib.util.module_from_spec(_spec); sys.modules["talos_ichi_strategy"] = TI; _spec.loader.exec_module(TI)
sys.path.insert(0, str(REPO / "scratchpad"))
import midas_oos_paxg as P              # noqa: E402


def trades_for(df, start):
    df = df.loc[df.index < df.index.max()]
    df = M.add_market_open(df); df["fx_day"] = M._fx_day(df)
    atr = M.atr_tf(df)
    ms, mst = M.signals(df, atr)
    mid = [t for t in M.walk(df, ms, mst, atr.to_numpy(), cost=M.COST_RT) if t.entry_time >= start]
    ts, tst = TI.signals(df, atr)
    ti = [t for t in M.walk(df, ts, tst, atr.to_numpy(), cost=TI.COST_RT) if t.entry_time >= start]
    return mid, ti


def stat(trades):
    r = np.array([t.pnl_r for t in trades]); n = len(r)
    if n == 0:
        return dict(n=0, totR=0, avgR=0, WR=0, PF=0, maxDD=0, taker=0)
    eq = r.cumsum(); dd = float((eq - np.maximum.accumulate(eq)).min())
    rt = np.array([((t.exit_px - t.entry) * t.side - 1e-3 * t.entry) / abs(t.entry - t.stop) for t in trades])
    pn = r[r > 0].sum(); pdn = -r[r < 0].sum()
    return dict(n=n, totR=round(r.sum(), 1), avgR=round(r.mean(), 3), WR=round(100 * (r > 0).mean()),
                PF=round(pn / pdn if pdn > 0 else 99, 2), maxDD=round(dd, 1), taker=round(rt.sum(), 1))


def daily(trades):
    if not trades:
        return pd.Series(dtype=float)
    return pd.Series([t.pnl_r for t in trades], index=[t.entry_time for t in trades]).resample("D").sum()


def show(label, mid, ti):
    sm, st = stat(mid), stat(ti)
    comb = stat(mid + ti)
    dm, dt = daily(mid), daily(ti)
    both = pd.concat([dm, dt], axis=1, keys=["m", "t"]).fillna(0)
    corr = both["m"].corr(both["t"]) if len(both) > 2 else float("nan")
    print(f"\n{'='*76}\n{label}\n{'='*76}")
    hdr = f"{'':14}{'n':>5}{'totR':>8}{'avgR':>8}{'WR':>5}{'PF':>6}{'maxDD':>8}{'taker':>8}"
    print(hdr)
    for name, s in (("MIDAS", sm), ("TALOS-ICHI", st), ("PORTFÖY (m+t)", comb)):
        print(f"{name:14}{s['n']:>5}{s['totR']:>+8.1f}{s['avgR']:>+8.3f}{s['WR']:>4}%{s['PF']:>6.2f}{s['maxDD']:>+8.1f}{s['taker']:>+8.1f}")
    print(f"günlük-R korelasyon(MIDAS,TALOS-ICHI) = {corr:+.3f}  (düşük = çeşitlendirici)")


if __name__ == "__main__":
    xa = pd.read_pickle(HERE / "xauusdt_1m_2026h1.pkl"); xj = pd.read_pickle(HERE / "xau_jul2026.pkl")
    xau = pd.concat([xa, xj]); xau = xau[~xau.index.duplicated()].sort_index()[["open", "high", "low", "close", "volume"]]
    show("2026 XAU (in-sample)", *trades_for(xau, pd.Timestamp("2026-01-01", tz="UTC")))
    agg = {"MIDAS": [], "TALOS-ICHI": []}
    for yr, (s, e) in {"2024": ("2024-01-01", "2025-01-01"), "2025": ("2025-01-01", "2026-01-01")}.items():
        df = P.load_paxg(pd.Timestamp(s, tz="UTC") - pd.Timedelta(days=2), pd.Timestamp(e, tz="UTC"))
        df = df.loc[(df.index >= pd.Timestamp(s, tz="UTC") - pd.Timedelta(days=2)) & (df.index < pd.Timestamp(e, tz="UTC"))]
        mid, ti = trades_for(df, pd.Timestamp(s, tz="UTC"))
        show(f"{yr} PAXG (OOS)", mid, ti)
        agg["MIDAS"] += mid; agg["TALOS-ICHI"] += ti
    show("3-YIL BİRLEŞİK (2026 XAU dahil değil — yalnız PAXG 24+25 OOS)", agg["MIDAS"], agg["TALOS-ICHI"])
