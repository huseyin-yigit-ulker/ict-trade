"""2026 backtest of d30so8f3h7 (signals + scale-out) on the TOP-100 crypto universe, comparing
UNGATED vs the vch<0.9 VOLUME-CONTRACTION gate. Exploration only (no DB write)."""
import sys, os
sys.path.insert(0, "sync"); sys.path.insert(0, "sync/donchian"); sys.path.insert(0, "sync/live_exec")
os.environ.setdefault("DCH_ENTRY_AT_CONFIRM", "1")
import numpy as np, pandas as pd
import _bootenv  # noqa: F401
import portfolio_backfill as pb
import trade_sync_common as tsc

ST = pb.STREAMS["d30so8f3h7"]
K, THR = 10, 0.9
W_START = pd.Timestamp("2026-01-01", tz="UTC")
W_END = pd.Timestamp("2026-06-22", tz="UTC")
SYMS = [s.strip() for s in open("scratchpad/top100_clean.txt") if s.strip()]

_D = {}
def _vch(sym, ts):
    if sym not in _D:
        d = tsc.fetch_klines(sym, "1d", int(pd.Timestamp("2025-09-01", tz="UTC").timestamp() * 1000),
                             int(W_END.timestamp() * 1000))
        v = None
        if d is not None and not d.empty:
            v = d["volume"].astype(float); v.index = pd.to_datetime(v.index, utc=True).normalize()
        _D[sym] = v
    v = _D[sym]
    if v is None:
        return np.nan
    day = pd.Timestamp(ts); day = (day.tz_localize("UTC") if day.tz is None else day.tz_convert("UTC")).normalize()
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
    gp = R[R > 0].sum(); gl = -R[R < 0].sum()
    bym = {}
    for r in closed:
        if r.get("exit") is not None:
            m = pd.Timestamp(r["exit"]).strftime("%Y-%m"); bym[m] = bym.get(m, 0) + r["r"]
    return dict(n=len(R), R=R.sum(), SL=sl, WR=np.mean(R > 0) * 100, avgR=R.mean(),
                PF=(gp / gl if gl else float("inf")), worst=min(bym.values()) if bym else 0,
                negM=sum(1 for v in bym.values() if v < 0), nM=len(bym))


print(f"=== TOP-100 ({len(SYMS)} syms) | d30so8f3h7 | 2026 | building events ===", flush=True)
all_ev, per = [], {}
for sym in SYMS:
    try:
        ev = pb.build_events(sym, ST, W_START, W_END)
        for e in ev:
            e["vch"] = _vch(sym, e["signal_ts"])
        all_ev += ev; per[sym] = len(ev)
        print(f"  {sym:<14} {len(ev):>4}", flush=True)
    except Exception as ex:  # noqa: BLE001
        print(f"  ! {sym}: {type(ex).__name__}: {str(ex)[:60]}", flush=True)

print(f"\n  total events: {len(all_ev)}\n", flush=True)
for name, evs in [("UNGATED (all top-100)", all_ev),
                  ("GATED vch<0.9", [e for e in all_ev if not np.isnan(e.get("vch", np.nan)) and e["vch"] < THR])]:
    m = stats(pb.walk(evs, ST, W_START, W_END))
    if m:
        print(f"  {name:24} n={m['n']:5} R={m['R']:+7.1f} avgR={m['avgR']:+.3f} WR={m['WR']:4.1f}% "
              f"SL={m['SL']:4.1f}% PF={m['PF']:.2f} worstMo={m['worst']:+.1f} neg={m['negM']}/{m['nM']}", flush=True)

# per-symbol R for the gated walk (top/bottom contributors)
real = pb.walk([e for e in all_ev if not np.isnan(e.get("vch", np.nan)) and e["vch"] < THR], ST, W_START, W_END)
bysym = {}
for r in real:
    if r.get("r") is not None:
        bysym.setdefault(r["symbol"], 0.0); bysym[r["symbol"]] += r["r"]
ranked = sorted(bysym.items(), key=lambda x: x[1], reverse=True)
print("\n  gated top 12:", "  ".join(f"{s.replace('USDT','')}:{r:+.0f}" for s, r in ranked[:12]))
print("  gated bot 12:", "  ".join(f"{s.replace('USDT','')}:{r:+.0f}" for s, r in ranked[-12:]))
