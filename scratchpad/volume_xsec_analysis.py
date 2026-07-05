"""Cross-sectional volume selection: do Donchian trades on the MOST-ACTIVE symbols (top-K by
daily USD-notional volume in the universe) outperform — and does it hold OOS?

Per day, rank every universe symbol by its trailing-N-day mean USD-notional volume
(close*volume, shifted -> no lookahead). Attach each trade its symbol's cross-sectional
rank/percentile on its signal day. Bucket by rank tier + "keep top-K" gate. IS (2026) vs OOS.
"""
import sys, os
sys.path.insert(0, "sync"); sys.path.insert(0, "sync/donchian"); sys.path.insert(0, "sync/live_exec")
os.environ.setdefault("DCH_ENTRY_AT_CONFIRM", "1")
import pandas as pd, numpy as np
import trade_sync_common as tsc
import strategy as strat

VERSIONS = sys.argv[1:] or ["d30so8f3h7"]
N = 20  # trailing window (days) for the liquidity measure
UNIV = list(strat.SYMBOLS)


def load_trades(version):
    conn = tsc.backtest_conn(); cur = conn.cursor()
    cur.execute(f"""SELECT symbol, signal_time, direction, pnl_r FROM {tsc.TABLE}
                    WHERE version=%s AND pnl_r IS NOT NULL""", (version,))
    rows = cur.fetchall(); cur.close(); conn.close()
    df = pd.DataFrame(rows, columns=["symbol", "signal_time", "direction", "pnl_r"])
    df["signal_time"] = pd.to_datetime(df["signal_time"], utc=True)
    df["pnl_r"] = df["pnl_r"].astype(float)
    return df


def build_rank_panel():
    """Daily DataFrame: index=date, cols=symbols, value = trailing-N-day mean USD-notional,
    as-of the PRIOR day (shifted). Then per-row rank (1=most active) + percentile."""
    notional = {}
    for sym in UNIV:
        d = tsc.fetch_klines(sym, "1d", int(pd.Timestamp("2023-10-01", tz="UTC").timestamp() * 1000),
                             int(pd.Timestamp("2026-06-29", tz="UTC").timestamp() * 1000))
        if d is None or d.empty:
            continue
        usd = (d["close"].astype(float) * d["volume"].astype(float))
        notional[sym] = usd.rolling(N).mean().shift(1)        # shift -> known at signal day
    panel = pd.DataFrame(notional)
    panel.index = pd.to_datetime(panel.index, utc=True).normalize()
    rank = panel.rank(axis=1, ascending=False, method="min")   # 1 = most active that day
    pct = panel.rank(axis=1, ascending=True, pct=True)         # 1.0 = most active (top), 0 = least
    return rank, pct


def attach(df, rank, pct):
    days = rank.index
    out = []
    for _, r in df.iterrows():
        day = r["signal_time"].normalize()
        i = days.searchsorted(day, side="right") - 1           # last panel day <= signal day
        rk = pe = np.nan
        if i >= 0:
            d0 = days[i]
            rk = rank.at[d0, r["symbol"]] if r["symbol"] in rank.columns else np.nan
            pe = pct.at[d0, r["symbol"]] if r["symbol"] in pct.columns else np.nan
        out.append({**r.to_dict(), "rank": rk, "pct": pe})
    return pd.DataFrame(out)


def stats(s):
    s = s.dropna(subset=["pnl_r"]); R = s["pnl_r"].values
    if not len(R):
        return dict(n=0, R=0, avgR=0, WR=0, PF=0)
    gp = R[R > 0].sum(); gl = -R[R < 0].sum()
    return dict(n=len(R), R=R.sum(), avgR=R.mean(), WR=100 * (R > 0).mean(),
                PF=(gp / gl if gl > 0 else float("inf")))


def show(t, s):
    m = stats(s)
    print(f"  {t:24} n={m['n']:5} R={m['R']:+7.1f} avgR={m['avgR']:+.3f} WR={m['WR']:4.1f}% PF={m['PF']:.2f}")


def period(df, name, mask):
    sub = df[mask].dropna(subset=["rank"])
    print(f"\n--- {name} (n={len(sub)}) ---")
    show("ALL", sub)
    for lo, hi, lab in [(1, 10, "rank 1-10 (top)"), (11, 20, "rank 11-20"),
                        (21, 30, "rank 21-30"), (31, 99, "rank 31+")]:
        show(lab, sub[(sub["rank"] >= lo) & (sub["rank"] <= hi)])
    base = stats(sub)
    print("  keep only top-K most-active symbols:")
    for k in [5, 10, 15, 20]:
        kept = sub[sub["rank"] <= k]; m = stats(kept)
        frac = 100 * m["n"] / base["n"] if base["n"] else 0
        print(f"    top-{k:<2} keep {frac:4.0f}%  n={m['n']:5} R={m['R']:+7.1f} "
              f"avgR={m['avgR']:+.3f} (base {base['avgR']:+.3f}) WR={m['WR']:4.1f}% PF={m['PF']:.2f}")


for v in VERSIONS:
    print(f"\n================= {v} | cross-sectional USD-vol rank (N={N}d) =================")
    rank, pct = build_rank_panel()
    df = attach(load_trades(v), rank, pct)
    y = df["signal_time"].dt.year
    period(df, "FULL 2024-2026", y >= 2024)
    period(df, "IN-SAMPLE 2026", y == 2026)
    period(df, "OOS 2024-2025", y < 2026)
