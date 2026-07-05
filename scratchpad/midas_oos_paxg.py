"""MIDAS OOS on 2024 + 2025 via PAXGUSDT (Pax Gold, 1 token = 1oz) — Binance SPOT, real volume.
Binance XAUUSDT 1m only exists from 2025-12-11, so PAXG is the reliable gold proxy for 2024/2025.
Method: reuse the SHIPPED engine (signals/walk/add_market_open/atr/vwap) unchanged; only the data
source is PAXGUSDT spot. First VALIDATE on 2026 (PAXG vs the XAUUSDT +145R book), then run 2024/2025.
"""
import sys, os, time, json, pickle, urllib.request
import pandas as pd, numpy as np
sys.path.insert(0, "sync/midas")
import strategy as M

CACHE = "scratchpad/paxg_cache"; os.makedirs(CACHE, exist_ok=True)
SYMBOL = "PAXGUSDT"; FX_COST = M.COST_RT  # $0.50/oz round-trip, same as the shipped MIDAS

# --- extend the US-market holiday calendar to 2024 + 2025 (mirror the 2026 FULL/EARLY structure:
#     gold trades a shortened session on 'stock' holidays, full-closes only Jan1/GoodFri/Dec25). ---
M.HOLIDAY_FULL_ET = M.HOLIDAY_FULL_ET + (
    "2024-01-01", "2024-03-29", "2024-12-25",
    "2025-01-01", "2025-04-18", "2025-12-25")
M.HOLIDAY_EARLY_ET = M.HOLIDAY_EARLY_ET + (
    "2024-01-15", "2024-02-19", "2024-05-27", "2024-06-19", "2024-07-03",
    "2024-09-02", "2024-11-28", "2024-11-29", "2024-12-24",
    "2025-01-20", "2025-02-17", "2025-05-26", "2025-06-19", "2025-07-03",
    "2025-09-01", "2025-11-27", "2025-11-28", "2025-12-24")

def fetch_spot_1m(start_ms, end_ms):
    """Paginated Binance SPOT 1m klines -> tz-aware UTC df[open,high,low,close,volume]."""
    rows = []; cur = start_ms
    while cur < end_ms:
        u = (f"https://api.binance.com/api/v3/klines?symbol={SYMBOL}&interval=1m"
             f"&startTime={cur}&endTime={end_ms}&limit=1000")
        for attempt in range(4):
            try:
                d = json.load(urllib.request.urlopen(u, timeout=25)); break
            except Exception as e:
                if attempt == 3: raise
                time.sleep(1.5)
        if not d: break
        rows.extend(d)
        nxt = d[-1][0] + 60_000
        if nxt <= cur: break
        cur = nxt
        if len(rows) % 50000 < 1000: print(f"    ... {len(rows)} bars", flush=True)
        time.sleep(0.12)  # gentle on the rate limit
    if not rows: return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["t","open","high","low","close","volume","ct","qv","n","tb","tq","ig"])
    df = df[["t","open","high","low","close","volume"]].astype({"open":float,"high":float,"low":float,"close":float,"volume":float})
    df.index = pd.to_datetime(df["t"], unit="ms", utc=True)
    return df[["open","high","low","close","volume"]][~df.index.duplicated()]

def load_paxg(start, end):
    key = f"{CACHE}/{SYMBOL}_{start.date()}_{end.date()}.pkl"
    if os.path.exists(key):
        return pickle.load(open(key, "rb"))
    print(f"  fetching {SYMBOL} {start.date()}..{end.date()} from Binance spot ...", flush=True)
    df = fetch_spot_1m(int(start.timestamp()*1000), int(end.timestamp()*1000))
    pickle.dump(df, open(key, "wb"))
    return df

def run_period(label, start, end):
    warm = start - pd.Timedelta(days=2)
    df = load_paxg(warm, end)
    if df.empty: print(f"{label}: NO DATA"); return None
    df = df.loc[(df.index >= warm) & (df.index < end)]
    df = M.add_market_open(df)
    atr = M.atr_tf(df)
    side, stop = M.signals(df, atr)
    trades = [t for t in M.walk(df, side, stop, atr.to_numpy(), cost=FX_COST) if t.entry_time >= start]
    rs = [t.pnl_r for t in trades]; n = len(rs); tot = sum(rs)
    wins = sum(1 for x in rs if x > 0)
    pn = sum(x for x in rs if x > 0); pdn = -sum(x for x in rs if x < 0)
    pf = pn/pdn if pdn > 0 else float("inf")
    # monthly + maxDD (by exit time)
    mon = {}
    for t in trades: mon[str(t.exit_time)[:7]] = mon.get(str(t.exit_time)[:7], 0) + t.pnl_r
    eq = peak = dd = 0.0
    for t in sorted(trades, key=lambda x: x.exit_time):
        eq += t.pnl_r; peak = max(peak, eq); dd = min(dd, eq-peak)
    print(f"\n{'='*68}\n{label}   bars={len(df)}  ({df.index[0]} .. {df.index[-1]})\n{'='*68}")
    print(f"  n={n}  totR={tot:+.1f}  avg={tot/n if n else 0:+.3f}  WR={wins/n*100 if n else 0:.0f}%  PF={pf:.2f}  maxDD={dd:+.1f}R")
    print("  monthly:", "  ".join(f"{k}:{v:+.0f}" for k,v in sorted(mon.items())))
    return dict(label=label, n=n, tot=tot, pf=pf, wr=(wins/n*100 if n else 0), dd=dd)

if __name__ == "__main__":
    res = []
    # 1) VALIDATION: 2026 overlap — must roughly reproduce the XAUUSDT book (+145R / PF1.68 / 389tr)
    res.append(run_period("VALIDATION 2026 (PAXG vs XAU book +145R)", pd.Timestamp("2026-01-01",tz="UTC"), pd.Timestamp("2026-07-02",tz="UTC")))
    # 2) OOS
    res.append(run_period("OOS 2025", pd.Timestamp("2025-01-01",tz="UTC"), pd.Timestamp("2026-01-01",tz="UTC")))
    res.append(run_period("OOS 2024", pd.Timestamp("2024-01-01",tz="UTC"), pd.Timestamp("2025-01-01",tz="UTC")))
    print(f"\n\n{'='*68}\nSUMMARY\n{'='*68}")
    for r in res:
        if r: print(f"  {r['label']:44s} n={r['n']:4d}  totR={r['tot']:+7.1f}  PF={r['pf']:.2f}  WR={r['wr']:.0f}%  maxDD={r['dd']:+.1f}R")
