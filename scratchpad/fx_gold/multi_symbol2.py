"""Test MIDAS VWAP-trend on Binance index/commodity/metal products (2026), per-instrument cost (bps)
and asset-class session model:
  metal (XAU/XAG/COPPER/XPT/XPD): FX-metal hours + London-skip(07-13 UTC) + Fri-16ET buffer, VWAP@18ET
  index (SPY/QQQ):                US RTH 09:30-16:00 ET only, VWAP anchored @09:30 ET (RTH-only)
IS/OOS = first half / second half of each symbol's available 2026 data (windows differ: SPY/QQQ ~3mo).
SPXUSDT is the SPX6900 MEMECOIN (not the index) -> excluded.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "sync" / "midas"))
sys.path.insert(0, str(HERE.parents[1] / "sync"))
import strategy as M
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
    et = df.index.tz_convert("America/New_York"); dow = et.dayofweek; h = et.hour; mn = et.minute
    if asset == "index":
        minute = (h * 60 + mn)
        return np.asarray((dow <= 4) & (minute >= 570) & (minute < 960))  # 09:30-16:00 ET Mon-Fri
    op = pd.Series(True, index=df.index)
    op &= ~(dow == 5); op &= ~((dow == 6) & (h < 18))
    op &= ~((dow == 4) & (h >= 16)); op &= ~((dow <= 3) & (h == 17))
    return op.values


def vwap(df, asset, om):
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    vol = df["volume"].replace(0, np.nan).ffill().fillna(1.0)
    et = df.index.tz_convert("America/New_York")
    if asset == "index":
        day = pd.Series(et.normalize().view("int64"), index=df.index)          # reset each ET date
        rth = pd.Series(om, index=df.index)
        pv = (tp * vol).where(rth, 0).groupby(day).cumsum()
        cv = (vol).where(rth, 0).groupby(day).cumsum()
    else:
        day = pd.Series((et - pd.Timedelta(hours=18)).normalize().view("int64"), index=df.index)
        pv = (tp * vol).groupby(day).cumsum(); cv = vol.groupby(day).cumsum()
    return pv / cv.replace(0, np.nan)


def signals(df, atr, vw, openmkt, skip_london):
    n = len(df); side = np.zeros(n); stop = np.full(n, np.nan)
    v = vw.to_numpy(); slope = (vw - vw.shift(SLOPE_N)).to_numpy()
    c = df["close"].to_numpy(); o = df["open"].to_numpy(); lo = df["low"].to_numpy(); hi = df["high"].to_numpy()
    a = atr.to_numpy(); uth = df.index.hour.to_numpy(); tol = TOUCH * a
    for i in range(SLOPE_N + 1, n):
        if not openmkt[i] or not np.isfinite(v[i]) or not np.isfinite(a[i]) or a[i] <= 0:
            continue
        if skip_london and 7 <= uth[i] < 13:
            continue
        if c[i] > v[i] and slope[i] > 0 and lo[i] <= v[i] + tol[i] and c[i] > o[i]:
            side[i] = 1; stop[i] = c[i] - ATR_INIT * a[i]
        elif c[i] < v[i] and slope[i] < 0 and hi[i] >= v[i] - tol[i] and c[i] < o[i]:
            side[i] = -1; stop[i] = c[i] + ATR_INIT * a[i]
    return side, stop


def walk(df, side, stop, atr, openmkt, cost_bps):
    o = df["open"].to_numpy(); h = df["high"].to_numpy(); l = df["low"].to_numpy(); c = df["close"].to_numpy()
    a = np.asarray(atr); ts = df.index; n = len(df); out = []
    i = 0
    while i < n - 1:
        s = side[i]
        if s == 0 or not openmkt[i] or not openmkt[i + 1] or not np.isfinite(stop[i]):
            i += 1; continue
        k = i + 1; entry = o[k]; st = stop[i]; sd = abs(entry - st)
        if sd <= 0: i += 1; continue
        cost = cost_bps / 1e4 * entry
        best = entry; xpx = np.nan; xi = None; j = k
        while j < n:
            if not openmkt[j]: xpx = c[j - 1]; xi = j - 1; break
            hit = (l[j] <= st) if s > 0 else (h[j] >= st)
            if hit: xpx = (min(st, o[j]) if s > 0 else max(st, o[j])); xi = j; break
            if MAXHOLD and (j - k) >= MAXHOLD: xpx = c[j]; xi = j; break
            if (j + 1 >= n) or (not openmkt[j + 1]): xpx = c[j]; xi = j; break
            if np.isfinite(a[j]):
                if s > 0: best = max(best, h[j]); st = max(st, best - TRAIL * a[j])
                else: best = min(best, l[j]); st = min(st, best + TRAIL * a[j])
            j += 1
        out.append((ts[k], int(s), float(((xpx - entry) * s - cost) / sd)))
        i = xi + 1
    return out


def run(sym, asset, cost_bps, start, end, skip_london=None):
    if skip_london is None: skip_london = (asset == "metal")
    df = load(sym, start - pd.Timedelta(days=2), end)
    if df.empty: return None
    om = market_open(df, asset)
    atr = M.atr_tf(df)
    vw = vwap(df, asset, om)
    side, stop = signals(df, atr, vw, om, skip_london)
    return [t for t in walk(df, side, stop, atr.to_numpy(), om, cost_bps) if t[0] >= start]


def stat(ts):
    if len(ts) < 5: return dict(n=len(ts), R=0.0, wr=0.0, pf=0.0)
    r = np.array([t[2] for t in ts]); w = r[r > 0].sum(); l = -r[r < 0].sum()
    return dict(n=len(ts), R=round(r.sum(), 1), wr=round((r > 0).mean(), 2), pf=round(w / l if l > 0 else 9.9, 2))


def split(trades):
    if not trades: return None
    times = sorted(t[0] for t in trades); mid = times[len(times) // 2]
    a = stat(trades); i = stat([t for t in trades if t[0] < mid]); o = stat([t for t in trades if t[0] >= mid])
    return a, i, o, mid


if __name__ == "__main__":
    S = pd.Timestamp("2026-01-01", tz="UTC"); E = pd.Timestamp("2026-07-01", tz="UTC")
    GRID = [
        ("XAUUSDT", "metal", [1.24]),                 # baseline
        ("XPTUSDT", "metal", [1.5, 4.0]),             # platinum
        ("XPDUSDT", "metal", [1.5, 4.0]),             # palladium
        ("COPPERUSDT", "metal", [1.5, 5.0]),          # copper
        ("SPYUSDT", "index", [1.5, 5.0, 10.0]),       # S&P 500 ETF (RTH) — short window (Apr-Jun)
        ("QQQUSDT", "index", [1.5, 5.0, 10.0]),       # Nasdaq ETF (RTH) — short window
    ]
    print(f"{'sym':>10} {'asset':>6} {'cost':>5} {'n':>5} {'totR':>7} {'WR':>4} {'PF':>5} | {'1.yarı':>7} {'2.yarı':>7}  (split)")
    for sym, asset, costs in GRID:
        base = run(sym, asset, costs[0], S, E)
        if base is None:
            print(f"{sym:>10} veri yok"); continue
        for cb in costs:
            tr = base if cb == costs[0] else run(sym, asset, cb, S, E)
            sp = split(tr)
            if sp is None:
                print(f"{sym:>10} {asset:>6} {cb:>4}b  az islem"); continue
            a, i, o, mid = sp
            print(f"{sym:>10} {asset:>6} {cb:>4}b {a['n']:>5} {a['R']:>+7.1f} {a['wr']:>4.0%} {a['pf']:>5.2f} | "
                  f"{i['R']:>+7.1f} {o['R']:>+7.1f}  (>={str(mid)[5:10]})")
