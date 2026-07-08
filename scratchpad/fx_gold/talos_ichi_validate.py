"""TALOS-ICHI full validation battery (the ship bar TALOS/MIDAS had to clear).

1. ICHIMOKU PERIOD PLATEAU — sweep (tenkan, kijun, senkou_b, shift) around the classic (9,26,52,26).
   A real edge is a SMOOTH plateau, not a single-cell spike.
2. RANDOM-DROP NULL — the Kumo filter keeps ~71% of TALOS signals (230/325). Is its selection
   SKILLFUL, or would randomly dropping the same fraction do as well? 500 random-drops -> band; the
   real filter's totR/avgR/PF must sit ABOVE the band (report a permutation p-value).
3. MONTHLY / YEARLY STABILITY — per-month R for the filtered book, 2026 + PAXG 2024/2025.
4. MULTI-YEAR OOS — the 3-year FULL vs FILTERED summary (avgR/WR/PF must improve every year).

Engine + cost identical to production (MIDAS walk, $0.50/oz). Run:
  .venv/bin/python scratchpad/fx_gold/talos_ichi_validate.py
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
import strategy as MS                    # noqa: E402
_spec = importlib.util.spec_from_file_location("talos_strategy", REPO / "sync" / "talos" / "strategy.py")
T = importlib.util.module_from_spec(_spec); sys.modules["talos_strategy"] = T; _spec.loader.exec_module(T)
sys.path.insert(0, str(REPO / "scratchpad"))
import midas_oos_paxg as P               # noqa: E402
RNG = np.random.default_rng(20260708)


def kumo(df, tenkan=9, kijun=26, senkou_b=52, shift=26):
    g = df.resample("15min", label="right", closed="right").agg({"high": "max", "low": "min"}).dropna()
    tk = (g["high"].rolling(tenkan).max() + g["low"].rolling(tenkan).min()) / 2
    kj = (g["high"].rolling(kijun).max() + g["low"].rolling(kijun).min()) / 2
    sa = ((tk + kj) / 2).shift(shift)
    sb = ((g["high"].rolling(senkou_b).max() + g["low"].rolling(senkou_b).min()) / 2).shift(shift)
    return sa.reindex(df.index, method="ffill").to_numpy(), sb.reindex(df.index, method="ffill").to_numpy()


def prep(df, start):
    df = df.loc[df.index < df.index.max()]
    df = MS.add_market_open(df); df["fx_day"] = MS._fx_day(df)
    atr = MS.atr_tf(df)
    side, stop = T.signals(df, atr)
    trades = [t for t in MS.walk(df, side, stop, atr.to_numpy(), cost=T.COST_RT) if t.entry_time >= start]
    idx = {ts: i for i, ts in enumerate(df.index)}
    return df, trades, idx


def apply_kumo(trades, idx, sa, sb):
    """Return list of pnl_r for signals the Kumo (sa,sb) keeps, + the kept-mask over trades."""
    out = []
    for t in trades:
        i = idx.get(t.signal_time)
        if i is None or not (np.isfinite(sa[i]) and np.isfinite(sb[i])):
            continue
        keep = (sa[i] > sb[i]) if t.side > 0 else (sa[i] < sb[i])
        if keep:
            out.append(t.pnl_r)
    return np.array(out)


def st(r):
    n = len(r)
    if n == 0:
        return dict(n=0, totR=0, avgR=0, WR=0, PF=0)
    pn = r[r > 0].sum(); pdn = -r[r < 0].sum()
    return dict(n=n, totR=round(r.sum(), 1), avgR=round(r.mean(), 3),
                WR=round(100 * (r > 0).mean()), PF=round(pn / pdn if pdn > 0 else 99, 2))


def load_xau():
    xa = pd.read_pickle(HERE / "xauusdt_1m_2026h1.pkl"); xj = pd.read_pickle(HERE / "xau_jul2026.pkl")
    x = pd.concat([xa, xj]); return x[~x.index.duplicated()].sort_index()[["open", "high", "low", "close", "volume"]]


if __name__ == "__main__":
    xau = load_xau()
    df26, tr26, idx26 = prep(xau, pd.Timestamp("2026-01-01", tz="UTC"))
    base_full = np.array([t.pnl_r for t in tr26])
    print(f"TALOS (filtresiz) 2026: {st(base_full)}")
    sa0, sb0 = kumo(df26)
    kept0 = apply_kumo(tr26, idx26, sa0, sb0)
    print(f"TALOS-ICHI (9/26/52/26): {st(kept0)}\n")

    # 1) PLATEAU — one dimension at a time around the default
    print("=" * 70); print("1) ICHIMOKU PERİYOT PLATOSU (2026 XAU)"); print("=" * 70)
    dims = {"tenkan": [7, 8, 9, 10, 11], "kijun": [22, 24, 26, 28, 30],
            "senkou_b": [44, 48, 52, 56, 60], "shift": [22, 24, 26, 28, 30]}
    defaults = dict(tenkan=9, kijun=26, senkou_b=52, shift=26)
    for dim, vals in dims.items():
        row = []
        for v in vals:
            p = dict(defaults); p[dim] = v
            sa, sb = kumo(df26, **p)
            s = st(apply_kumo(tr26, idx26, sa, sb))
            row.append(f"{v}:{s['totR']:+.0f}/PF{s['PF']:.2f}/n{s['n']}")
        print(f"  {dim:9s}: " + "   ".join(row))

    # 2) RANDOM-DROP NULL — keep the same count as the real filter, at random, 500x
    print("\n" + "=" * 70); print("2) RANDOM-DROP NULL (Kumo seçimi becerikli mi?)"); print("=" * 70)
    k = len(kept0); N = len(base_full)
    tots = []; avgs = []; pfs = []
    for _ in range(500):
        pick = RNG.choice(N, size=k, replace=False)
        r = base_full[pick]; tots.append(r.sum()); avgs.append(r.mean())
        pn = r[r > 0].sum(); pdn = -r[r < 0].sum(); pfs.append(pn / pdn if pdn > 0 else 99)
    real = st(kept0)
    p_tot = (np.array(tots) >= real["totR"]).mean()
    p_avg = (np.array(avgs) >= real["avgR"]).mean()
    print(f"  gerçek Kumo:  totR={real['totR']:+.1f}  avgR={real['avgR']:+.3f}  PF={real['PF']:.2f}  (n={k}/{N})")
    print(f"  random-drop:  totR={np.mean(tots):+.1f}±{np.std(tots):.1f}  avgR={np.mean(avgs):+.3f}±{np.std(avgs):.3f}  PF={np.mean(pfs):.2f}")
    print(f"  p-değeri:     totR p={p_tot:.3f}   avgR p={p_avg:.3f}   (küçük = Kumo seçimi beceri)")

    # 3+4) MONTHLY + MULTI-YEAR
    print("\n" + "=" * 70); print("3+4) AYLIK İSTİKRAR + ÇOK-YIL OOS (FULL -> FİLTRELİ)"); print("=" * 70)
    def year_block(label, df, start):
        d, tr, idx = prep(df, start)
        full = np.array([t.pnl_r for t in tr])
        sa, sb = kumo(d); kept_mask = []
        rows = []
        for t in tr:
            i = idx.get(t.signal_time)
            ok = None if (i is None or not np.isfinite(sa[i]) or not np.isfinite(sb[i])) else (
                (sa[i] > sb[i]) if t.side > 0 else (sa[i] < sb[i]))
            rows.append((t.exit_time, t.pnl_r, ok))
        kept = np.array([r for _, r, ok in rows if ok])
        print(f"\n{label}:  FULL {st(full)}  ->  FİLTRELİ {st(kept)}")
        mon = {}
        for xt, r, ok in rows:
            if ok:
                mon[str(xt)[:7]] = mon.get(str(xt)[:7], 0) + r
        print("  aylık(filtreli): " + "  ".join(f"{m}:{v:+.0f}" for m, v in sorted(mon.items())))
    year_block("2026 XAU (in-sample)", xau, pd.Timestamp("2026-01-01", tz="UTC"))
    for yr, (s, e) in {"2024": ("2024-01-01", "2025-01-01"), "2025": ("2025-01-01", "2026-01-01")}.items():
        df = P.load_paxg(pd.Timestamp(s, tz="UTC") - pd.Timedelta(days=2), pd.Timestamp(e, tz="UTC"))
        df = df.loc[(df.index >= pd.Timestamp(s, tz="UTC") - pd.Timedelta(days=2)) & (df.index < pd.Timestamp(e, tz="UTC"))]
        year_block(f"{yr} PAXG (OOS)", df, pd.Timestamp(s, tz="UTC"))
