"""RANGE / RANGE+ gated by the 6-detector ensemble computed on 1h klines (not 4h).

The production RANGE stream computes its regime ENSEMBLE on 4h bars (window=150 4h ≈
25 days). This builds two parallel variants that gate the SAME RANGE_DEV signals by the
ensemble computed on 1h bars (window=150 1h ≈ 6 days) — a finer-timeframe regime read,
across the full RANGE universe for 2026:

  range_1h   : RANGE_DEV, 1h-ensemble verdict == trend, full-TP   (mirror of 'range')
  rangeq_1h  : range_1h further filtered: drop 1h-score [0.20,0.30) + reward/risk >= 2
               (mirror of 'range_q' via promote_range_q, but on the 1h score)

Signals + their full-TP outcomes are gate-independent, so we generate + resolve once per
symbol and apply both 1h gates. Causal: the 1h score at a signal uses 1h bars up to that
signal's own bar close (= fire time), no look-ahead. 1m resolution reuses the cached
/tmp/range1m_cache/{sym}.pkl frames when present (fetches + caches otherwise).

  python sync/backfill_range_1h.py --dry-run            # report per-symbol + totals, no write
  python sync/backfill_range_1h.py --apply              # wipe versions range_1h/rangeq_1h, write
  python sync/backfill_range_1h.py --apply --symbols BTCUSDT ETHUSDT
"""
from __future__ import annotations
import sys
import math
import pickle
import argparse
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trade_sync_common as tsc
import regime_ensemble as RE
from burak_strategy import generate_signals
from ict import config as C
from backfill_range import SYMBOLS as RANGE_SYMBOLS

W_START = pd.Timestamp("2026-01-01", tz="UTC")
NOW = pd.Timestamp.now(tz="UTC")
W_END = min(pd.Timestamp("2027-01-01", tz="UTC"), NOW)
DROP_LO, DROP_HI, MIN_RR = 0.20, 0.30, 2.0     # mirror promote_range_q
V_RANGE_1H, V_RANGEQ_1H = "range_1h", "rangeq_1h"
CACHE = Path("/tmp/range1m_cache")


def fin(x):
    return isinstance(x, float) and math.isfinite(x)


def load_1m(sym):
    cf = CACHE / f"{sym}.pkl"
    if cf.exists():
        return pickle.loads(cf.read_bytes())
    df = tsc.fetch_1m(sym, W_START - pd.Timedelta(hours=2), NOW)
    if df is not None and not df.empty:
        CACHE.mkdir(exist_ok=True)
        cf.write_bytes(pickle.dumps(df))
    return df


def run_symbol(sym):
    """Return (recs, keep_r, keep_q) for one symbol; recs = (sig, score, verdict, rr, res)."""
    df = tsc.fetch_1h(sym, W_START - pd.Timedelta(hours=2200), NOW)
    if df is None or df.empty:
        print(f"  {sym:<12} SKIP (no 1h)", flush=True)
        return [], [], []
    sigs = [s for s in generate_signals(df)
            if s.strategy == "RANGE_DEV" and W_START <= s.timestamp < W_END]
    if not sigs:
        print(f"  {sym:<12} 0 RANGE_DEV", flush=True)
        return [], [], []
    kl = [[int(ts.timestamp() * 1000), float(r.open), float(r.high), float(r.low), float(r.close)]
          for ts, r in df.iterrows()]
    opens = [k[0] for k in kl]
    open_idx = {o: i for i, o in enumerate(opens)}

    def score_1h(sig_ms):
        idx = open_idx.get(sig_ms)
        if idx is None:
            lo, hi = 0, len(opens) - 1
            while lo <= hi:
                m = (lo + hi) >> 1
                if opens[m] <= sig_ms:
                    idx = m; lo = m + 1
                else:
                    hi = m - 1
            if idx is None:
                return float("nan")
        return RE.compute_score(kl[:idx + 1])

    df1m = load_1m(sym)
    if df1m is None or df1m.empty:
        print(f"  {sym:<12} SKIP (no 1m)", flush=True)
        return [], [], []
    prev = C.PARTIAL_TP_ENABLED
    C.PARTIAL_TP_ENABLED = False
    recs = []
    try:
        for s in sigs:
            sc = score_1h(int(s.timestamp.timestamp() * 1000))
            v = RE.verdict(sc)
            risk = abs(s.entry - s.stop_loss)
            rr = abs(s.take_profit_1 - s.entry) / risk if risk > 0 else 0.0
            res = tsc.simulate(sym, s.timestamp, s.direction, s.entry, s.stop_loss,
                               s.take_profit_1, df1m=df1m, expiry_minutes=s.expiry_minutes)
            recs.append((s, sc, v, rr, res))
    finally:
        C.PARTIAL_TP_ENABLED = prev
    keep_r = [r for r in recs if r[2] == "trend"]
    keep_q = [r for r in keep_r if fin(r[1]) and not (DROP_LO <= r[1] < DROP_HI) and r[3] >= MIN_RR]
    rr_n, rr_r = totR(keep_r)
    rq_n, rq_r = totR(keep_q)
    print(f"  {sym:<12} {len(sigs):>3} RANGE_DEV -> 1h: range_1h {rr_n:>2}={rr_r:+6.1f}R  "
          f"rangeq_1h {rq_n:>2}={rq_r:+6.1f}R", flush=True)
    return recs, keep_r, keep_q


