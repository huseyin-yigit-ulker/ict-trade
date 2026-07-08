"""MIDAS timing + Ichimoku DIRECTION filter — keep only MIDAS trades that agree with the cloud.

User idea: Ichimoku sets the long/short bias (HTF trend), MIDAS decides WHEN. So a MIDAS long is
taken only when Ichimoku is bullish; a MIDAS short only when bearish. This is a directional-
confluence overlay, NOT MIDAS's own trend gate (MIDAS already needs price/VWAP-slope agreement).

Bias definitions tested at each MIDAS signal bar (15m Ichimoku, no-lookahead):
  CLOUD : long ok if close > cloud-top ; short ok if close < cloud-bottom
  TK    : long ok if Tenkan > Kijun    ; short ok if Tenkan < Kijun
  BOTH  : CLOUD and TK agree
  FUTURE: cloud is bullish if Senkou A > Senkou B at the projected (current) point (Kumo colour)

Reported vs the FULL MIDAS book: n, totR, avgR, WR, LOSS% (r<0), PF, IS/OOS, taker. The question
is whether filtering RAISES avgR / lowers loss-rate (quality), not just cuts trades.
Run: .venv/bin/python scratchpad/fx_gold/midas_ichimoku_filter.py
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
sys.path.insert(0, str(HERE))
from ichimoku_xau import load, ichimoku_15m    # noqa: E402


def midas_trades(df, atr):
    side, stop = M.signals(df, atr)
    return M.walk(df, side, stop, atr.to_numpy(), cost=M.COST_RT)


def bias_at(ich, df):
    """Per-bar Ichimoku bias flags aligned to df index."""
    sa = ich["span_a"].to_numpy(); sb = ich["span_b"].to_numpy()
    tk = ich["tenkan"].to_numpy(); kj = ich["kijun"].to_numpy()
    c = df["close"].to_numpy()
    cloud_hi = np.fmax(sa, sb); cloud_lo = np.fmin(sa, sb)
    return {
        "cloud_long": c > cloud_hi, "cloud_short": c < cloud_lo,
        "tk_long": tk > kj, "tk_short": tk < kj,
        "future_long": sa > sb, "future_short": sa < sb,
    }


def stats(trs, label):
    r = np.array([t.pnl_r for t in trs]); n = len(r)
    if n == 0:
        return {"filtre": label, "n": 0}
    is_ = np.array([t.entry_time < pd.Timestamp("2026-05-01", tz="UTC") for t in trs])
    rt = np.array([((t.exit_px - t.entry) * t.side - 1e-3 * t.entry) / abs(t.entry - t.stop) for t in trs])
    pn = r[r > 0].sum(); pdn = -r[r < 0].sum()
    return {"filtre": label, "n": n, "totR": round(r.sum(), 1), "avgR": round(r.mean(), 3),
            "WR": round((r > 0).mean(), 3), "LOSS%": round(100 * (r < 0).mean()),
            "PF": round(pn / pdn, 2) if pdn > 0 else 99,
            "IS": round(r[is_].sum(), 1), "OOS": round(r[~is_].sum(), 1),
            "taker": round(rt.sum(), 1)}


if __name__ == "__main__":
    df = load(); atr = M.atr_tf(df); ich = ichimoku_15m(df)
    trades = midas_trades(df, atr)
    idx = {ts: i for i, ts in enumerate(df.index)}
    B = bias_at(ich, df)

    def keep(t, long_key, short_key):
        i = idx.get(t.signal_time)
        if i is None:
            return False
        return B[long_key][i] if t.side > 0 else B[short_key][i]

    rows = [stats(trades, "MIDAS FULL (filtresiz)")]
    rows.append(stats([t for t in trades if keep(t, "cloud_long", "cloud_short")], "+ CLOUD (fiyat vs bulut)"))
    rows.append(stats([t for t in trades if keep(t, "tk_long", "tk_short")], "+ TK (Tenkan vs Kijun)"))
    rows.append(stats([t for t in trades if keep(t, "cloud_long", "cloud_short") and keep(t, "tk_long", "tk_short")], "+ BOTH (bulut & TK)"))
    rows.append(stats([t for t in trades if keep(t, "future_long", "future_short")], "+ FUTURE (Kumo rengi A>B)"))
    # inverse: trades the CLOUD filter REMOVES — are they actually the losers?
    removed = [t for t in trades if not keep(t, "cloud_long", "cloud_short")]
    rows.append(stats(removed, "  (CLOUD'un ELEDİĞİ işlemler)"))

    print("MIDAS + Ichimoku yön-filtresi · XAU 2026 · aynı motor/maliyet\n")
    print(pd.DataFrame(rows).to_string(index=False))
    print("\nSoru: filtre avgR'ı yükseltip LOSS%'i düşürüyor mu (kalite), yoksa sadece işlem mi kırpıyor?")
    print("İpucu: 'ELEDİĞİ işlemler' pozitifse filtre iyi işlemleri atıyor demektir.")
