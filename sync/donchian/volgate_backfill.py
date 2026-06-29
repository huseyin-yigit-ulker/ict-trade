"""Backtest backfill for the VOLUME-CONTRACTION-GATED d30so8f3h7 twin -> version='d30so8f3vg'.

Same signals + same scale-out exit model as d30so8f3h7 (30m+4h, close_frac 0.3, cap 8R, 7-day
limit, +0.5R confirm), but only TAKES a signal if the symbol's daily volume is CONTRACTING at
signal time (vol[d-K:d] / vol[d-2K:d-K] < THR, no lookahead). The 2024-26 portfolio test showed
this robustly lowers SL-rate + worst-month and lifts WR/PF (at fewer trades). Backtest-only here;
the live dashboard twin emits mode='dch30_4hvg' (canli.py --volume-gate).

    python sync/donchian/volgate_backfill.py --dry-run
    python sync/donchian/volgate_backfill.py --apply
"""
from __future__ import annotations
import sys, os, argparse
from pathlib import Path
_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent)); sys.path.insert(0, str(_HERE.parents[1]))
sys.path.insert(0, str(_HERE.parents[1] / "live_exec"))
os.environ.setdefault("DCH_ENTRY_AT_CONFIRM", "1")
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import _bootenv  # noqa: E402,F401
import portfolio_backfill as pb  # noqa: E402
import trade_sync_common as tsc  # noqa: E402

VERSION = "d30so8f3vg"
THR = 0.9
K = 10
ST = pb.STREAMS["d30so8f3h7"]
W_START = pd.Timestamp("2024-01-01", tz="UTC")

_D = {}
def _vol(sym):
    if sym not in _D:
        d = tsc.fetch_klines(sym, "1d", int(pd.Timestamp("2023-09-01", tz="UTC").timestamp() * 1000),
                             int(pd.Timestamp("2026-06-29", tz="UTC").timestamp() * 1000))
        v = None
        if d is not None and not d.empty:
            v = d["volume"].astype(float); v.index = pd.to_datetime(v.index, utc=True).normalize()
        _D[sym] = v
    return _D[sym]


def _vch(sym, ts):
    v = _vol(sym)
    if v is None:
        return np.nan
    day = pd.Timestamp(ts)
    day = (day.tz_localize("UTC") if day.tz is None else day.tz_convert("UTC")).normalize()
    prior = v.loc[v.index < day]
    if len(prior) < 2 * K:
        return np.nan
    older = prior.iloc[-2 * K:-K].mean()
    return float(prior.iloc[-K:].mean() / older) if older > 0 else np.nan


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true"); g.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    w_end = pd.Timestamp.now(tz="UTC")
    print(f"=== [{VERSION}] gated d30so8f3h7 (vch<{THR}) | {W_START.date()}..{w_end.date()} | "
          f"{len(pb.SYMBOLS)} symbols ===", flush=True)
    events = []
    for sym in pb.SYMBOLS:
        try:
            ev = pb.build_events(sym, ST, W_START, w_end)
            kept = [e for e in ev if (lambda x: not np.isnan(x) and x < THR)(_vch(sym, e["signal_ts"]))]
            events += kept
            if ev:
                print(f"  {sym:<12} {len(kept):>4}/{len(ev)} kept", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {sym}: {type(e).__name__}: {e}", flush=True)
    realized = pb.walk(events, ST, W_START, w_end)
    rows = pb.to_rows(realized, ST)
    for r in rows:
        r["version"] = VERSION                      # override d30so8f3h7 -> gated tag
    closed = [r for r in realized if r["r"] is not None]
    tot = sum(r["r"] for r in closed)
    sl = round(100 * sum(1 for r in closed if r["status"] == "closed_sl") / len(closed)) if closed else 0
    wr = round(100 * sum(1 for r in closed if r["r"] > 0) / len(closed)) if closed else 0
    print(f"\n  -> {len(rows)} rows · closed={len(closed)} · R={tot:+.1f} · WR={wr}% · SLrate={sl}% "
          f"· active={len(realized) - len(closed)}", flush=True)
    if args.apply:
        conn = tsc.backtest_conn(); cur = conn.cursor()
        cur.execute(f"DELETE FROM {tsc.TABLE} WHERE version = %s", (VERSION,))
        deleted = cur.rowcount; conn.commit(); cur.close()
        n = tsc.upsert_rows(conn, rows); conn.close()
        print(f"  [DB] deleted {deleted} old, upserted {n} rows for version='{VERSION}'", flush=True)
    else:
        print(f"  [dry-run] {len(rows)} rows would upsert.", flush=True)


if __name__ == "__main__":
    main()
