"""Ichimoku (Kumo cloud) on XAU 2026 — is it a usable edge, or a re-skin of MIDAS?

Ichimoku is a trend-follow + pullback system, structurally the same family as MIDAS (VWAP pullback)
and TALOS (Keltner pullback). So the honest test is: same audited engine (1.5*ATR stop, 3.5*ATR
chandelier trail, 8h cap, session flat, $0.50 FX cost), same 2026 XAU 1m data, IS/OOS split, vs
MIDAS's +143R / PF1.67 benchmark.

Ichimoku on 15m bars (9/26/52 — the classic set, on 15m ≈ 2.25h/6.5h/13h look-backs, a sensible
intraday map). Cloud projected +26 (Senkou shifted forward, standard). Three trader-classic entries
tested, each in the cloud-defined trend, filled next 1m open, MIDAS session discipline:
  V1 KUMO-BREAK : price closes from inside/below cloud to ABOVE it (long) — cloud breakout
  V2 TK-CROSS   : Tenkan crosses above Kijun WHILE price is above the cloud (trend-aligned TK)
  V3 KIJUN-PULL : uptrend (price>cloud, Tenkan>Kijun), price pulls back to touch Kijun then closes
                  back up — the direct analogue of MIDAS's VWAP-pullback
Short = mirror. Run: .venv/bin/python scratchpad/fx_gold/ichimoku_xau.py
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
import engine as E                      # noqa: E402
assert "fx_gold" in E.__file__

TOL = 0.25   # Kijun-touch tolerance in ATR (mirror MIDAS)


def load():
    xa = pd.read_pickle(HERE / "xauusdt_1m_2026h1.pkl")
    xj = pd.read_pickle(HERE / "xau_jul2026.pkl")
    df = pd.concat([xa, xj])
    df = df[~df.index.duplicated()].sort_index()[["open", "high", "low", "close", "volume"]]
    df = M.add_market_open(df)
    df["fx_day"] = M._fx_day(df)
    return df


def ichimoku_15m(df):
    """Standard Ichimoku on 15m bars, reindexed to 1m (ffill, no lookahead: each 15m value is
    known only at its bar close; Senkou spans are shifted FORWARD so they use only past data)."""
    g = df.resample("15min", label="right", closed="right").agg(
        {"high": "max", "low": "min", "close": "last"}).dropna()
    hi9 = g["high"].rolling(9).max();  lo9 = g["low"].rolling(9).min()
    hi26 = g["high"].rolling(26).max(); lo26 = g["low"].rolling(26).min()
    hi52 = g["high"].rolling(52).max(); lo52 = g["low"].rolling(52).min()
    tenkan = (hi9 + lo9) / 2
    kijun = (hi26 + lo26) / 2
    span_a = ((tenkan + kijun) / 2).shift(26)      # leading, projected forward (past-derived)
    span_b = ((hi52 + lo52) / 2).shift(26)
    out = pd.DataFrame({"tenkan": tenkan, "kijun": kijun, "span_a": span_a, "span_b": span_b}, index=g.index)
    return out.reindex(df.index, method="ffill")


def signals(df, ich, atr, mode):
    a = atr.to_numpy(); c = df["close"].to_numpy(); o = df["open"].to_numpy()
    lo = df["low"].to_numpy(); hi = df["high"].to_numpy()
    tk = ich["tenkan"].to_numpy(); kj = ich["kijun"].to_numpy()
    sa = ich["span_a"].to_numpy(); sb = ich["span_b"].to_numpy()
    cloud_hi = np.fmax(sa, sb); cloud_lo = np.fmin(sa, sb)
    openmkt = df["open_mkt"].to_numpy(bool); uth = df.index.hour.to_numpy()
    day = pd.Series(df["fx_day"].to_numpy()); bars_in = day.groupby(day).cumcount().to_numpy()
    n = len(df); side = np.zeros(n); stop = np.full(n, np.nan)
    tol = TOL * a
    for i in range(1, n):
        if not openmkt[i] or not np.isfinite(a[i]) or a[i] <= 0 or not np.isfinite(cloud_hi[i]):
            continue
        if M.SKIP_UTC_START <= uth[i] < M.SKIP_UTC_END or bars_in[i] < M.MATURE_MIN:
            continue
        up = c[i] > cloud_hi[i]; dn = c[i] < cloud_lo[i]
        L = Sh = False
        if mode == "kumo":
            L = up and c[i-1] <= cloud_hi[i-1] and c[i] > o[i]
            Sh = dn and c[i-1] >= cloud_lo[i-1] and c[i] < o[i]
        elif mode == "tk":
            L = up and tk[i] > kj[i] and tk[i-1] <= kj[i-1]
            Sh = dn and tk[i] < kj[i] and tk[i-1] >= kj[i-1]
        elif mode == "kijun":
            L = up and tk[i] > kj[i] and lo[i] <= kj[i] + tol[i] and c[i] > kj[i] and c[i] > o[i]
            Sh = dn and tk[i] < kj[i] and hi[i] >= kj[i] - tol[i] and c[i] < kj[i] and c[i] < o[i]
        if L:
            side[i] = 1; stop[i] = c[i] - M.ATR_INIT_MULT * a[i]
        elif Sh:
            side[i] = -1; stop[i] = c[i] + M.ATR_INIT_MULT * a[i]
    return side, stop


def report(df, side, stop, atr, label):
    cfg = E.Cfg(cost_rt=0.50, max_hold_min=480, trail_mult=3.5)
    tr = E.backtest(df, side, stop, np.full(len(df), np.nan), cfg, atr=atr.to_numpy())
    if tr.empty:
        return {"strateji": label, "n": 0}
    tr["r_taker"] = (tr["gross"] - 1e-3 * tr["entry"]) / tr["stop_dist"]
    s = E.split_stats(tr, cfg, oos_start="2026-05-01")
    return {"strateji": label, "n": s["all"]["n"], "totR": s["all"]["totR"], "WR": s["all"]["wr"],
            "PF": s["all"]["pf"], "maxDD": s["all"]["maxddR"], "IS": s["is"]["totR"],
            "OOS": s["oos"]["totR"], "taker": round(float(tr["r_taker"].sum()), 1)}


if __name__ == "__main__":
    df = load(); atr = M.atr_tf(df); ich = ichimoku_15m(df)
    rows = []
    for mode, name in (("kumo", "V1 Kumo-kırılım"), ("tk", "V2 TK-kesişim (bulut üstü)"),
                       ("kijun", "V3 Kijun-çekilme (MIDAS analoğu)")):
        sd, st = signals(df, ich, atr, mode)
        rows.append(report(df, sd, st, atr, name))
    print("Ichimoku @ XAU 2026 — MIDAS motoru (1.5×ATR stop / 3.5×ATR trail / 8h / $0.50 FX)\n")
    print(pd.DataFrame(rows).to_string(index=False))
    print("\nbenchmark MIDAS 2026: +143.1R · 396tr · PF1.67 · IS+85/OOS+58 · taker+22.9")

    # overlap of the best Ichimoku variant with the MIDAS book (diversifier or clone?)
    ds = pd.read_pickle(HERE / "ml" / "dataset.pkl"); mid = ds[ds.source == "xau26"]
    sd, st = signals(df, ich, atr, "kijun")
    cfg = E.Cfg(cost_rt=0.50, max_hold_min=480, trail_mult=3.5)
    tr = E.backtest(df, sd, st, np.full(len(df), np.nan), cfg, atr=atr.to_numpy())
    if not tr.empty:
        dm = mid.set_index("entry_time").r.resample("D").sum()
        di = tr.set_index("entry_time").r.resample("D").sum()
        both = pd.concat([dm, di], axis=1, keys=["midas", "ichi"]).fillna(0)
        print(f"\nV3 Kijun-çekilme ↔ MIDAS günlük-R korelasyon: {both.midas.corr(both.ichi):+.3f} "
              f"(yüksek = klon, düşük = çeşitlendirici)")
