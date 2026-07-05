"""Fully independent reimplementation of the VWAP-trend pullback claim.
Does NOT import engine.py or fxstrat.py. Written from scratch off the spec.
"""
import numpy as np
import pandas as pd

PKL = "/home/ulkerhuseyin1905/ict-trade/scratchpad/fx_gold/xauusdt_1m_2026h1.pkl"

df = pd.read_pickle(PKL)
df = df.sort_index()
assert str(df.index.tz) == "UTC"

idx = df.index
et = idx.tz_convert("America/New_York")
dow = et.dayofweek          # Mon=0..Sun=6
hour = et.hour
minute = et.minute

# ---- market-hours filter: Sun 18:00 ET -> Fri 17:00 ET, daily 17:00-18:00 break ----
is_open = np.ones(len(df), dtype=bool)
is_open &= ~(dow == 5)                      # Saturday closed
is_open &= ~((dow == 6) & (hour < 18))      # Sun opens 18:00 ET
is_open &= ~((dow == 4) & (hour >= 17))     # Fri closes 17:00 ET
is_open &= ~((dow <= 3) & (hour == 17))     # Mon-Thu 17:00-18:00 break
openmkt = is_open

# ---- FX-day id: boundary at 18:00 ET ----
shifted = et - pd.Timedelta(hours=18)
fxday = shifted.normalize().asi8   # integer ns at midnight (unique per fx-day)

# ---- ATR(15m,14) ffilled to 1m ----
g = df.resample("15min", label="right", closed="right").agg(
    {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
pc = g["close"].shift(1)
tr15 = pd.concat([(g["high"] - g["low"]),
                  (g["high"] - pc).abs(),
                  (g["low"] - pc).abs()], axis=1).max(axis=1)
atr15 = tr15.ewm(alpha=1.0/14, adjust=False).mean()
atr = atr15.reindex(idx, method="ffill").to_numpy()

# ---- anchored daily VWAP + cumulative std ----
tp = (df["high"] + df["low"] + df["close"]) / 3.0
vol = df["volume"].replace(0, np.nan).ffill().fillna(1.0)
day_s = pd.Series(fxday, index=idx)
pv = (tp * vol).groupby(day_s).cumsum()
cv = vol.groupby(day_s).cumsum()
vwap = (pv / cv).to_numpy()

# ---- signal: vwap_trend, slope_n=60, atr_mult=1.5, touch_tol=0.25 ----
SLOPE_N = 60
ATR_MULT = 1.5
TOUCH_TOL = 0.25
C = df["close"].to_numpy(); O = df["open"].to_numpy()
LO = df["low"].to_numpy(); HI = df["high"].to_numpy()
vw = vwap
slope = vw - np.concatenate([np.full(SLOPE_N, np.nan), vw[:-SLOPE_N]])
tol = TOUCH_TOL * atr

n = len(df)
sig_side = np.zeros(n)
sig_stop = np.full(n, np.nan)
for i in range(2, n):
    if not openmkt[i] or not np.isfinite(vw[i]) or not np.isfinite(atr[i]) or atr[i] <= 0:
        continue
    if (C[i] > vw[i] and slope[i] > 0 and LO[i] <= vw[i] + tol[i] and C[i] > O[i]):
        es = C[i] - ATR_MULT * atr[i]
        sig_side[i] = 1; sig_stop[i] = es
    elif (C[i] < vw[i] and slope[i] < 0 and HI[i] >= vw[i] - tol[i] and C[i] < O[i]):
        es = C[i] + ATR_MULT * atr[i]
        sig_side[i] = -1; sig_stop[i] = es

# ---- backtest: enter next-open, init stop 1.5ATR, ATR-trail 3.5x, 8h max-hold, force-flat session ----
COST = 0.50
MAX_HOLD = 480
TRAIL = 3.5
o = O; h = HI; l = LO; c = C
ts = idx
trades = []
i = 0
while i < n - 1:
    s = sig_side[i]
    if s == 0 or not openmkt[i] or not openmkt[i+1] or not np.isfinite(sig_stop[i]):
        i += 1; continue
    k = i + 1
    entry = o[k]
    sd = abs(entry - sig_stop[i])
    if sd <= 0 or not np.isfinite(sd):
        i += 1; continue
    st = sig_stop[i]
    best = entry
    exit_px = np.nan; exit_idx = None; reason = ""
    j = k
    while j < n:
        if not openmkt[j]:
            exit_px = c[j-1]; exit_idx = j-1; reason = "session"; break
        hit_stop = (l[j] <= st) if s > 0 else (h[j] >= st)
        if hit_stop:
            exit_px = min(st, o[j]) if s > 0 else max(st, o[j])
            exit_idx = j; reason = "stop"; break
        if MAX_HOLD and (j - k) >= MAX_HOLD:
            exit_px = c[j]; exit_idx = j; reason = "time"; break
        if (j + 1 >= n) or (not openmkt[j+1]):
            exit_px = c[j]; exit_idx = j; reason = "session"; break
        # ratchet trail using this bar's extreme, effective next bar
        if TRAIL > 0 and np.isfinite(atr[j]):
            if s > 0:
                best = max(best, h[j]); st = max(st, best - TRAIL * atr[j])
            else:
                best = min(best, l[j]); st = min(st, best + TRAIL * atr[j])
        j += 1
    gross = (exit_px - entry) * s
    net = gross - COST
    r = net / sd
    trades.append({"entry_time": ts[k], "exit_time": ts[exit_idx], "side": int(s),
                   "entry": entry, "exit": exit_px, "stop_dist": sd,
                   "net": net, "r": r, "reason": reason})
    i = exit_idx + 1

tr = pd.DataFrame(trades)
r = tr["r"].to_numpy()
eq = r.cumsum(); peak = np.maximum.accumulate(eq); ddR = (eq - peak).min()
wins = r[r > 0].sum(); losses = -r[r < 0].sum()
pf = wins / losses if losses > 0 else float("inf")
wr = (r > 0).mean()

def sub(mask, lbl):
    rr = tr.loc[mask, "r"].to_numpy()
    if len(rr) == 0:
        return f"  {lbl:14s} n=0"
    w = rr[rr>0].sum(); lo_ = -rr[rr<0].sum()
    p = w/lo_ if lo_>0 else float('inf')
    return f"  {lbl:14s} n={len(rr):4d} totR={rr.sum():+7.1f} wr={(rr>0).mean():.2f} pf={p:.2f}"

oos = pd.Timestamp("2026-05-01", tz="UTC")
print(f"=== INDEPENDENT REIMPL: VWAP-trend pullback ===")
print(f"  ALL            n={len(tr):4d} totR={r.sum():+7.1f} wr={wr:.3f} pf={pf:.2f} maxddR={ddR:.1f}")
print(sub(tr.entry_time < oos, "IS(Jan-Apr)"))
print(sub(tr.entry_time >= oos, "OOS(May-Jun)"))
print(sub(tr.side > 0, "LONG"))
print(sub(tr.side < 0, "SHORT"))
print("  reasons:", tr["reason"].value_counts().to_dict())
mon = {str(m): round(gg["r"].sum(),1) for m,gg in tr.groupby(tr.entry_time.dt.to_period("M"))}
print("  monthly:", mon)

# daily sharpe on R
daily = tr.set_index("exit_time")["r"].resample("D").sum()
daily = daily[daily != 0]
sharpe = daily.mean()/daily.std()*np.sqrt(252) if daily.std()>0 else 0
print(f"  sharpe(daily): {sharpe:.2f}")
print(f"  open-bar fraction: {openmkt.mean():.3f}  open bars: {openmkt.sum()}")
