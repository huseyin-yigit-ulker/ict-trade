"""Volume CHANGE / momentum (not level): is volume EXPANDING vs a prior period at signal time,
and does that predict better Donchian trades — robustly OOS?

vol_change(K) = mean(vol[d-K : d-1]) / mean(vol[d-2K : d-K])   (>1 = volume building, <1 = fading)
Both windows end strictly before the signal day -> no lookahead. Bucket trades by it, IS vs OOS.
"""
import sys, os
sys.path.insert(0, "sync"); sys.path.insert(0, "sync/donchian"); sys.path.insert(0, "sync/live_exec")
os.environ.setdefault("DCH_ENTRY_AT_CONFIRM", "1")
import pandas as pd, numpy as np
import trade_sync_common as tsc

VERSIONS = sys.argv[1:] or ["d30so8f3h7"]
KS = [5, 10]   # volume-change windows (days): last K vs prior K


def load_trades(version):
    conn = tsc.backtest_conn(); cur = conn.cursor()
    cur.execute(f"""SELECT symbol, signal_time, pnl_r FROM {tsc.TABLE}
                    WHERE version=%s AND pnl_r IS NOT NULL""", (version,))
    rows = cur.fetchall(); cur.close(); conn.close()
    df = pd.DataFrame(rows, columns=["symbol", "signal_time", "pnl_r"])
    df["signal_time"] = pd.to_datetime(df["signal_time"], utc=True)
    df["pnl_r"] = df["pnl_r"].astype(float)
    return df


_VOL = {}
def vol_series(sym):
    if sym in _VOL:
        return _VOL[sym]
    d = tsc.fetch_klines(sym, "1d", int(pd.Timestamp("2023-09-01", tz="UTC").timestamp() * 1000),
                         int(pd.Timestamp("2026-06-29", tz="UTC").timestamp() * 1000))
    v = None if (d is None or d.empty) else d["volume"].astype(float)
    if v is not None:
        v.index = pd.to_datetime(v.index, utc=True).normalize()
    _VOL[sym] = v
    return v


def attach(df):
    out = []
    for sym, g in df.groupby("symbol"):
        v = vol_series(sym)
        for _, r in g.iterrows():
            rec = {**r.to_dict()}
            day = r["signal_time"].normalize()
            for K in KS:
                ch = np.nan
                if v is not None:
                    prior = v.loc[v.index < day]
                    if len(prior) >= 2 * K:
                        recent = prior.iloc[-K:].mean()
                        older = prior.iloc[-2 * K:-K].mean()
                        if older > 0:
                            ch = float(recent / older)
                rec[f"ch{K}"] = ch
            out.append(rec)
    return pd.DataFrame(out)


def stats(s):
    R = s["pnl_r"].dropna().values
    if not len(R):
        return dict(n=0, R=0, avgR=0, WR=0, PF=0)
    gp = R[R > 0].sum(); gl = -R[R < 0].sum()
    return dict(n=len(R), R=R.sum(), avgR=R.mean(), WR=100 * (R > 0).mean(),
                PF=(gp / gl if gl > 0 else float("inf")))


def show(t, s):
    m = stats(s)
    print(f"  {t:22} n={m['n']:5} R={m['R']:+7.1f} avgR={m['avgR']:+.3f} WR={m['WR']:4.1f}% PF={m['PF']:.2f}")


def period(df, name, mask, K):
    sub = df[mask].dropna(subset=[f"ch{K}"])
    col = f"ch{K}"
    print(f"\n--- {name} | vol-change K={K} (n={len(sub)}) ---")
    show("ALL", sub)
    bins = [0, 0.7, 0.9, 1.1, 1.3, 1.6, 99]
    labs = ["<0.7 fade", "0.7-0.9", "0.9-1.1 flat", "1.1-1.3", "1.3-1.6", ">1.6 surge"]
    b = pd.cut(sub[col], bins=bins, labels=labs)
    for lab in labs:
        show(lab, sub[b == lab])
    base = stats(sub)
    print("  gates:")
    for t in [1.1, 1.3, 1.6]:
        kept = sub[sub[col] >= t]; m = stats(kept)
        frac = 100 * m["n"] / base["n"] if base["n"] else 0
        print(f"    expand >= {t:<4} keep {frac:3.0f}%  R={m['R']:+7.1f} avgR={m['avgR']:+.3f} "
              f"(base {base['avgR']:+.3f}) WR={m['WR']:4.1f}% PF={m['PF']:.2f}")
    # contracting side too
    kept = sub[sub[col] < 0.9]; m = stats(kept)
    print(f"    fade   <  0.9  keep {100*m['n']/base['n'] if base['n'] else 0:3.0f}%  "
          f"R={m['R']:+7.1f} avgR={m['avgR']:+.3f} WR={m['WR']:4.1f}% PF={m['PF']:.2f}")


for v in VERSIONS:
    print(f"\n================= {v} | volume CHANGE =================")
    df = attach(load_trades(v))
    y = df["signal_time"].dt.year
    for K in KS:
        period(df, "IN-SAMPLE 2026", y == 2026, K)
        period(df, "OOS 2024-2025", y < 2026, K)
