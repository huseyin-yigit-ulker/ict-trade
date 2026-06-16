"""Robustness battery for the light+range-verdict subset (the stream_rescue lead).

v2_light / kma_light gated to the ensemble RANGE verdict (score<=-0.15) was OOS-positive
in stream_rescue (v2_light +15.5R, kma_light +11.8R in 2025). The sample is small (~52
resolved/yr), so before building it we ask the questions that matter for a small edge:
is the R spread across MONTHS and SYMBOLS, or carried by a few lucky trades?

Light: 4h klines only (cached per symbol). No 1m, no heavy backfill, no ban risk.

  python sync/validate_light_range.py
"""
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
FETCH_START = "2024-09-01"
RANGE_VERDICT = -0.15                  # ensemble score <= this == RANGE verdict
VERSIONS = ["v2_light", "kma_light"]
_CACHE = {}


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


def roll_for(sym):
    if sym in _CACHE:
        return _CACHE[sym]
    kl = fetch4h(sym, int(pd.Timestamp(FETCH_START, tz="UTC").timestamp() * 1000))
    _CACHE[sym] = RE.build_rolling(kl) if len(kl) >= 80 else None
    time.sleep(0.35)
    return _CACHE[sym]


def load(version):
    conn = tsc.backtest_conn(); cur = conn.cursor()
    cur.execute("""SELECT symbol, signal_time, pnl_r, status
        FROM ict_trade.trading_signals WHERE version=%s
          AND status IN ('closed_tp','closed_sl') ORDER BY signal_time""", (version,))
    rows = cur.fetchall(); cur.close(); conn.close()
    return rows


def kept_trades(version):
    out = []
    for sym, st, pnl, status in load(version):
        roll = roll_for(sym)
        if not roll:
            continue
        sc = RE.score_at(roll, int(pd.Timestamp(st).timestamp() * 1000) + HOUR)
        if isinstance(sc, float) and math.isfinite(sc) and sc <= RANGE_VERDICT:
            out.append(dict(sym=sym, ts=pd.Timestamp(st), R=float(pnl), win=(status == "closed_tp")))
    return out


def report(version, trades):
    n = len(trades); tot = sum(t["R"] for t in trades); w = sum(1 for t in trades if t["win"])
    print(f"\n================ {version} + range-verdict  ({n} resolved, WR {100*w/n if n else 0:.0f}%, {tot:+.1f}R) ================")

    by_m = defaultdict(lambda: [0, 0.0])
    for t in trades:
        m = t["ts"].strftime("%Y-%m"); by_m[m][0] += 1; by_m[m][1] += t["R"]
    pos = sum(1 for m in by_m if by_m[m][1] > 0); neg = sum(1 for m in by_m if by_m[m][1] < 0)
    print(f"  monthly ({pos} up / {neg} down of {len(by_m)} months):")
    for m in sorted(by_m):
        c, r = by_m[m]; bar = ("+" if r >= 0 else "-") * min(int(abs(r)), 30)
        print(f"    {m}  n={c:>2}  {r:>+6.1f}R  {bar}")

    by_s = defaultdict(lambda: [0, 0.0])
    for t in trades:
        by_s[t["sym"]][0] += 1; by_s[t["sym"]][1] += t["R"]
    syms = sorted(by_s, key=lambda s: -by_s[s][1])
    posS = sum(1 for s in by_s if by_s[s][1] > 0)
    print(f"  by symbol ({posS}/{len(by_s)} symbols net-positive):")
    for s in syms:
        c, r = by_s[s]; print(f"    {s:<12} n={c:>2}  {r:>+6.1f}R")
    # concentration: how much of total R comes from the single best symbol / best month
    if tot > 0:
        topS = by_s[syms[0]][1]; topM = max(by_m[m][1] for m in by_m)
        print(f"  concentration: best symbol = {100*topS/tot:.0f}% of totR · best month = {100*topM/tot:.0f}% of totR")


def main():
    for v in VERSIONS:
        report(v, kept_trades(v))


if __name__ == "__main__":
    main()
