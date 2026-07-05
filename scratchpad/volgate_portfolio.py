"""Portfolio-level test of the VOLUME-CONTRACTION gate on d30so8f3h7.

Build the live stream's events ONCE over the full universe (2024-01-01..now), attach each a
volume-change value (vol[d-K:d]/vol[d-2K:d-K], no lookahead), then re-run the portfolio walk
at several contraction thresholds and report SL-rate / WR / total-R / worst-month / per-year.
Confirms whether the per-trade SL-rate reduction survives the portfolio interactions.
"""
import sys, os
sys.path.insert(0, "sync"); sys.path.insert(0, "sync/donchian"); sys.path.insert(0, "sync/live_exec")
os.environ.setdefault("DCH_ENTRY_AT_CONFIRM", "1")
import pandas as pd, numpy as np
import _bootenv  # noqa: F401
import portfolio_backfill as pb
import trade_sync_common as tsc

K = 10
ST = pb.STREAMS["d30so8f3h7"]
W_START = pd.Timestamp("2024-01-01", tz="UTC")
W_END = pd.Timestamp.now(tz="UTC")

_D = {}
def vol_series(sym):
    if sym not in _D:
        d = tsc.fetch_klines(sym, "1d", int(pd.Timestamp("2023-09-01", tz="UTC").timestamp() * 1000),
                             int(pd.Timestamp("2026-06-29", tz="UTC").timestamp() * 1000))
        v = None
        if d is not None and not d.empty:
            v = d["volume"].astype(float)
            v.index = pd.to_datetime(v.index, utc=True).normalize()
        _D[sym] = v
    return _D[sym]


def vchange(sym, signal_ts):
    v = vol_series(sym)
    if v is None:
        return np.nan
    day = pd.Timestamp(signal_ts)
    day = (day.tz_localize("UTC") if day.tz is None else day.tz_convert("UTC")).normalize()
    prior = v.loc[v.index < day]
    if len(prior) < 2 * K:
        return np.nan
    older = prior.iloc[-2 * K:-K].mean()
    return float(prior.iloc[-K:].mean() / older) if older > 0 else np.nan


def stats(realized):
    closed = [r for r in realized if r.get("r") is not None]
    if not closed:
        return None
    R = np.array([r["r"] for r in closed])
    sl = np.mean([r["status"] == "closed_sl" for r in closed]) * 100
    wr = np.mean(R > 0) * 100
    gp = R[R > 0].sum(); gl = -R[R < 0].sum()
    bym = {}
    for r in closed:
        if r.get("exit") is not None:
            m = pd.Timestamp(r["exit"]).strftime("%Y-%m"); bym[m] = bym.get(m, 0) + r["r"]
    worst = min(bym.values()) if bym else 0
    yr = {}
    for r in closed:
        if r.get("exit") is not None:
            y = pd.Timestamp(r["exit"]).year; yr[y] = yr.get(y, 0) + r["r"]
    return dict(n=len(closed), R=R.sum(), SL=sl, WR=wr, PF=(gp / gl if gl else float("inf")),
                worst=worst, yr=yr)


print(f"=== building d30so8f3h7 events (full universe {W_START.date()}..{W_END.date()}) ===", flush=True)
all_ev = []
for sym in pb.SYMBOLS:
    try:
        ev = pb.build_events(sym, ST, W_START, W_END)
        for e in ev:
            e["vch"] = vchange(sym, e["signal_ts"])
        all_ev += ev
        if ev:
            print(f"  {sym:<12} {len(ev):>4}", flush=True)
    except Exception as ex:  # noqa: BLE001
        print(f"  ! {sym}: {type(ex).__name__}: {ex}", flush=True)

print(f"\n  total events: {len(all_ev)}", flush=True)
GATES = [("BASE (no gate)", None), ("vch < 1.0", 1.0), ("vch < 0.9", 0.9), ("vch < 0.7", 0.7)]
print(f"\n{'gate':16} {'n':>5} {'SLrate':>7} {'WR':>6} {'totR':>8} {'PF':>5} {'worstMo':>8}  per-year")
print("-" * 92)
for name, thr in GATES:
    evs = all_ev if thr is None else [e for e in all_ev if not np.isnan(e.get("vch", np.nan)) and e["vch"] < thr]
    realized = pb.walk(evs, ST, W_START, W_END)
    m = stats(realized)
    if not m:
        continue
    yr = "  ".join(f"{y}:{m['yr'].get(y,0):+.0f}" for y in [2024, 2025, 2026])
    print(f"{name:16} {m['n']:5} {m['SL']:6.1f}% {m['WR']:5.1f}% {m['R']:+8.1f} {m['PF']:4.2f} "
          f"{m['worst']:+8.1f}  {yr}", flush=True)
