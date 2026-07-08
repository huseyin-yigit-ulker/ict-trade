"""3-way: MIDAS vs TALOS-ICHI vs OPUS — the live streams side by side, 2026.

MIDAS + TALOS-ICHI = gold XAU 1m trailing (MIDAS walk, $0.50/oz FX). OPUS = d30so8f3h7 crypto
Donchian scale-out on the 5 LIVE symbols (BTC/ETH/SOL/FET/ARB), real-money stream. All in R units.
Reports each stream's 2026 stats + pairwise daily-R correlations + the equal-weight 3-way portfolio.
OPUS is a different asset class (crypto) so it should be a near-zero-correlation diversifier to gold.

Run: DCH_ENTRY_AT_CONFIRM=1 .venv/bin/python scratchpad/fx_gold/three_way.py
"""
from __future__ import annotations
import os
import sys
import importlib.util
from pathlib import Path

os.environ.setdefault("DCH_ENTRY_AT_CONFIRM", "1")

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
# Load MIDAS + TALOS-ICHI under UNIQUE module names — 'strategy' must stay free for the Donchian
# module that portfolio_backfill imports (both packages have a strategy.py).
_ms = importlib.util.spec_from_file_location("midas_strategy", REPO / "sync" / "midas" / "strategy.py")
M = importlib.util.module_from_spec(_ms); sys.modules["midas_strategy"] = M; _ms.loader.exec_module(M)
_ts = importlib.util.spec_from_file_location("talos_ichi_strategy", REPO / "sync" / "talos_ichi" / "strategy.py")
TI = importlib.util.module_from_spec(_ts); sys.modules["talos_ichi_strategy"] = TI; _ts.loader.exec_module(TI)
sys.path.insert(0, str(REPO / "sync"))
sys.path.insert(0, str(REPO / "sync" / "donchian"))
import portfolio_backfill as PB          # noqa: E402  (imports the Donchian strategy as 'strategy')

START = pd.Timestamp("2026-01-01", tz="UTC"); END = pd.Timestamp("2026-07-07", tz="UTC")
OPUS_SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "FETUSDT", "ARBUSDT"]


def gold_trades():
    xa = pd.read_pickle(HERE / "xauusdt_1m_2026h1.pkl"); xj = pd.read_pickle(HERE / "xau_jul2026.pkl")
    xau = pd.concat([xa, xj]); xau = xau[~xau.index.duplicated()].sort_index()[["open", "high", "low", "close", "volume"]]
    df = M.add_market_open(xau); df["fx_day"] = M._fx_day(df); atr = M.atr_tf(df)
    ms, mst = M.signals(df, atr)
    mid = [(t.entry_time, t.pnl_r) for t in M.walk(df, ms, mst, atr.to_numpy(), cost=M.COST_RT) if t.entry_time >= START]
    ts, tst = TI.signals(df, atr)
    ti = [(t.entry_time, t.pnl_r) for t in M.walk(df, ts, tst, atr.to_numpy(), cost=TI.COST_RT) if t.entry_time >= START]
    return mid, ti


def opus_trades():
    st = PB.STREAMS["d30so8f3h7"]; out = []
    for sym in OPUS_SYMS:
        try:
            real = PB.walk(PB.build_events(sym, st, START, END), st, START, END)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {sym}: {e}"); continue
        for r in real:
            if r["r"] is not None and r["fill"] is not None:
                out.append((pd.Timestamp(r["fill"]).tz_convert("UTC"), float(r["r"])))
    return out


def stat(tr):
    r = np.array([x[1] for x in tr]); n = len(r)
    if n == 0:
        return dict(n=0, totR=0, avgR=0, WR=0, PF=0, maxDD=0)
    eq = r.cumsum(); dd = float((eq - np.maximum.accumulate(eq)).min())
    pn = r[r > 0].sum(); pdn = -r[r < 0].sum()
    return dict(n=n, totR=round(r.sum(), 1), avgR=round(r.mean(), 3), WR=round(100 * (r > 0).mean()),
                PF=round(pn / pdn if pdn > 0 else 99, 2), maxDD=round(dd, 1))


def daily(tr):
    if not tr:
        return pd.Series(dtype=float)
    return pd.Series([x[1] for x in tr], index=[x[0] for x in tr]).resample("D").sum()


if __name__ == "__main__":
    mid, ti = gold_trades()
    print("OPUS trade'leri üretiliyor (5 canlı kripto, d30so8f3h7) ...", flush=True)
    op = opus_trades()
    books = {"MIDAS": mid, "TALOS-ICHI": ti, "OPUS": op}

    print(f"\n{'='*70}\n3-LÜ KARŞILAŞTIRMA · 2026 (Oca-Tem) · R birimi\n{'='*70}")
    print(f"{'':14}{'n':>5}{'totR':>8}{'avgR':>8}{'WR':>5}{'PF':>6}{'maxDD':>8}")
    for name, tr in books.items():
        s = stat(tr)
        print(f"{name:14}{s['n']:>5}{s['totR']:>+8.1f}{s['avgR']:>+8.3f}{s['WR']:>4}%{s['PF']:>6.2f}{s['maxDD']:>+8.1f}")
    s = stat(mid + ti + op)
    print(f"{'PORTFÖY 3-lü':14}{s['n']:>5}{s['totR']:>+8.1f}{s['avgR']:>+8.3f}{s['WR']:>4}%{s['PF']:>6.2f}{s['maxDD']:>+8.1f}")

    print("\ngünlük-R korelasyonları (düşük = iyi çeşitlendirici):")
    d = {k: daily(v) for k, v in books.items()}
    for a, b in (("MIDAS", "TALOS-ICHI"), ("MIDAS", "OPUS"), ("TALOS-ICHI", "OPUS")):
        both = pd.concat([d[a], d[b]], axis=1, keys=["x", "y"]).fillna(0)
        c = both["x"].corr(both["y"]) if len(both) > 2 else float("nan")
        print(f"  {a:12} ↔ {b:12} = {c:+.3f}")
    print("\nNOT: MIDAS/TALOS-ICHI = altın 1m trailing ($0.50 FX). OPUS = kripto Donchian scale-out")
    print("     (gerçek-para, 5 sembol). OPUS çok-yıl kripto OOS POZİTİF; altın akışları çok-yıl breakeven/neg.")
