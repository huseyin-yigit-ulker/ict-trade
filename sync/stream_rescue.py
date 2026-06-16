"""Generalize the range_q rescue method to EVERY stream.

For each version, pull its resolved trades (2026 in-sample + 2025 OOS), recompute the
CAUSAL features that worked for range_q — 6-detector ensemble score, 4h trend direction
+ alignment, reward/risk, risk% — and sweep mechanistically-motivated candidate gates,
reporting 2026 vs 2025 side by side. A gate only "PASSES" if it holds in BOTH years
(in-sample totR>0 AND OOS totR>0 AND OOS avgR>baseline OOS avgR AND n>=30 both years) —
the same discipline that promoted range -> range_q. Either a stream yields an OOS-robust
high-conviction subset, or it is confirmed period-fit (dead).

4h klines are fetched ONCE per symbol (cached across versions) to stay light on Binance.

  python sync/stream_rescue.py
  python sync/stream_rescue.py --versions karma opus v2
"""
import argparse
import json
import math
import sys
import time
import urllib.request
from collections import defaultdict

import pandas as pd

sys.path.insert(0, "sync")
import trade_sync_common as tsc       # noqa: E402
import regime_ensemble as RE          # noqa: E402

HOUR = 3_600_000
TREND_LB = 20                          # 4h bars (~3.3d) for the directional read at the signal bar
FETCH_START = "2024-09-01"             # 4h history start (covers 2025 warmup + direction lookback)
DEF_VERSIONS = ["v1", "v2", "karma", "opus", "v2_light", "kma_light"]
YEARS = [2026, 2025]

_CACHE = {}                            # symbol -> (roll, opens, closes) | None


def fetch4h(sym, start_ms):
    b = "".join(ch for ch in sym if ch.isalnum())
    now = int(time.time() * 1000); out = []; frm = int(start_ms)
    for _ in range(12):
        try:
            d = json.load(urllib.request.urlopen(
                f"https://fapi.binance.com/fapi/v1/klines?symbol={b}&interval=4h&startTime={frm}&limit=1500", timeout=30))
        except Exception as e:
            print(f"    ! 4h {sym}: {e}", flush=True); break
        if not d:
            break
        for k in d:
            if not out or int(k[0]) > int(out[-1][0]):
                out.append(k)
        last = int(d[-1][0])
        if len(d) < 1500 or last >= now - RE.FOURH_MS:
            break
        frm = last + 1
    return out


def cache_symbol(sym):
    if sym in _CACHE:
        return _CACHE[sym]
    start = int(pd.Timestamp(FETCH_START, tz="UTC").timestamp() * 1000)
    kl = fetch4h(sym, start)
    if len(kl) < 80:
        _CACHE[sym] = None
    else:
        _CACHE[sym] = (RE.build_rolling(kl), [int(k[0]) for k in kl], [float(k[4]) for k in kl])
        time.sleep(0.35)               # courtesy gap (rate-limit safety)
    return _CACHE[sym]


def load(version, year):
    conn = tsc.backtest_conn(); cur = conn.cursor()
    cur.execute("""SELECT symbol, signal_time, trade_type, entry_price, sl_price, tp_price, pnl_r, status, confluence_score
        FROM ict_trade.trading_signals WHERE version=%s
          AND signal_time>=%s AND signal_time<%s AND status IN ('closed_tp','closed_sl')""",
                (version, f"{year}-01-01", f"{year+1}-01-01"))
    rows = cur.fetchall(); cur.close(); conn.close()
    return rows


def idx_at(opens, fire_ms):
    lo, hi, idx = 0, len(opens) - 1, -1
    while lo <= hi:
        m = (lo + hi) >> 1
        if opens[m] + RE.FOURH_MS <= fire_ms:
            idx = m; lo = m + 1
        else:
            hi = m - 1
    return idx


