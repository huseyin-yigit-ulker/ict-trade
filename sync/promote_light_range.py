"""Promote a LIGHT stream's range-verdict subset into its own stream (the stream_rescue lead).

stream_rescue found that the LIGHT streams (ICT signals already band-passed to 4h ER in
[0.20,0.35)), when ALSO gated to the ensemble RANGE verdict (score <= -0.15), are the only
non-range subset that stays OOS-positive (v2_light +15.5R, kma_light +11.8R in 2025) — the
same character as range_q and consistent with "our ICT set is really a RANGE strategy".
validate_light_range.py confirmed the R is broad across months + symbols (not a few lucky
trades) in BOTH years.

Like promote_range_q, this is a STRICT SUBSET copy of the parent light rows (same signals,
entries, exits, stored resolution) with version flipped — light 4h-only score recompute,
no 1m re-sim, rate-limit-safe, zero resolution drift.

  python sync/promote_light_range.py --dry-run
  python sync/promote_light_range.py --apply --parents v2_light      # writes v2_light_r
"""
import argparse
import math
import sys
import time
from collections import defaultdict

import pandas as pd

sys.path.insert(0, "sync")
import trade_sync_common as tsc       # noqa: E402
import regime_ensemble as RE          # noqa: E402

HOUR_MS = 3_600_000
RANGE_VERDICT = -0.15
FETCH_START = "2024-09-01"
PARENT_MAP = {"v2_light": "v2_light_r", "kma_light": "kma_light_r"}
COPY_COLS = [
    "symbol", "trade_type", "signal_time", "signal_price", "entry_price", "sl_price",
    "tp_price", "status", "real_entry_time", "exit_time", "exit_price", "pnl_r",
    "created_at", "direction", "strategy", "quality", "confluence_score", "context",
]
_CACHE = {}


def fetch4h(sym, start_ms):
    import json
    import urllib.request
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


def kept_ids(parent):
    conn = tsc.backtest_conn(); cur = conn.cursor()
    cur.execute("""SELECT id, symbol, signal_time, pnl_r, status FROM ict_trade.trading_signals
        WHERE version=%s ORDER BY symbol, signal_time""", (parent,))
    rows = cur.fetchall(); cur.close(); conn.close()
    kept, stats, noscore = [], defaultdict(lambda: [0, 0, 0.0]), 0
    for _id, sym, st, pnl, status in rows:
        roll = roll_for(sym)
        if not roll:
            noscore += 1; continue
        sc = RE.score_at(roll, int(pd.Timestamp(st).timestamp() * 1000) + HOUR_MS)
        if not (isinstance(sc, float) and math.isfinite(sc)):
            noscore += 1; continue
        if sc <= RANGE_VERDICT:
            kept.append(_id)
            yr = pd.Timestamp(st).year
            stats[yr][0] += 1
            if status in ("closed_tp", "closed_sl") and pnl is not None:
                stats[yr][1] += 1; stats[yr][2] += float(pnl)
    return rows, kept, stats, noscore


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parents", nargs="*", default=list(PARENT_MAP), choices=list(PARENT_MAP))
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    for parent in args.parents:
        child = PARENT_MAP[parent]
        rows, kept, stats, noscore = kept_ids(parent)
        print(f"\n=== {parent} -> {child}  (range-verdict score<={RANGE_VERDICT}) ===")
        print(f"  {'year':>6}{'kept':>7}{'resolved':>10}{'totR':>9}{'avgR':>8}")
        for yr in sorted(stats):
            k, res, r = stats[yr]
            print(f"  {yr:>6}{k:>7}{res:>10}{r:>+9.1f}{(r/res if res else 0):>+8.3f}")
        print(f"  kept {len(kept)} / {len(rows)} {parent} rows  (no-score skipped: {noscore})")

        if args.apply:
            conn = tsc.backtest_conn(); cur = conn.cursor()
            cur.execute(f"DELETE FROM {tsc.TABLE} WHERE version=%s", (child,))
            wiped = cur.rowcount
            cols = ", ".join(COPY_COLS)
            cur.execute(
                f"INSERT INTO {tsc.TABLE} ({cols}, version) "
                f"SELECT {cols}, %s FROM {tsc.TABLE} WHERE version=%s AND id = ANY(%s)",
                (child, parent, kept))
            ins = cur.rowcount
            conn.commit(); cur.close(); conn.close()
            print(f"  [apply] wiped {wiped} old {child}, inserted {ins} new {child} rows.")
    if args.dry_run:
        print("\n[dry-run] no DB write.")


if __name__ == "__main__":
    main()
