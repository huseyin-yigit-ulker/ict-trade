"""MIDAS + VWAP bands — apply TALOS's deep-band-pullback idea to MIDAS's VWAP line.

MIDAS today enters on a SHALLOW touch of the VWAP line itself (low <= VWAP + 0.25*ATR). TALOS enters
on a DEEP pullback to a band BELOW its midline (EMA - 0.75*ATR). Question (user): give MIDAS the same
band structure — a line ABOVE and BELOW the VWAP (VWAP ± k*ATR) — and enter on a deep pullback to the
lower band (long) / upper band (short). Does a deeper VWAP discount beat the shallow touch?

Two entry variants, k (band width in ATR15) swept, everything else = shipped MIDAS (VWAP slope trend,
1.5*ATR stop, 3.5*ATR trailing, 8h, session discipline, $0.50 FX), engine = MIDAS walk (exact parity):
  BAND-RECLAIM : trend = VWAP slope up; low dips to (VWAP - k*ATR) lower band (within 0.25*ATR),
                 close RECLAIMS back above that band (c > band_lo), bullish bar. (TALOS-style, VWAP-anchored)
  BAND+VWAP    : same but ALSO require close still above VWAP (c > VWAP) — trend stricter.
k=0.25 BAND-RECLAIM ≈ the shipped MIDAS touch (sanity anchor). 2026 XAU, IS Jan-Apr / OOS May-Jul.
Run: .venv/bin/python scratchpad/fx_gold/midas_bands.py
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "sync" / "midas"))
import strategy as M                    # noqa: E402


def load():
    xa = pd.read_pickle(HERE / "xauusdt_1m_2026h1.pkl"); xj = pd.read_pickle(HERE / "xau_jul2026.pkl")
    df = pd.concat([xa, xj]); df = df[~df.index.duplicated()].sort_index()[["open", "high", "low", "close", "volume"]]
    return M.add_market_open(df)


def band_signals(df, atr, k, require_vwap):
    """MIDAS trend + deep pullback to the VWAP ± k*ATR band (reclaim). require_vwap adds c>VWAP."""
    vwap = M.anchored_vwap(df)
    n = len(df); side = np.zeros(n); stop = np.full(n, np.nan)
    vw = vwap.to_numpy(); slope = (vwap - vwap.shift(M.SLOPE_N)).to_numpy()
    c = df["close"].to_numpy(); o = df["open"].to_numpy()
    lo = df["low"].to_numpy(); hi = df["high"].to_numpy()
    a = atr.to_numpy(); openmkt = df["open_mkt"].to_numpy(bool)
    uth = df.index.hour.to_numpy()
    day = pd.Series(M._fx_day(df)); bars_in = day.groupby(day).cumcount().to_numpy()
    tol = M.TOUCH_TOL * a
    for i in range(M.SLOPE_N + 1, n):
        if not openmkt[i] or not np.isfinite(vw[i]) or not np.isfinite(a[i]) or a[i] <= 0:
            continue
        if M.SKIP_UTC_START <= uth[i] < M.SKIP_UTC_END or bars_in[i] < M.MATURE_MIN:
            continue
        band_lo = vw[i] - k * a[i]; band_hi = vw[i] + k * a[i]
        long_ok = (slope[i] > 0 and c[i] > band_lo and lo[i] <= band_lo + tol[i] and c[i] > o[i]
                   and (c[i] > vw[i] if require_vwap else True))
        short_ok = (slope[i] < 0 and c[i] < band_hi and hi[i] >= band_hi - tol[i] and c[i] < o[i]
                    and (c[i] < vw[i] if require_vwap else True))
        if long_ok:
            side[i] = 1; stop[i] = c[i] - M.ATR_INIT_MULT * a[i]
        elif short_ok:
            side[i] = -1; stop[i] = c[i] + M.ATR_INIT_MULT * a[i]
    return side, stop


def stats(trades, label):
    r = np.array([t.pnl_r for t in trades]); n = len(r)
    if n == 0:
        return dict(strateji=label, n=0)
    is_ = np.array([t.entry_time < pd.Timestamp("2026-05-01", tz="UTC") for t in trades])
    rt = np.array([((t.exit_px - t.entry) * t.side - 1e-3 * t.entry) / abs(t.entry - t.stop) for t in trades])
    eq = r.cumsum(); dd = float((eq - np.maximum.accumulate(eq)).min())
    pn = r[r > 0].sum(); pdn = -r[r < 0].sum()
    return dict(strateji=label, n=n, totR=round(r.sum(), 1), avgR=round(r.mean(), 3),
                WR=round(100 * (r > 0).mean()), PF=round(pn / pdn if pdn > 0 else 99, 2),
                maxDD=round(dd, 1), IS=round(r[is_].sum(), 1), OOS=round(r[~is_].sum(), 1),
                taker=round(rt.sum(), 1))


if __name__ == "__main__":
    df = load(); atr = M.atr_tf(df)
    start = pd.Timestamp("2026-01-01", tz="UTC")

    # base MIDAS (shipped) for reference
    bs, bst = M.signals(df, atr)
    base = [t for t in M.walk(df, bs, bst, atr.to_numpy(), cost=M.COST_RT) if t.entry_time >= start]
    rows = [stats(base, "MIDAS shipped (VWAP touch)")]

    for require_vwap, tag in ((False, "BAND-RECLAIM"), (True, "BAND+VWAP")):
        for k in (0.25, 0.5, 0.75, 1.0, 1.5):
            s, st = band_signals(df, atr, k, require_vwap)
            tr = [t for t in M.walk(df, s, st, atr.to_numpy(), cost=M.COST_RT) if t.entry_time >= start]
            rows.append(stats(tr, f"{tag} k={k:g}"))

    print("MIDAS + VWAP-bant · XAU 2026 · MIDAS motoru ($0.50 FX) · IS(Oca-Nis)/OOS(May-Tem)\n")
    print(pd.DataFrame(rows).to_string(index=False))
    print("\nreferans base MIDAS ≈ +143R / PF1.67 / IS+85 / OOS+58.  k=0.25 BAND-RECLAIM ≈ shipped touch (sanity).")
