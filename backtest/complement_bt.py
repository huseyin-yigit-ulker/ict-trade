"""Quick standalone backtest of TREND-FOLLOWING candidates as a complement to the
RANGE/mean-reversion 'main' ICT stream. Trend strategies should earn their R in the
HIGH efficiency-ratio (strong/mid trend) regime where main is weak.

Run:  python backtest/complement_bt.py
No DB, no project deps beyond ict.data.fetch_klines.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from ict.data import fetch_klines  # noqa: E402

FEE = 0.0005          # per side -> 0.1% round trip
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XAUUSDT", "XAGUSDT"]
START = "2025-06-16"
END   = "2026-06-16"
INTERVAL = "1h"


# ---------- indicators ----------
def atr(df, n=14):
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def adx(df, n=14):
    h, l, c = df["high"], df["low"], df["close"]
    up = h.diff()
    dn = -l.diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr_ = tr.ewm(alpha=1 / n, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / atr_
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / atr_
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean()


def eff_ratio(close, n=24):
    """Kaufman efficiency ratio over n bars: |net move| / sum|moves|. ~0=chop, ~1=clean trend."""
    change = close.diff(n).abs()
    vol = close.diff().abs().rolling(n).sum()
    return change / vol.replace(0, np.nan)


def net_r(entry, exit_px, risk, direction):
    if risk <= 0:
        return 0.0
    gross = (exit_px - entry) if direction == "long" else (entry - exit_px)
    fees = FEE * (entry + exit_px)
    return (gross - fees) / risk


# ---------- strategies (each returns list of trade dicts) ----------
def run_trades(df, signals_iter, atr_mult=2.0):
    """Generic event loop. signals_iter yields (i, direction) entry signals at bar close i.
    Exit: ATR stop OR opposite Donchian-style trailing handled by caller via 'exit_fn'."""
    raise NotImplementedError  # not used; each strategy below is self-contained


def donchian(df, n_entry=20, n_exit=10, atr_mult=2.0):
    a = atr(df)
    er = eff_ratio(df["close"])
    hi = df["high"].rolling(n_entry).max().shift(1)
    lo = df["low"].rolling(n_entry).min().shift(1)
    exit_hi = df["high"].rolling(n_exit).max().shift(1)
    exit_lo = df["low"].rolling(n_exit).min().shift(1)
    c = df["close"].values
    H, L = df["high"].values, df["low"].values
    trades, pos = [], None
    for i in range(n_entry + 1, len(df)):
        if pos is None:
            if c[i] > hi.iloc[i]:
                pos = dict(dir="long", entry=c[i], stop=c[i] - atr_mult * a.iloc[i],
                           risk=atr_mult * a.iloc[i], er=er.iloc[i])
            elif c[i] < lo.iloc[i]:
                pos = dict(dir="short", entry=c[i], stop=c[i] + atr_mult * a.iloc[i],
                           risk=atr_mult * a.iloc[i], er=er.iloc[i])
        else:
            exit_px = None
            if pos["dir"] == "long":
                if L[i] <= pos["stop"]:
                    exit_px = pos["stop"]
                elif c[i] < exit_lo.iloc[i]:
                    exit_px = c[i]
            else:
                if H[i] >= pos["stop"]:
                    exit_px = pos["stop"]
                elif c[i] > exit_hi.iloc[i]:
                    exit_px = c[i]
            if exit_px is not None:
                trades.append(dict(r=net_r(pos["entry"], exit_px, pos["risk"], pos["dir"]),
                                   er=pos["er"]))
                pos = None
    return trades


def ema_adx(df, fast=20, slow=50, adx_min=20, atr_mult=2.0):
    a = atr(df)
    er = eff_ratio(df["close"])
    ef = df["close"].ewm(span=fast, adjust=False).mean()
    es = df["close"].ewm(span=slow, adjust=False).mean()
    ax = adx(df)
    c = df["close"].values
    H, L = df["high"].values, df["low"].values
    up = (ef > es).values
    trades, pos = [], None
    for i in range(slow + 1, len(df)):
        if pos is None:
            cross_up = up[i] and not up[i - 1]
            cross_dn = (not up[i]) and up[i - 1]
            if cross_up and ax.iloc[i] >= adx_min:
                pos = dict(dir="long", entry=c[i], stop=c[i] - atr_mult * a.iloc[i],
                           risk=atr_mult * a.iloc[i], er=er.iloc[i])
            elif cross_dn and ax.iloc[i] >= adx_min:
                pos = dict(dir="short", entry=c[i], stop=c[i] + atr_mult * a.iloc[i],
                           risk=atr_mult * a.iloc[i], er=er.iloc[i])
        else:
            exit_px = None
            if pos["dir"] == "long":
                if L[i] <= pos["stop"]:
                    exit_px = pos["stop"]
                elif not up[i]:
                    exit_px = c[i]
            else:
                if H[i] >= pos["stop"]:
                    exit_px = pos["stop"]
                elif up[i]:
                    exit_px = c[i]
            if exit_px is not None:
                trades.append(dict(r=net_r(pos["entry"], exit_px, pos["risk"], pos["dir"]),
                                   er=pos["er"]))
                pos = None
    return trades


STRATS = {
    "Donchian(20/10)": lambda d: donchian(d, 20, 10),
    "Donchian(55/20)": lambda d: donchian(d, 55, 20),
    "EMA20/50+ADX20": lambda d: ema_adx(d, 20, 50, 20),
}


def summarize(trades):
    if not trades:
        return dict(n=0, total_r=0.0, win=0.0, avg_er=float("nan"))
    rs = [t["r"] for t in trades]
    wins = [t for t in trades if t["r"] > 0]
    ers = [t["er"] for t in trades if not np.isnan(t["er"])]
    return dict(n=len(trades), total_r=round(sum(rs), 1),
                win=round(100 * len(wins) / len(trades), 0),
                avg_er=round(float(np.mean(ers)), 2) if ers else float("nan"))


def main():
    s_ms = int(pd.Timestamp(START, tz="UTC").timestamp() * 1000)
    e_ms = int(pd.Timestamp(END, tz="UTC").timestamp() * 1000)
    data = {}
    for sym in SYMBOLS:
        df = fetch_klines(sym, INTERVAL, s_ms, e_ms, futures=True)
        print(f"{sym}: {len(df)} bars  {df.index.min()} -> {df.index.max()}")
        data[sym] = df

    print("\n" + "=" * 78)
    grand = {k: [] for k in STRATS}
    for name, fn in STRATS.items():
        print(f"\n### {name}")
        print(f"{'symbol':<10}{'trades':>7}{'totalR':>9}{'win%':>7}{'avgER@entry':>13}")
        for sym in SYMBOLS:
            if len(data[sym]) < 100:
                continue
            tr = fn(data[sym])
            grand[name].extend(tr)
            s = summarize(tr)
            print(f"{sym:<10}{s['n']:>7}{s['total_r']:>9}{s['win']:>6.0f}%{s['avg_er']:>13}")
        g = summarize(grand[name])
        print(f"{'ALL':<10}{g['n']:>7}{g['total_r']:>9}{g['win']:>6.0f}%{g['avg_er']:>13}")

    # ---- complementarity check: R by ER regime bucket for each strategy ----
    print("\n" + "=" * 78)
    print("R by ENTRY-REGIME bucket  (main's R lives in ER 0.20-0.35; strong = ER>0.35)")
    print(f"{'strategy':<18}{'chop<0.20':>12}{'light .20-.35':>15}{'strong>0.35':>13}")
    for name in STRATS:
        b = {"chop": 0.0, "light": 0.0, "strong": 0.0}
        for t in grand[name]:
            er = t["er"]
            if np.isnan(er):
                continue
            k = "chop" if er < 0.20 else ("light" if er < 0.35 else "strong")
            b[k] += t["r"]
        print(f"{name:<18}{b['chop']:>12.1f}{b['light']:>15.1f}{b['strong']:>13.1f}")


if __name__ == "__main__":
    main()
