"""Does a daily RELATIVE-VOLUME symbol gate improve the Donchian book?

Hypothesis (user): only trade symbols whose recent volume is above their N-day average.
Test it on the EXISTING Donchian trades (no re-backfill): for each trade compute the symbol's
prev-day relative volume (vol / N-day SMA, fully known at signal time -> no lookahead), bucket
trades by it, and compare expectancy IN-SAMPLE (2026) vs OOS (2024-25). If high-rel-vol trades
systematically pay more AND it holds OOS, the gate is worth building.
"""
import sys, os
sys.path.insert(0, "sync"); sys.path.insert(0, "sync/donchian"); sys.path.insert(0, "sync/live_exec")
os.environ.setdefault("DCH_ENTRY_AT_CONFIRM", "1")
import pandas as pd, numpy as np
import trade_sync_common as tsc

VERSIONS = sys.argv[1:] or ["d30so8f3h7"]
N = 20  # volume SMA window (days)


def load_trades(version):
    conn = tsc.backtest_conn(); cur = conn.cursor()
    cur.execute(f"""SELECT symbol, signal_time, direction, pnl_r
                    FROM {tsc.TABLE} WHERE version=%s AND pnl_r IS NOT NULL""", (version,))
    rows = cur.fetchall(); cur.close(); conn.close()
    df = pd.DataFrame(rows, columns=["symbol", "signal_time", "direction", "pnl_r"])
    df["signal_time"] = pd.to_datetime(df["signal_time"], utc=True)
    df["pnl_r"] = df["pnl_r"].astype(float)
    return df


_DAILY = {}
def rel_vol_series(sym):
    if sym in _DAILY:
        return _DAILY[sym]
    d = tsc.fetch_klines(sym, "1d", int(pd.Timestamp("2023-10-01", tz="UTC").timestamp() * 1000),
                         int(pd.Timestamp("2026-06-29", tz="UTC").timestamp() * 1000))
    if d is None or d.empty:
        _DAILY[sym] = None; return None
    vol = d["volume"].astype(float)
    sma = vol.rolling(N).mean()
    rel = (vol / sma)
    _DAILY[sym] = rel
    return rel


def attach_relvol(df):
    out = []
    for sym, g in df.groupby("symbol"):
        rel = rel_vol_series(sym)
        for _, r in g.iterrows():
            rv = np.nan
            if rel is not None:
                # last daily bar STRICTLY before the signal day -> no lookahead
                day = r["signal_time"].normalize()
                prior = rel.loc[rel.index < day]
                if len(prior):
                    rv = float(prior.iloc[-1])
            out.append({**r.to_dict(), "rel_vol": rv})
    return pd.DataFrame(out)


def stats(s):
    s = s.dropna(subset=["pnl_r"])
    if not len(s):
        return dict(n=0, R=0, avgR=0, WR=0, PF=0)
    R = s["pnl_r"].values
    gp = R[R > 0].sum(); gl = -R[R < 0].sum()
    return dict(n=len(R), R=R.sum(), avgR=R.mean(), WR=100 * (R > 0).mean(),
                PF=(gp / gl if gl > 0 else float("inf")))


def show(title, s):
    m = stats(s)
    print(f"  {title:26} n={m['n']:5} R={m['R']:+7.1f} avgR={m['avgR']:+.3f} "
          f"WR={m['WR']:4.1f}% PF={m['PF']:.2f}")


def period(df, name, mask):
    sub = df[mask]
    print(f"\n--- {name} (n={len(sub)}) ---")
    have = sub.dropna(subset=["rel_vol"])
    miss = len(sub) - len(have)
    show("ALL", sub)
    # buckets
    bins = [0, 0.8, 1.0, 1.2, 1.5, 2.0, 99]
    labs = ["<0.8", "0.8-1.0", "1.0-1.2", "1.2-1.5", "1.5-2.0", ">2.0"]
    have = have.copy()
    have["b"] = pd.cut(have["rel_vol"], bins=bins, labels=labs)
    for lab in labs:
        show(f"relvol {lab}", have[have["b"] == lab])
    # threshold gates (keep trades with rel_vol >= t)
    print("  gates (keep rel_vol >= t):")
    base = stats(have)
    for t in [1.0, 1.2, 1.5, 2.0]:
        kept = have[have["rel_vol"] >= t]
        m = stats(kept)
        frac = 100 * m["n"] / base["n"] if base["n"] else 0
        print(f"    >= {t:<4} keep {frac:4.0f}%  n={m['n']:5} R={m['R']:+7.1f} "
              f"avgR={m['avgR']:+.3f} (base {base['avgR']:+.3f}) WR={m['WR']:4.1f}% PF={m['PF']:.2f}")
    if miss:
        print(f"  ({miss} trades had no daily-vol history -> excluded from buckets)")


for v in VERSIONS:
    print(f"\n================= {v} (N={N}d volume SMA) =================")
    df = load_trades(v)
    df = attach_relvol(df)
    y = df["signal_time"].dt.year
    period(df, "FULL 2024-2026", y >= 2024)
    period(df, "IN-SAMPLE 2026", y == 2026)
    period(df, "OOS 2024-2025", y < 2026)