def totR(kept):
    res = [r for r in kept if r[4]["status"] in ("closed_tp", "closed_sl") and r[4]["pnl_r"] is not None]
    return len(res), sum(float(r[4]["pnl_r"]) for r in res)


def rows_for(sym_kept, version):
    out = []
    for sym, kept in sym_kept:
        for (s, _sc, _v, _rr, res) in kept:
            row = tsc.build_row(sym, s.timestamp, s.direction, s.entry, s.stop_loss,
                                s.take_profit_1, res, strategy=s.strategy,
                                quality=s.quality, confluence_score=s.confluence_score)
            row["version"] = version
            out.append(row)
    return out


def summary(name, sym_kept):
    n = r = w = 0
    for _sym, kept in sym_kept:
        for rec in kept:
            res = rec[4]
            if res["status"] in ("closed_tp", "closed_sl") and res["pnl_r"] is not None:
                n += 1; r += float(res["pnl_r"]); w += res["status"] == "closed_tp"
    print(f"  {name:<11} resolved={n:>4}  WR={100*w/n if n else 0:.0f}%  totR={r:+.1f}")
    return n, r


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    ap.add_argument("--symbols", nargs="*", default=RANGE_SYMBOLS)
    args = ap.parse_args()

    print(f"=== RANGE 1h-regime backfill 2026 | {len(args.symbols)} symbols ===", flush=True)
    range_keep, rangeq_keep = [], []
    for sym in args.symbols:
        try:
            _recs, kr, kq = run_symbol(sym)
            if kr:
                range_keep.append((sym, kr))
            if kq:
                rangeq_keep.append((sym, kq))
        except Exception as e:
            print(f"  ! {sym}: {e}", flush=True)

    print("\n=== TOTALS (1h regime, 2026) ===")
    summary("range_1h", range_keep)
    summary("rangeq_1h", rangeq_keep)
    print("  (4h baselines for ref: range +41.6R book / range_q higher-conviction subset)")

    if args.dry_run:
        print("\n[dry-run] no DB write.")
        return

    r_rows = rows_for(range_keep, V_RANGE_1H)
    q_rows = rows_for(rangeq_keep, V_RANGEQ_1H)
    conn = tsc.backtest_conn(); cur = conn.cursor()
    for version in (V_RANGE_1H, V_RANGEQ_1H):
        cur.execute(f"DELETE FROM {tsc.TABLE} WHERE version=%s", (version,))
        print(f"  wiped {cur.rowcount} existing {version} rows")
    conn.commit(); cur.close()
    n1 = tsc.upsert_rows(conn, r_rows)
    n2 = tsc.upsert_rows(conn, q_rows)
    conn.close()
    print(f"\nupserted {n1} '{V_RANGE_1H}' + {n2} '{V_RANGEQ_1H}' rows")


if __name__ == "__main__":
    main()
