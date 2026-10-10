"""RANGE stream diagnostic — what do the SL trades share, and what extra gate helps?

Pulls the resolved RANGE trades (version='range') for 2026 + 2025, recomputes each
trade's CAUSAL features (ensemble score, 4h trend DIRECTION, session, RR, risk%,
confluence), and tabulates SL-rate + total R by each, to find the common loser
pattern and the best additive gate. Main hypothesis: a range-fade aligned WITH the
4h trend direction wins; counter-trend fades are the SL cluster (the ensemble gate
gives persistence MAGNITUDE but not DIRECTION).
"""
import sys, json, urllib.request, time, math
from collections import defaultdict
sys.path.insert(0, "sync")
import trade_sync_common as tsc
import regime_ensemble as RE
import pandas as pd

HOUR = 3_600_000
TREND_LB = 20   # 4h bars (~3.3 days) for the directional read at the signal bar


def fetch4h(sym, start_ms):
    b = "".join(ch for ch in sym if ch.isalnum())
    now = int(time.time() * 1000); out = []; frm = int(start_ms)
    for _ in range(12):
        try:
            d = json.load(urllib.request.urlopen(
                f"https://fapi.binance.com/fapi/v1/klines?symbol={b}&interval=4h&startTime={frm}&limit=1500", timeout=30))
        except Exception:
            break
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


def load(year):
    conn = tsc.backtest_conn(); cur = conn.cursor()
    cur.execute(f"""SELECT symbol, signal_time, trade_type, entry_price, sl_price, tp_price, pnl_r, status, confluence_score
        FROM {tsc.TABLE} WHERE version='range'
          AND signal_time>=%s AND signal_time<%s AND status IN ('closed_tp','closed_sl')""",
                (f"{year}-01-01", f"{year+1}-01-01"))
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


def enrich(rows, cache):
    out = []
    for sym, st, tt, entry, sl, tp, pnl, status, conf in rows:
        c = cache.get(sym)
        if not c:
            continue
        roll, opens, closes = c
        fire = int(pd.Timestamp(st).timestamp() * 1000) + HOUR
        i = idx_at(opens, fire)
        if i < TREND_LB:
            continue
        score = roll[i][1]
        trend_dir = 1 if closes[i] > closes[i - TREND_LB] else -1   # +1 up, -1 down (4h)
        d = "SHORT" if tt in ("SELL", "SHORT") else "LONG"
        # aligned = fade in the SAME direction as the 4h trend
        aligned = (d == "SHORT" and trend_dir < 0) or (d == "LONG" and trend_dir > 0)
        fire_dt = pd.Timestamp(st) + pd.Timedelta(hours=1)
        rr = abs(float(tp) - float(entry)) / abs(float(sl) - float(entry)) if float(sl) != float(entry) else 0
        risk_pct = abs(float(sl) - float(entry)) / float(entry) * 100
        out.append(dict(sym=sym, dir=d, score=score if isinstance(score, float) and math.isfinite(score) else 0,
                        trend_dir=trend_dir, aligned=aligned, hour=fire_dt.hour, wd=fire_dt.dayofweek,
                        conf=int(conf) if conf is not None else 0, rr=rr, risk_pct=risk_pct,
                        win=(status == "closed_tp"), R=float(pnl)))
    return out


def grp(trades, keyfn, label):
    g = defaultdict(lambda: [0, 0, 0.0])   # n, sl, totR
    for t in trades:
        k = keyfn(t)
        g[k][0] += 1
        g[k][1] += 0 if t["win"] else 1
        g[k][2] += t["R"]
    print(f"  by {label}:")
    for k in sorted(g):
        n, sl, R = g[k]
        print(f"    {str(k):<16} n={n:>3}  SL%={sl/n*100:3.0f}  totR={R:+6.1f}  avgR={R/n:+.3f}")


def main():
    data = {}
    for yr in (2026, 2025):
        rows = load(yr)
        syms = sorted({r[0] for r in rows})
        cache = {}
        for s in syms:
            kl = fetch4h(s, int(pd.Timestamp(f"{yr-1}-09-01", tz="UTC").timestamp() * 1000))
            if len(kl) < 80:
                cache[s] = None; continue
            cache[s] = (RE.build_rolling(kl), [int(k[0]) for k in kl], [float(k[4]) for k in kl])
        data[yr] = enrich(rows, cache)
        print(f"\n================ RANGE {yr}: {len(data[yr])} resolved trades ================")
        t = data[yr]
        tot = sum(x["R"] for x in t); sl = sum(1 for x in t if not x["win"])
        print(f"  overall: SL%={sl/len(t)*100:.0f}  totR={tot:+.1f}  avgR={tot/len(t):+.3f}")
        grp(t, lambda x: ("ALIGNED" if x["aligned"] else "COUNTER"), "trend alignment (fade vs 4h dir)")
        grp(t, lambda x: x["dir"], "direction")
        grp(t, lambda x: ("score<0.20" if x["score"] < 0.20 else "0.20-0.30" if x["score"] < 0.30 else "score>=0.30"), "ensemble score")
        grp(t, lambda x: f"conf{x['conf']}", "confluence (9=swept)")
        grp(t, lambda x: ("RR<2" if x["rr"] < 2 else "RR>=2"), "reward/risk")
        grp(t, lambda x: ("risk<1%" if x["risk_pct"] < 1 else "risk1-2%" if x["risk_pct"] < 2 else "risk>=2%"), "risk size")
        grp(t, lambda x: ("wknd" if x["wd"] >= 5 else "weekday"), "weekend?")

    # candidate additive gates — must improve/hold in BOTH years (2026 in-sample, 2025 OOS)
    GATES = {
        "baseline (all)":          lambda x: True,
        "RR>=2":                   lambda x: x["rr"] >= 2,
        "score>=0.30":             lambda x: x["score"] >= 0.30,
        "RR>=2 & score>=0.30":     lambda x: x["rr"] >= 2 and x["score"] >= 0.30,
        "drop score 0.20-0.30":    lambda x: not (0.20 <= x["score"] < 0.30),
        "RR>=2 & drop 0.20-0.30":  lambda x: x["rr"] >= 2 and not (0.20 <= x["score"] < 0.30),
        "SHORT only":              lambda x: x["dir"] == "SHORT",
        "risk>=1%":                lambda x: x["risk_pct"] >= 1,
    }
    print("\n================ CANDIDATE GATES — 2026 (in-sample) vs 2025 (OOS) ================")
    print(f"  {'gate':<26}{'2026 n':>7}{'totR':>8}{'avgR':>7}   {'2025 n':>7}{'totR':>8}{'avgR':>7}")
    for name, fn in GATES.items():
        a = [x for x in data[2026] if fn(x)]; b = [x for x in data[2025] if fn(x)]
        def s(t):
            return (len(t), sum(x["R"] for x in t), sum(x["R"] for x in t) / len(t) if t else 0)
        n1, r1, a1 = s(a); n2, r2, a2 = s(b)
        print(f"  {name:<26}{n1:>7}{r1:>+8.1f}{a1:>+7.3f}   {n2:>7}{r2:>+8.1f}{a2:>+7.3f}")


if __name__ == "__main__":
    main()
