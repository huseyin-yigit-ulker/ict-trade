"""A/B harness: full-TP vs ½TP+breakeven exit on the CURRENT RANGE stream (2026).

The RANGE signals (version='range' — Burak RANGE_DEV, ensemble TREND-gated) are
identical regardless of exit model (the partial logic only changes what happens AFTER
entry fills), so we pull the production signal set straight from the DB and re-resolve
EACH signal on 1m TWICE on the SAME 1m window: once full-TP (PARTIAL_TP_ENABLED=False)
and once ½TP+BE (True). Only the exit model varies. Reports resolved win% / avg R /
total R + monthly, so we can decide whether a 'range_half' module is worth shipping.

The existing strategyInfo claims ½TP sinks RANGE_DEV (+37R -> -11R) — but that predates
the ensemble TREND gate, so this re-measures it on the current gated set.

Robust to Binance rate-limits: 1m is fetched per-symbol over the whole 2026 window
ONCE, rate-limited + 418/429 backoff, and CACHED to /tmp/range1m_cache/{sym}.pkl so a
re-run resumes instantly. Resolution then runs in-memory.

    python sync/experiment_range_partial.py
"""
from __future__ import annotations
import sys
import time
import pickle
from pathlib import Path
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trade_sync_common as tsc
from ict import config as C

WIN_START = pd.Timestamp("2026-01-01", tz="UTC")
NOW = pd.Timestamp.now(tz="UTC")
CACHE = Path("/tmp/range1m_cache"); CACHE.mkdir(exist_ok=True)
FAPI = "https://fapi.binance.com/fapi/v1/klines"
COLS = ["open", "high", "low", "close", "volume"]


def fetch_1m_cached(sym, start, end):
    """Whole-window 1m with rate-limit + 418/429 backoff, cached to disk (resumable)."""
    cf = CACHE / f"{sym}.pkl"
    if cf.exists():
        return pickle.loads(cf.read_bytes())
    rows = []; cur = int(start.timestamp() * 1000); endms = int(end.timestamp() * 1000)
    while cur < endms:
        params = {"symbol": sym, "interval": "1m", "startTime": cur, "endTime": endms, "limit": 1500}
        data = None
        for attempt in range(12):
            try:
                r = requests.get(FAPI, params=params, timeout=25)
                if r.status_code in (418, 429):
                    wait = int(r.headers.get("Retry-After", "0") or 0) or min(300, 45 * (attempt + 1))
                    print(f"   {sym} {r.status_code} backoff {wait}s", flush=True); time.sleep(wait); continue
                r.raise_for_status(); data = r.json(); break
            except requests.exceptions.RequestException as e:
                w = min(300, 45 * (attempt + 1)); print(f"   {sym} err {e}; sleep {w}s", flush=True); time.sleep(w)
        if not data:
            break
        rows.extend(data)
        if len(data) < 1500:
            break
        cur = data[-1][0] + 1; time.sleep(0.45)
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume", "_c", "_q", "_t", "_a", "_b", "_i"])
    df["timestamp"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("timestamp")[COLS].astype(float)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    cf.write_bytes(pickle.dumps(df))
    return df


def pull_signals():
    conn = tsc.backtest_conn(); cur = conn.cursor()
    cur.execute(f"""
        SELECT symbol, signal_time, direction, entry_price, sl_price, tp_price, pnl_r, status
        FROM {tsc.TABLE} WHERE version = 'range' AND signal_time >= %s ORDER BY signal_time
    """, (WIN_START.strftime("%Y-%m-%d"),))
    rows = cur.fetchall(); cur.close(); conn.close()
    return rows


def stats(pnls):
    n = len(pnls); wins = sum(1 for r in pnls if r > 0); total = sum(pnls)
    return n, (100 * wins / n if n else 0.0), (total / n if n else 0.0), total


def main():
    sigs = pull_signals()
    by_sym = {}
    for s in sigs:
        by_sym.setdefault(s[0], []).append(s)
    print(f"pulled {len(sigs)} range signals over {len(by_sym)} symbols (>= {WIN_START.date()})", flush=True)

    full, half, full_m, half_m, db_sum, resolved = [], [], {}, {}, 0.0, 0
    for si, (sym, rows) in enumerate(by_sym.items(), 1):
        df1m = fetch_1m_cached(sym, WIN_START - pd.Timedelta(hours=2), NOW)
        if df1m is None or df1m.empty:
            print(f"  [{si}/{len(by_sym)}] {sym}: NO 1m data", flush=True); continue
        for (_s, ts, direction, entry, sl, tp, db_pnl, db_status) in rows:
            ts = pd.Timestamp(ts)
            if ts.tz is None:
                ts = ts.tz_localize("UTC")
            if db_pnl is not None and db_status in ("closed_tp", "closed_sl"):
                db_sum += float(db_pnl)
            C.PARTIAL_TP_ENABLED = False
            of = tsc.simulate(sym, ts, direction, entry, sl, tp, df1m=df1m)
            C.PARTIAL_TP_ENABLED = True
            oh = tsc.simulate(sym, ts, direction, entry, sl, tp, df1m=df1m)
            m = ts.strftime("%Y-%m")
            if of["raw_status"] in ("tp_hit", "sl_hit") and of["pnl_r"] is not None:
                full.append(of["pnl_r"]); full_m[m] = full_m.get(m, 0.0) + of["pnl_r"]
            if oh["raw_status"] in ("tp_hit", "sl_hit") and oh["pnl_r"] is not None:
                half.append(oh["pnl_r"]); half_m[m] = half_m.get(m, 0.0) + oh["pnl_r"]
            resolved += 1
        print(f"  [{si}/{len(by_sym)}] {sym}: {len(rows)} sigs done (full so far {sum(full):+.1f}R)", flush=True)

    C.PARTIAL_TP_ENABLED = False
    fn, fw, fa, ft = stats(full); pn, pw, pa, pt = stats(half)
    print(f"\nresolved {resolved} signals · DB full-TP stored sum (closed) = {db_sum:+.1f}R (cross-check)")
    print("\n=== RANGE 2026 EXIT-MODEL A/B (same signals, same 1m) ===")
    print(f'{"model":<26}{"trd":>5}{"win%":>7}{"avgR":>8}{"totR":>9}')
    print(f'{"  full-TP (current)":<26}{fn:>5}{fw:>7.1f}{fa:>8.3f}{ft:>9.1f}')
    print(f'{"  ½TP + breakeven":<26}{pn:>5}{pw:>7.1f}{pa:>8.3f}{pt:>9.1f}')
    print(f'{"  -> delta totR":<26}{"":>5}{"":>7}{"":>8}{pt - ft:>+9.1f}')
    print("\n--- monthly totR: full -> ½TP (delta) ---")
    for m in sorted(set(full_m) | set(half_m)):
        c, p = full_m.get(m, 0.0), half_m.get(m, 0.0)
        print(f"    {m}   {c:>7.1f} -> {p:>7.1f}   ({p - c:>+6.1f})")


if __name__ == "__main__":
    main()
