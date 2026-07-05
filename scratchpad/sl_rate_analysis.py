"""Which volume change REDUCES the full-SL rate, robustly (IS 2026 AND OOS 2024-25)?

User's lens: WR is structurally tied to TP1; a good entry filter should show up as FEWER
full stop-outs. So score every candidate by SL-rate = share of trades closing at full SL
(status='closed_sl'). A change is worth applying only if it cuts SL-rate in BOTH periods.

Computes 3 volume features per trade and reports base vs gated SL-rate (+ trades kept):
  A) level     rel_vol = prevday vol / 20d SMA        (is volume above its own average)
  B) xsec      cross-sectional USD-notional rank      (most-active symbols)
  C) change    vol[d-K:d]/vol[d-2K:d-K]               (volume expanding vs prior period)
"""
import sys, os
sys.path.insert(0, "sync"); sys.path.insert(0, "sync/donchian"); sys.path.insert(0, "sync/live_exec")
os.environ.setdefault("DCH_ENTRY_AT_CONFIRM", "1")
import pandas as pd, numpy as np
import trade_sync_common as tsc
import strategy as strat

VERSION = sys.argv[1] if len(sys.argv) > 1 else "d30so8f3h7"
N = 20; K = 10
UNIV = list(strat.SYMBOLS)


def load():
    conn = tsc.backtest_conn(); cur = conn.cursor()
    cur.execute(f"""SELECT symbol, signal_time, pnl_r, status FROM {tsc.TABLE}
                    WHERE version=%s AND pnl_r IS NOT NULL""", (VERSION,))
    rows = cur.fetchall(); cur.close(); conn.close()
    df = pd.DataFrame(rows, columns=["symbol", "signal_time", "pnl_r", "status"])
    df["signal_time"] = pd.to_datetime(df["signal_time"], utc=True)
    df["pnl_r"] = df["pnl_r"].astype(float)
    df["is_sl"] = (df["status"] == "closed_sl").astype(int)
    return df


_D = {}
def daily(sym):
    if sym not in _D:
        d = tsc.fetch_klines(sym, "1d", int(pd.Timestamp("2023-09-01", tz="UTC").timestamp() * 1000),
                             int(pd.Timestamp("2026-06-29", tz="UTC").timestamp() * 1000))
        if d is not None and not d.empty:
            d.index = pd.to_datetime(d.index, utc=True).normalize()
        _D[sym] = d
    return _D[sym]


def rank_panel():
    notion = {}
    for sym in UNIV:
        d = daily(sym)
        if d is None or d.empty:
            continue
        notion[sym] = (d["close"].astype(float) * d["volume"].astype(float)).rolling(N).mean().shift(1)
    p = pd.DataFrame(notion)
    return p.rank(axis=1, ascending=False, method="min")


def features(df):
    rk = rank_panel()
    days = rk.index
    out = []
    for sym, g in df.groupby("symbol"):
        d = daily(sym)
        vol = None if (d is None or d.empty) else d["volume"].astype(float)
        sma = None if vol is None else vol.rolling(N).mean()
        for _, r in g.iterrows():
            day = r["signal_time"].normalize()
            lvl = ch = rank = np.nan
            if vol is not None:
                prior = vol.loc[vol.index < day]
                if len(prior):
                    s = sma.loc[sma.index < day]
                    if len(s) and s.iloc[-1] > 0:
                        lvl = float(prior.iloc[-1] / s.iloc[-1])
                if len(prior) >= 2 * K:
                    older = prior.iloc[-2 * K:-K].mean()
                    if older > 0:
                        ch = float(prior.iloc[-K:].mean() / older)
            i = days.searchsorted(day, side="right") - 1
            if i >= 0 and sym in rk.columns:
                rank = rk.at[days[i], sym]
            out.append({**r.to_dict(), "lvl": lvl, "ch": ch, "rank": rank})
    return pd.DataFrame(out)


def slrate(s):
    s = s.dropna(subset=["is_sl"])
    return (len(s), 100 * s["is_sl"].mean() if len(s) else 0,
            s["pnl_r"].sum(), 100 * (s["pnl_r"] > 0).mean() if len(s) else 0)


def report(df, feat, gates, label):
    print(f"\n##### {label} #####")
    for nm, mask_is, mask_oos in [("IN-SAMPLE 2026", df["signal_time"].dt.year == 2026, None),
                                  ("OOS 2024-25", df["signal_time"].dt.year < 2026, None)]:
        sub = df[mask_is].dropna(subset=[feat])
        bn, bsl, bR, bwr = slrate(sub)
        print(f"  -- {nm}: base  n={bn:5} SLrate={bsl:4.1f}%  WR={bwr:4.1f}%  R={bR:+.1f}")
        for gname, gfn in gates:
            kept = sub[gfn(sub[feat])]
            n, sl, R, wr = slrate(kept)
            keep = 100 * n / bn if bn else 0
            flag = "  <== SL down" if sl < bsl - 0.3 else ""
            print(f"       {gname:16} keep{keep:4.0f}%  n={n:5} SLrate={sl:4.1f}% (Δ{sl-bsl:+4.1f}) "
                  f"WR={wr:4.1f}% R={R:+7.1f}{flag}")


df = features(load())
print(f"================= {VERSION} — SL-RATE lens (N={N}, K={K}) =================")
report(df, "ch", [("fade <0.9", lambda x: x < 0.9), ("fade <1.0", lambda x: x < 1.0),
                  ("<0.7 deep", lambda x: x < 0.7), ("expand >=1.3", lambda x: x >= 1.3)],
       "C) VOLUME CHANGE (expanding vs prior period)")
report(df, "lvl", [("relvol <1.0", lambda x: x < 1.0), ("relvol <0.8", lambda x: x < 0.8),
                   ("relvol >=1.5", lambda x: x >= 1.5)],
       "A) VOLUME LEVEL (vs own 20d average)")
report(df, "rank", [("top-5", lambda x: x <= 5), ("exclude top-5", lambda x: x > 5),
                    ("mid 11-20", lambda x: (x >= 11) & (x <= 20))],
       "B) CROSS-SECTIONAL rank (most active)")
