"""CONFLUENCE — trader-style complex HYBRID system for XAU (rule-based, no ML).

The architecture real discretionary traders run as a checklist, mechanized:

  C1  HTF trend alignment : 1h EMA50 slope up AND close above 4h EMA20 (mirror for short)
  C2  Intraday trend      : close above anchored VWAP AND 60m VWAP slope up (MIDAS trend def)
  C3  Location (zone)     : bar low touches within 0.25*ATR of a demand zone — anchored VWAP,
                            15m Keltner lower band (0.75*ATR20), or the prior fx-day high/low
                            (S/R flip) — any one qualifies
  C4  Trigger candle      : up-close AND close in the upper half of the bar's range (rejection)
  C5  Participation       : volume z-score > 0
  SESSION (always on)     : shipped MIDAS discipline — skip 07-13 UTC London window, no entries
                            in the fx-day's first 120 min, market-hours + holiday mask

Entry = SESSION and at least K of {C1..C5} (K swept 2..5), direction from C2's VWAP side.
Exit  = the audited MIDAS engine: 1.5*ATR initial stop, 3.5*ATR chandelier trail, 8h cap,
        session flatten (repo dogma: exits are untouchable for gold). A fixed-2R "trader target"
        variant is reported for comparison.

Second classic: BREAKOUT-RETEST — prior fx-day high/low breaks, price retests the level within
2h and holds (close back on the break side) -> enter with the same trail exit.

2026 (Jan..Jul-7), IS Jan-Apr / OOS May-Jul, $0.50 FX + 10bps-taker views, MIDAS as benchmark.
Run: .venv/bin/python scratchpad/fx_gold/hybrid_xau.py
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
sys.path.insert(0, str(HERE))           # after strategy import (it prepends backtest/)
import engine as E                      # noqa: E402
assert "fx_gold" in E.__file__

TOL = 0.25          # zone-touch tolerance, *ATR
KMULT = 0.75        # Keltner band width (TALOS-validated)
RETEST_MIN = 120    # breakout-retest window (minutes)


def load_1m() -> pd.DataFrame:
    xa = pd.read_pickle(HERE / "xauusdt_1m_2026h1.pkl")
    xj = pd.read_pickle(HERE / "xau_jul2026.pkl")
    df = pd.concat([xa, xj])
    df = df[~df.index.duplicated()].sort_index()[["open", "high", "low", "close", "volume"]]
    df = M.add_market_open(df)
    df["fx_day"] = M._fx_day(df)
    return df


def resample_last(df, tf, series):
    return series.resample(tf, label="right", closed="right").last().reindex(df.index, method="ffill")


def conditions(df: pd.DataFrame):
    """Per-bar long-side condition masks C1..C5 (+ session gate). Shorts = computed mirror."""
    c = df["close"]; o = df["open"]; h = df["high"]; lo = df["low"]
    atr = M.atr_tf(df)
    a = atr.to_numpy()
    vwap = M.anchored_vwap(df)

    # C1 HTF: 1h EMA50 slope + 4h EMA20 side (resampled, ffilled -> last COMPLETED bar, no lookahead)
    c1h = df["close"].resample("1h", label="right", closed="right").last()
    ema50_1h = c1h.ewm(span=50, adjust=False).mean()
    sl_1h = (ema50_1h - ema50_1h.shift(3)).reindex(df.index, method="ffill")
    c4h = df["close"].resample("4h", label="right", closed="right").last()
    ema20_4h = c4h.ewm(span=20, adjust=False).mean().reindex(df.index, method="ffill")
    C1L = (sl_1h > 0) & (c > ema20_4h)
    C1S = (sl_1h < 0) & (c < ema20_4h)

    # C2 intraday trend (MIDAS def)
    slope = vwap - vwap.shift(M.SLOPE_N)
    C2L = (c > vwap) & (slope > 0)
    C2S = (c < vwap) & (slope < 0)

    # C3 location: touch of VWAP / Keltner band / prior-day H-L within TOL*ATR
    g15 = df["close"].resample("15min", label="right", closed="right").last()
    ema20_15 = g15.ewm(span=20, adjust=False).mean().reindex(df.index, method="ffill")
    g15o = df.resample("15min", label="right", closed="right").agg(
        {"high": "max", "low": "min", "close": "last"}).dropna()
    pc15 = g15o["close"].shift(1)
    tr15 = pd.concat([(g15o["high"] - g15o["low"]), (g15o["high"] - pc15).abs(),
                      (g15o["low"] - pc15).abs()], axis=1).max(axis=1)
    katr = tr15.ewm(alpha=1 / 20, adjust=False).mean().reindex(df.index, method="ffill")
    kelt_lo = ema20_15 - KMULT * katr
    kelt_hi = ema20_15 + KMULT * katr
    day = df["fx_day"]
    pd_hi = df["high"].groupby(day).max().shift(1).reindex(day.values).to_numpy()
    pd_lo = df["low"].groupby(day).min().shift(1).reindex(day.values).to_numpy()
    tol = TOL * a
    near = lambda level: (lo.to_numpy() <= level + tol) & (c.to_numpy() > level - tol)
    C3L = near(vwap.to_numpy()) | near(kelt_lo.to_numpy()) | near(pd_hi) | near(pd_lo)
    nearS = lambda level: (h.to_numpy() >= level - tol) & (c.to_numpy() < level + tol)
    C3S = nearS(vwap.to_numpy()) | nearS(kelt_hi.to_numpy()) | nearS(pd_hi) | nearS(pd_lo)

    # C4 trigger candle
    rng = (h - lo).replace(0, np.nan)
    C4L = (c > o) & ((c - lo) / rng > 0.5)
    C4S = (c < o) & ((h - c) / rng > 0.5)

    # C5 participation
    v = df["volume"].replace(0, np.nan)
    volz = (v - v.rolling(300, min_periods=60).mean()) / v.rolling(300, min_periods=60).std()
    C5 = volz > 0

    # session gate (shipped discipline)
    uth = df.index.hour
    mature = day.groupby(day).cumcount() >= M.MATURE_MIN
    sess = df["open_mkt"].to_numpy(bool) & ~((uth >= M.SKIP_UTC_START) & (uth < M.SKIP_UTC_END)) \
        & mature.to_numpy() & np.isfinite(a) & (a > 0)

    L = [np.asarray(x, bool) for x in (C1L, C2L, C3L, C4L, C5)]
    Sh = [np.asarray(x, bool) for x in (C1S, C2S, C3S, C4S, C5)]
    return L, Sh, sess, atr


def confluence_signal(df, L, Sh, sess, atr, k: int):
    scoreL = np.sum(L, axis=0); scoreS = np.sum(Sh, axis=0)
    a = atr.to_numpy(); c = df["close"].to_numpy()
    side = np.zeros(len(df))
    side[sess & L[1] & (scoreL >= k)] = 1              # direction requires the C2 VWAP side itself
    side[sess & Sh[1] & (scoreS >= k) & (side == 0)] = -1
    stop = np.where(side != 0, c - side * 1.5 * a, np.nan)
    return side, stop


def breakout_retest(df, sess, atr):
    """Prior fx-day H/L break -> retest within RETEST_MIN holding the level -> enter w/ trail."""
    c = df["close"].to_numpy(); h = df["high"].to_numpy(); lo = df["low"].to_numpy()
    a = atr.to_numpy(); day = df["fx_day"]
    pd_hi = df["high"].groupby(day).max().shift(1).reindex(day.values).to_numpy()
    pd_lo = df["low"].groupby(day).min().shift(1).reindex(day.values).to_numpy()
    n = len(df); side = np.zeros(n); stop = np.full(n, np.nan)
    brkL = -1; brkS = -1   # bar index of the most recent unresolved break
    for i in range(1, n):
        if not sess[i]:
            continue
        if np.isfinite(pd_hi[i]) and c[i - 1] <= pd_hi[i - 1] and c[i] > pd_hi[i]:
            brkL = i
        if np.isfinite(pd_lo[i]) and c[i - 1] >= pd_lo[i - 1] and c[i] < pd_lo[i]:
            brkS = i
        tol = TOL * a[i]
        if brkL >= 0 and i - brkL <= RETEST_MIN and i > brkL:
            if lo[i] <= pd_hi[i] + tol and c[i] > pd_hi[i]:      # retest held
                side[i] = 1; stop[i] = c[i] - 1.5 * a[i]; brkL = -1
            elif c[i] < pd_hi[i] - tol:
                brkL = -1                                        # failed break
        if side[i] == 0 and brkS >= 0 and i - brkS <= RETEST_MIN and i > brkS:
            if h[i] >= pd_lo[i] - tol and c[i] < pd_lo[i]:
                side[i] = -1; stop[i] = c[i] + 1.5 * a[i]; brkS = -1
            elif c[i] > pd_lo[i] + tol:
                brkS = -1
    return side, stop


def report(df, side, stop, atr, label, target=None, trail=3.5):
    tgt = np.full(len(df), np.nan) if target is None else target
    cfg = E.Cfg(cost_rt=0.50, max_hold_min=480, trail_mult=trail)
    tr = E.backtest(df, side, stop, tgt, cfg, atr=atr.to_numpy())
    if tr.empty:
        print(f"{label}: no trades"); return None
    tr["r_taker"] = (tr["gross"] - 1e-3 * tr["entry"]) / tr["stop_dist"]
    s = E.split_stats(tr, cfg, oos_start="2026-05-01")
    row = {"label": label, "n": s["all"]["n"], "totR": s["all"]["totR"], "wr": s["all"]["wr"],
           "pf": s["all"]["pf"], "maxDD": s["all"]["maxddR"],
           "IS": s["is"]["totR"], "OOS": s["oos"]["totR"],
           "long": s["long"]["totR"], "short": s["short"]["totR"],
           "takerR": round(float(tr["r_taker"].sum()), 1)}
    return row, s["monthly"]


if __name__ == "__main__":
    df = load_1m()
    L, Sh, sess, atr = conditions(df)
    for i, nm in enumerate(("C1 HTF", "C2 VWAP", "C3 zone", "C4 trigger", "C5 vol")):
        print(f"  {nm}: L {L[i].mean():.3f}  S {Sh[i].mean():.3f} of bars")

    rows, monthlies = [], {}
    for k in (2, 3, 4, 5):
        side, stop = confluence_signal(df, L, Sh, sess, atr, k)
        r = report(df, side, stop, atr, f"CONF k>={k} (trail)")
        if r:
            rows.append(r[0]); monthlies[f"k{k}"] = r[1]
        # trader fixed-2R target variant
        c = df["close"].to_numpy(); a = atr.to_numpy()
        tgt = np.where(side != 0, c + np.sign(side) * 3.0 * a, np.nan)   # 2R = 3.0*ATR (stop 1.5)
        r2 = report(df, side, stop, atr, f"CONF k>={k} (2R tgt)", target=tgt, trail=0.0)
        if r2:
            rows.append(r2[0])
    side, stop = breakout_retest(df, sess, atr)
    r = report(df, side, stop, atr, "BREAK-RETEST (trail)")
    if r:
        rows.append(r[0]); monthlies["brk"] = r[1]

    print("\n================ 2026 Jan..Jul — engine-audited, $0.50 FX (IS Jan-Apr / OOS May-Jul)")
    print(pd.DataFrame(rows).to_string(index=False))
    print("\nbenchmark: MIDAS 2026 aynı dönem +143.1R / 396tr / PF1.67 (taker +22.9)")
    print("\nmonthly (trail variants):")
    for k, mon in monthlies.items():
        print(f"  {k}: " + "  ".join(f"{m}:{v:+.0f}" for m, v in sorted(mon.items())))
