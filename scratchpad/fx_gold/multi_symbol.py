"""Test the MIDAS VWAP-trend strategy on XAU vs XAG / BTC / ETH (2026), with per-instrument cost
(bps-relative, NOT absolute $) and per-asset-class session handling:
  metal  (XAU/XAG): FX-gold hours + London-skip(07-13 UTC) + Fri-16:00ET weekend buffer, VWAP@18:00ET
  crypto (BTC/ETH): 24/7, NO session filter, VWAP@00:00 UTC, exits via trail + 8h cap only
Same core signal (VWAP-pullback + slope), same trailing (1.5xATR init / 3.5xATR trail / 8h cap).
No-lookahead: decide on bar close, fill next open.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "sync" / "midas"))
sys.path.insert(0, str(HERE.parents[1] / "sync"))
import strategy as M          # reuse atr_tf + tuned constants
import trade_sync_common as tsc

SLOPE_N, ATR_INIT, TRAIL, TOUCH, MAXHOLD = M.SLOPE_N, M.ATR_INIT_MULT, M.TRAIL_MULT, M.TOUCH_TOL, M.MAX_HOLD_MIN


def load(sym, start, end):
    cache = HERE / f"_1m_{sym}.pkl"
    if cache.exists():
        df = pd.read_pickle(cache)
    else:
        df = tsc.fetch_klines(sym, "1m", int(start.timestamp()*1000), int(end.timestamp()*1000))
        if df is not None and not df.empty:
            df.to_pickle(cache)
    if df is None or df.empty:
        return pd.DataFrame()
    return df.loc[(df.index >= start) & (df.index < end)]


def market_open(df, asset):
    if asset == "crypto":
        return pd.Series(True, index=df.index).values
    et = df.index.tz_convert("America/New_York"); dow = et.dayofweek; h = et.hour
    op = pd.Series(True, index=df.index)
    op &= ~(dow == 5); op &= ~((dow == 6) & (h < 18))
    op &= ~((dow == 4) & (h >= 16))            # Fri flat 16:00 ET (weekend buffer)
    op &= ~((dow <= 3) & (h == 17))            # daily break
    return op.values


def vwap(df, asset):
    tp = (df["high"]+df["low"]+df["close"])/3.0
    vol = df["volume"].replace(0, np.nan).ffill().fillna(1.0)
    if asset == "crypto":
        day = pd.Series(df.index.normalize().view("int64"), index=df.index)     # 00:00 UTC reset
    else:
        et = df.index.tz_convert("America/New_York")
        day = pd.Series((et - pd.Timedelta(hours=18)).normalize().view("int64"), index=df.index)  # 18:00 ET
    return ((tp*vol).groupby(day).cumsum() / vol.groupby(day).cumsum())


def signals(df, atr, vw, openmkt, skip_london):
    n = len(df); side = np.zeros(n); stop = np.full(n, np.nan)
    v = vw.to_numpy(); slope = (vw - vw.shift(SLOPE_N)).to_numpy()
    c = df["close"].to_numpy(); o = df["open"].to_numpy(); lo = df["low"].to_numpy(); hi = df["high"].to_numpy()
    a = atr.to_numpy(); uth = df.index.hour.to_numpy(); tol = TOUCH*a
    for i in range(SLOPE_N+1, n):
        if not openmkt[i] or not np.isfinite(v[i]) or not np.isfinite(a[i]) or a[i] <= 0:
            continue
        if skip_london and 7 <= uth[i] < 13:
            continue
        if c[i] > v[i] and slope[i] > 0 and lo[i] <= v[i]+tol[i] and c[i] > o[i]:
            side[i] = 1; stop[i] = c[i]-ATR_INIT*a[i]
        elif c[i] < v[i] and slope[i] < 0 and hi[i] >= v[i]-tol[i] and c[i] < o[i]:
            side[i] = -1; stop[i] = c[i]+ATR_INIT*a[i]
    return side, stop


def walk(df, side, stop, atr, openmkt, cost_bps):
    o = df["open"].to_numpy(); h = df["high"].to_numpy(); l = df["low"].to_numpy(); c = df["close"].to_numpy()
    a = np.asarray(atr); ts = df.index; n = len(df); out = []
    i = 0
    while i < n-1:
        s = side[i]
        if s == 0 or not openmkt[i] or not openmkt[i+1] or not np.isfinite(stop[i]):
            i += 1; continue
        k = i+1; entry = o[k]; st = stop[i]; sd = abs(entry-st)
        if sd <= 0: i += 1; continue
        cost = cost_bps/1e4*entry                      # PROPORTIONAL round-trip cost
        best = entry; xpx = np.nan; xi = None; j = k
        while j < n:
            if not openmkt[j]: xpx = c[j-1]; xi = j-1; break
            hit = (l[j] <= st) if s > 0 else (h[j] >= st)
            if hit: xpx = (min(st,o[j]) if s>0 else max(st,o[j])); xi = j; break
            if MAXHOLD and (j-k) >= MAXHOLD: xpx = c[j]; xi = j; break
            if (j+1>=n) or (not openmkt[j+1]): xpx = c[j]; xi = j; break
            if np.isfinite(a[j]):
                if s>0: best = max(best,h[j]); st = max(st,best-TRAIL*a[j])
                else: best = min(best,l[j]); st = min(st,best+TRAIL*a[j])
            j += 1
        r = ((xpx-entry)*s - cost)/sd
        out.append((ts[k], int(s), float(r)))
        i = xi+1
    return out


def run(sym, asset, cost_bps, start, end, skip_london=None):
    if skip_london is None: skip_london = (asset == "metal")
    df = load(sym, start - pd.Timedelta(days=2), end)
    if df.empty: return None
    om = market_open(df, asset)
    atr = M.atr_tf(df)
    vw = vwap(df, asset)
    side, stop = signals(df, atr, vw, om, skip_london)
    trades = [t for t in walk(df, side, stop, atr.to_numpy(), om, cost_bps) if t[0] >= start]
    return trades


def stats(trades, oos="2026-05-01"):
    if not trades: return None
    oo = pd.Timestamp(oos, tz="UTC")
    def S(ts):
        if len(ts) < 5: return dict(n=len(ts), R=0, wr=0, pf=0)
        r = np.array([t[2] for t in ts]); w = r[r>0].sum(); l = -r[r<0].sum()
        return dict(n=len(ts), R=round(r.sum(),1), wr=round((r>0).mean(),2), pf=round(w/l if l>0 else 9.9,2))
    a = S(trades); i = S([t for t in trades if t[0] < oo]); o = S([t for t in trades if t[0] >= oo])
    return a, i, o


if __name__ == "__main__":
    S = pd.Timestamp("2026-01-01", tz="UTC"); E = pd.Timestamp("2026-07-01", tz="UTC")
    GRID = [
        ("XAUUSDT", "metal", [1.24]),
        ("XAGUSDT", "metal", [1.5, 4.0]),
        ("BTCUSDT", "crypto", [1.5, 5.0, 10.0]),
        ("ETHUSDT", "crypto", [1.5, 5.0, 10.0]),
    ]
    print(f"{'sym':>8} {'asset':>6} {'cost':>5} {'n':>5} {'totR':>7} {'WR':>4} {'PF':>5} | {'IS_R':>6} {'OOS_R':>6}")
    for sym, asset, costs in GRID:
        tr = run(sym, asset, costs[0], S, E)
        if tr is None: print(f"{sym:>8} veri yok"); continue
        for cb in costs:
            trades = [t for t in tr] if cb == costs[0] else run(sym, asset, cb, S, E)
            a, i, o = stats(trades)
            print(f"{sym:>8} {asset:>6} {cb:>4}b {a['n']:>5} {a['R']:>+7.1f} {a['wr']:>4.0%} {a['pf']:>5.2f} | {i['R']:>+6.1f} {o['R']:>+6.1f}")
