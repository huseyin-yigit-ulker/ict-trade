"""MIDAS(XAU) + OPUS(d30so8f3h7 on BTC/ETH/SOL/FET/ARB) — combined 2026 backtest analysis.
Both measured in R (1R = initial risk per trade). R is additive across streams IF each trade risks
the same $ (equal risk-per-trade sizing) — the standard risk-unit portfolio assumption."""
import os, json, urllib.request, urllib.parse, statistics as st
from collections import defaultdict, OrderedDict

def env(k):
    for line in open("/home/ulkerhuseyin1905/ict-trade/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
URL = env("BACKTESTING_VITE_SUPABASE_URL"); KEY = env("BACKTESTING_VITE_SUPABASE_PUBLISHABLE_DEFAULT_KEY")

def fetch(qs):
    req = urllib.request.Request(f"{URL}/rest/v1/trading_signals?{qs}",
        headers={"apikey": KEY, "Authorization": f"Bearer {KEY}", "Accept-Profile": "ict_trade"})
    return json.load(urllib.request.urlopen(req))

sel = "select=symbol,signal_time,exit_time,pnl_r,status&limit=2000"
midas = fetch(f"version=eq.midas&symbol=eq.XAUUSDT&signal_time=gte.2026-01-01&{sel}")
OPUS_SYMS = ["BTCUSDT","ETHUSDT","SOLUSDT","FETUSDT","ARBUSDT"]
opus = fetch(f"version=eq.d30so8f3h7&symbol=in.({','.join(OPUS_SYMS)})&signal_time=gte.2026-01-01&{sel}")
for r in midas: r["stream"] = "MIDAS"
for r in opus:  r["stream"] = "OPUS"
for r in midas + opus: r["r"] = float(r["pnl_r"]) if r.get("pnl_r") is not None else 0.0

def stats(rows):
    rs = [r["r"] for r in rows]; n = len(rs); tot = sum(rs)
    wins = sum(1 for x in rs if x > 0)
    pn = sum(x for x in rs if x > 0); pd_ = -sum(x for x in rs if x < 0)
    pf = pn/pd_ if pd_ > 0 else float("inf")
    return n, tot, (tot/n if n else 0), (wins/n*100 if n else 0), pf

def month(r): return r["signal_time"][:7]

def monthly(rows):
    m = defaultdict(float)
    for r in rows: m[month(r)] += r["r"]
    return m

def maxdd(rows):
    # order by exit_time (when R books); fallback signal_time
    srt = sorted(rows, key=lambda r: (r.get("exit_time") or r["signal_time"]))
    eq = 0.0; peak = 0.0; dd = 0.0
    for r in srt:
        eq += r["r"]; peak = max(peak, eq); dd = min(dd, eq - peak)
    return dd

print("="*74)
print("PER-STREAM (2026)")
print("="*74)
for name, rows in [("MIDAS  (XAU 1m VWAP-trend, FX cost)", midas),
                   ("OPUS   (d30so8f3h7, 5 crypto)", opus)]:
    n, tot, avg, wr, pf = stats(rows)
    print(f"{name:38s} n={n:4d}  totR={tot:+7.1f}  avg={avg:+.3f}  WR={wr:4.0f}%  PF={pf:.2f}  maxDD={maxdd(rows):+.1f}R")

print("\nOPUS per-symbol:")
for s in OPUS_SYMS:
    n, tot, avg, wr, pf = stats([r for r in opus if r["symbol"] == s])
    print(f"  {s:8s} n={n:3d}  totR={tot:+6.1f}  avg={avg:+.3f}  WR={wr:4.0f}%  PF={pf:.2f}")

print("\n" + "="*74)
print("COMBINED PORTFOLIO (MIDAS + OPUS, equal 1R risk/trade)")
print("="*74)
combo = midas + opus
n, tot, avg, wr, pf = stats(combo)
print(f"{'COMBINED':38s} n={n:4d}  totR={tot:+7.1f}  avg={avg:+.3f}  WR={wr:4.0f}%  PF={pf:.2f}  maxDD={maxdd(combo):+.1f}R")

print("\n" + "="*74)
print("MONTHLY R  (diversification: gold vs crypto)")
print("="*74)
mm, mo, mc = monthly(midas), monthly(opus), monthly(combo)
months = sorted(set(mm) | set(mo))
print(f"{'month':8s} {'MIDAS':>8s} {'OPUS':>8s} {'COMBINED':>9s}")
mid_series, opus_series = [], []
for mth in months:
    a, b = mm.get(mth,0), mo.get(mth,0)
    mid_series.append(a); opus_series.append(b)
    print(f"{mth:8s} {a:+8.1f} {b:+8.1f} {a+b:+9.1f}")
print(f"{'TOTAL':8s} {sum(mm.values()):+8.1f} {sum(mo.values()):+8.1f} {sum(mc.values()):+9.1f}")

# correlation of monthly returns
if len(mid_series) >= 3:
    try:
        corr = st.correlation(mid_series, opus_series)
    except Exception:
        corr = float("nan")
    print(f"\nMonthly-return correlation MIDAS vs OPUS: {corr:+.2f}")
    mid_neg = sum(1 for x in mid_series if x < 0); opus_neg = sum(1 for x in opus_series if x < 0)
    combo_neg = sum(1 for a,b in zip(mid_series,opus_series) if a+b < 0)
    print(f"Negative months: MIDAS {mid_neg}/{len(months)}, OPUS {opus_neg}/{len(months)}, COMBINED {combo_neg}/{len(months)}")
