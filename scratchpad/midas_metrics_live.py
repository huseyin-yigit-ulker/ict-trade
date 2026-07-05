"""Show the EXACT metrics MIDAS computes on live XAUUSDT 1m data for a signal, bar by bar."""
import sys
sys.path.insert(0, "sync"); sys.path.insert(0, "sync/midas"); sys.path.insert(0, "sync/live_exec")
import pandas as pd, numpy as np
import strategy as M

now = pd.Timestamp.now(tz="UTC")
df = M.load_1m(now - pd.Timedelta(hours=10), now)
df = M.add_market_open(df)
bar = pd.Timedelta(minutes=1)
df = df[df.index + bar <= now]                 # only closed bars

atr = M.atr_tf(df)
vwap = M.anchored_vwap(df)
slope = (vwap - vwap.shift(M.SLOPE_N))
o, c = df["open"].to_numpy(), df["close"].to_numpy()
lo, hi = df["low"].to_numpy(), df["high"].to_numpy()
vw, a, sl = vwap.to_numpy(), atr.to_numpy(), slope.to_numpy()
om = df["open_mkt"].to_numpy(bool)
uth = df.index.hour.to_numpy()
tol = M.TOUCH_TOL * a

print(f"XAUUSDT 1m · now={now:%Y-%m-%d %H:%M}Z · last close={c[-1]:.2f}")
print(f"config: SLOPE_N={M.SLOPE_N} ATR(15m,{M.ATR_N}) touch_tol={M.TOUCH_TOL}·ATR  "
      f"initSL={M.ATR_INIT_MULT}·ATR  trail={M.TRAIL_MULT}·ATR  skipUTC=[{M.SKIP_UTC_START},{M.SKIP_UTC_END})\n")
print("LONG  needs: open_mkt · UTC∉[7,13) · close>VWAP · slope>0 · low≤VWAP+0.25ATR (pullback) · close>open")
print("SHORT needs: open_mkt · UTC∉[7,13) · close<VWAP · slope<0 · high≥VWAP−0.25ATR (pullback) · close<open\n")

hdr = f"{'time(UTC)':16} {'open':>8} {'close':>8} {'VWAP':>8} {'slope60':>8} {'ATR15':>6} {'tol':>5} {'c-VWAP':>7} {'low-VWAP':>8}  mkt sess  >VW slope pull bar  SIG"
print(hdr); print("-" * len(hdr))


def row(i):
    above = c[i] > vw[i]; below = c[i] < vw[i]
    slp_up = sl[i] > 0; slp_dn = sl[i] < 0
    pull_l = lo[i] <= vw[i] + tol[i]; pull_s = hi[i] >= vw[i] - tol[i]
    bull = c[i] > o[i]; bear = c[i] < o[i]
    sess = not (M.SKIP_UTC_START <= uth[i] < M.SKIP_UTC_END)
    sig = ""
    if om[i] and sess and np.isfinite(vw[i]) and np.isfinite(a[i]) and a[i] > 0:
        if above and slp_up and pull_l and bull:
            sig = f"LONG sl={c[i]-M.ATR_INIT_MULT*a[i]:.2f}"
        elif below and slp_dn and pull_s and bear:
            sig = f"SHORT sl={c[i]+M.ATR_INIT_MULT*a[i]:.2f}"
    # which direction's conditions to display (use trend side)
    isL = sl[i] >= 0
    vwflag = ("✓" if above else "·") if isL else ("✓" if below else "·")
    slflag = "✓" if (slp_up if isL else slp_dn) else "·"
    pullflag = "✓" if (pull_l if isL else pull_s) else "·"
    barflag = "✓" if (bull if isL else bear) else "·"
    return (f"{df.index[i]:%m-%d %H:%M}    {o[i]:8.2f} {c[i]:8.2f} {vw[i]:8.2f} {sl[i]:+8.2f} {a[i]:6.2f} "
            f"{tol[i]:5.2f} {c[i]-vw[i]:+7.2f} {lo[i]-vw[i]:+8.2f}   {'Y' if om[i] else 'n'}  "
            f"{'Y' if sess else 'n'}   {vwflag}   {slflag}   {pullflag}   {barflag}   {sig}")


for i in range(len(df) - 16, len(df)):
    print(row(i))

# any signals in the loaded window?
side, stop = M.signals(df, atr)
fires = np.where(side != 0)[0]
print(f"\nsignals fired in last 10h window: {len(fires)}")
for i in fires[-6:]:
    print(f"  {df.index[i]:%m-%d %H:%M}  {'LONG' if side[i]>0 else 'SHORT'}  entry(next open)~{c[i]:.2f}  initSL={stop[i]:.2f}")