def enrich(rows):
    out = []
    for sym, st, tt, entry, sl, tp, pnl, status, conf in rows:
        c = cache_symbol(sym)
        if not c:
            continue
        roll, opens, closes = c
        fire = int(pd.Timestamp(st).timestamp() * 1000) + HOUR
        i = idx_at(opens, fire)
        if i < TREND_LB:
            continue
        score = roll[i][1]
        trend_dir = 1 if closes[i] > closes[i - TREND_LB] else -1
        d = "SHORT" if tt in ("SELL", "SHORT") else "LONG"
        aligned = (d == "SHORT" and trend_dir < 0) or (d == "LONG" and trend_dir > 0)
        rr = abs(float(tp) - float(entry)) / abs(float(sl) - float(entry)) if float(sl) != float(entry) else 0
        risk_pct = abs(float(sl) - float(entry)) / float(entry) * 100
        out.append(dict(sym=sym, dir=d, aligned=aligned,
                        score=score if isinstance(score, float) and math.isfinite(score) else float("nan"),
                        rr=rr, risk_pct=risk_pct, win=(status == "closed_tp"), R=float(pnl)))
    return out


def finite(x):
    return isinstance(x["score"], float) and math.isfinite(x["score"])


GATES = {
    "baseline":                  lambda x: True,
    "RR>=2":                     lambda x: x["rr"] >= 2,
    "RR>=2.5":                   lambda x: x["rr"] >= 2.5,
    "ALIGNED w/4h":              lambda x: x["aligned"],
    "COUNTER 4h":                lambda x: not x["aligned"],
    "score>=0.30 (strong trend)":lambda x: finite(x) and x["score"] >= 0.30,
    "trend verdict>=0.15":       lambda x: finite(x) and x["score"] >= 0.15,
    "range verdict<=-0.15":      lambda x: finite(x) and x["score"] <= -0.15,
    "drop score[0.20,0.30)":     lambda x: not (finite(x) and 0.20 <= x["score"] < 0.30),
    "SHORT only":                lambda x: x["dir"] == "SHORT",
    "LONG only":                 lambda x: x["dir"] == "LONG",
    "risk>=1%":                  lambda x: x["risk_pct"] >= 1,
    "ALIGNED & RR>=2":           lambda x: x["aligned"] and x["rr"] >= 2,
    "score>=0.30 & RR>=2":       lambda x: finite(x) and x["score"] >= 0.30 and x["rr"] >= 2,
    "drop[0.20,0.30) & RR>=2":   lambda x: (not (finite(x) and 0.20 <= x["score"] < 0.30)) and x["rr"] >= 2,
}


def stat(trades):
    n = len(trades); r = sum(t["R"] for t in trades)
    return n, r, (r / n if n else 0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--versions", nargs="*", default=DEF_VERSIONS)
    args = ap.parse_args()

    data = {}
    for v in args.versions:
        data[v] = {y: enrich(load(v, y)) for y in YEARS}

    summary = []
    for v in args.versions:
        d26, d25 = data[v][2026], data[v][2025]
        b26, b25 = stat(d26), stat(d25)
        print(f"\n================ {v}  (2026 n={b26[0]} {b26[1]:+.1f}R · 2025 OOS n={b25[0]} {b25[1]:+.1f}R) ================")
        print(f"  {'gate':<28}{'26 n':>6}{'26 totR':>9}{'26 avgR':>9}   {'25 n':>6}{'25 totR':>9}{'25 avgR':>9}  pass")
        for name, fn in GATES.items():
            a, b = [x for x in d26 if fn(x)], [x for x in d25 if fn(x)]
            n1, r1, a1 = stat(a); n2, r2, a2 = stat(b)
            # PASS: holds in BOTH years (in-sample +, OOS +, OOS avgR beats baseline, sample not tiny)
            ok = (name != "baseline" and r1 > 0 and r2 > 0 and a2 > b25[2] and n1 >= 30 and n2 >= 30)
            print(f"  {name:<28}{n1:>6}{r1:>+9.1f}{a1:>+9.3f}   {n2:>6}{r2:>+9.1f}{a2:>+9.3f}  {'PASS' if ok else ''}")
            if ok:
                summary.append((v, name, r1, r2, n2))

    print("\n================ OOS-ROBUST GATES (positive + improving in BOTH years) ================")
    if not summary:
        print("  none — no stream had a gate that flipped OOS-positive while holding in-sample.")
    for v, name, r1, r2, n2 in sorted(summary, key=lambda s: -s[3]):
        print(f"  {v:<10} {name:<28} 2026 {r1:+.1f}R · 2025 OOS {r2:+.1f}R (n={n2})")


if __name__ == "__main__":
    main()
