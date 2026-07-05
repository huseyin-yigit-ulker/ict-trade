"""Parameter sweep for the supply/demand video strategy. Caches klines (1h/15m/1m) ONCE per
symbol+window, then runs many configs by mutating module globals. Reports 2026 + an OOS check
on the winner. One-factor-at-a-time around the baseline, plus the min-risk fee-floor."""
import os, sys
os.environ.setdefault("ENTRY_AT_CONFIRM", "1"); os.environ.setdefault("ENTRY_CONFIRM_BUF", "0.5")
sys.path.insert(0, "sync"); sys.path.insert(0, "sync/donchian"); sys.path.insert(0, "sync/live_exec")
sys.path.insert(0, "scratchpad")
import pandas as pd, numpy as np
import supdem_video_bt as b
import trade_sync_common as tsc

# ---- memoizing kline cache so a sweep doesn't re-fetch 1m every config ----
_orig = tsc.fetch_klines
_CACHE = {}
def _cached(sym, tf, s_ms, e_ms):
    k = (sym, tf, s_ms, e_ms)
    if k not in _CACHE:
        _CACHE[k] = _orig(sym, tf, s_ms, e_ms)
    return _CACHE[k]
tsc.fetch_klines = _cached
b.tsc.fetch_klines = _cached

BASE = dict(IMPULSE_N=3, IMP_ATR=1.0, EMA_LEN=8, RR_MIN=1.5, RR_MAX=6.0, RR_DEF=2.5,
            SL_BUF_ATR=0.1, MIN_RISK_PCT=0.0)


def apply(cfg):
    for k, v in {**BASE, **cfg}.items():
        setattr(b, k, v)


def metrics(start, end):
    all_ev = []
    sig_n = 0
    for sym in b.SYMBOLS:
        sigs = b.signals_for_symbol(sym, start, end)
        sig_n += len(sigs)
        if not sigs:
            continue
        m1end = end + pd.Timedelta(days=15)        # fixed (no now()) -> stable cache key
        df1m = tsc.fetch_klines(sym, "1m", int((start - pd.Timedelta(days=2)).timestamp() * 1000),
                                int(m1end.timestamp() * 1000))
        if df1m is None or df1m.empty:
            continue
        all_ev += b.build_events(sym, sigs, df1m, end)
    realized = b.walk(all_ev, max_concurrent=len(b.SYMBOLS))
    closed = [r for r in realized if r["r"] is not None]
    R = np.array([r["r"] for r in closed]) if closed else np.array([0.0])
    tot = R.sum(); wr = 100 * (R > 0).mean(); avg = R.mean()
    gp = R[R > 0].sum(); gl = -R[R < 0].sum(); pf = gp / gl if gl > 0 else float("inf")
    bym = {}
    for r in closed:
        m = pd.Timestamp(r["exit"]).strftime("%Y-%m"); bym.setdefault(m, 0.0); bym[m] += r["r"]
    worst = min(bym.values()) if bym else 0.0
    neg = sum(1 for v in bym.values() if v < 0)
    return dict(n=len(closed), R=tot, WR=wr, avgR=avg, PF=pf, worst=worst, negM=neg, nM=len(bym), maxLoss=R.min())


def line(tag, m):
    print(f"  {tag:22} n={m['n']:3} R={m['R']:+7.1f} WR={m['WR']:4.1f}% avgR={m['avgR']:+.2f} "
          f"PF={m['PF']:.2f} worstMo={m['worst']:+.1f} neg={m['negM']}/{m['nM']} maxL={m['maxLoss']:+.1f}",
          flush=True)


S26, E26 = pd.Timestamp("2026-01-01", tz="UTC"), pd.Timestamp("2026-06-22", tz="UTC")
b.SYMBOLS = ["BTCUSDT", "ETHUSDT", "XAUUSDT", "XAGUSDT"]

print("=== 2026 SWEEP (one-factor-at-a-time around baseline) ===", flush=True)
SWEEP = [
    ("baseline", {}),
    ("min_risk 0.20%", {"MIN_RISK_PCT": 0.0020}),
    ("min_risk 0.30%", {"MIN_RISK_PCT": 0.0030}),
    ("min_risk 0.50%", {"MIN_RISK_PCT": 0.0050}),
    ("impulse_N 4", {"IMPULSE_N": 4}),
    ("imp_ATR 0.75", {"IMP_ATR": 0.75}),
    ("imp_ATR 1.5", {"IMP_ATR": 1.5}),
    ("imp_ATR 2.0", {"IMP_ATR": 2.0}),
    ("EMA 9", {"EMA_LEN": 9}),
    ("EMA 21", {"EMA_LEN": 21}),
    ("RR_MAX 4", {"RR_MAX": 4.0}),
    ("RR_MAX 8", {"RR_MAX": 8.0}),
    ("RR_DEF 2.0", {"RR_DEF": 2.0}),
    ("SL_buf 0.25", {"SL_BUF_ATR": 0.25}),
    # combo: fee-floor + stronger impulse
    ("floor.3+impATR1.5", {"MIN_RISK_PCT": 0.0030, "IMP_ATR": 1.5}),
    ("floor.3+RRmax8", {"MIN_RISK_PCT": 0.0030, "RR_MAX": 8.0}),
]
results = {}
for tag, cfg in SWEEP:
    apply(cfg)
    m = metrics(S26, E26)
    results[tag] = (cfg, m)
    line(tag, m)

# pick winner by R with a sanity guard (PF>1.3, worst month not catastrophic)
ok = {t: v for t, v in results.items() if v[1]["PF"] > 1.3}
winner = max(ok or results, key=lambda t: results[t][1]["R"])
print(f"\n=== WINNER (2026): {winner} -> OOS CHECK ===", flush=True)
wcfg = results[winner][0]
apply(wcfg)
for yr, (s, e, syms) in {
    "2025": (pd.Timestamp("2025-01-01", tz="UTC"), pd.Timestamp("2026-01-01", tz="UTC"), ["BTCUSDT", "ETHUSDT", "XAUUSDT"]),
    "2024": (pd.Timestamp("2024-01-01", tz="UTC"), pd.Timestamp("2025-01-01", tz="UTC"), ["BTCUSDT", "ETHUSDT"]),
}.items():
    b.SYMBOLS = syms
    line(f"{winner}@{yr}", metrics(s, e))
    b.SYMBOLS = ["BTCUSDT", "ETHUSDT", "XAUUSDT", "XAGUSDT"]
print("\n(baseline OOS was: 2025 +175.0 / 2024 +151.6)")
