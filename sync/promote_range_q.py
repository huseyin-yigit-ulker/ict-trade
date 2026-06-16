"""Promote the RANGE stream into the high-conviction RANGE+ stream (version='range_q').

range_q is a STRICT SUBSET of version='range' — identical signals, entries, exits and
stored resolution — keeping only the rows whose causal 6-detector ensemble score is NOT
in the loser band [0.20, 0.30) AND whose reward/risk >= 2.0. The SL-pattern study
(range_sl_analysis.py) found that mild-trend band + RR<2 is the loser cluster; excluding
it lifts 2025 OOS from +9.2R to +26.2R while KEEPING the profitable score<0.20 tail that
a plain 0.30 score floor (the first 'range_q' draft) would have discarded.

Because range_q reuses the already-resolved 'range' rows, this needs only LIGHT 4h-kline
fetches (for the per-trade score) — no 1m re-simulation — so it does not trip Binance
rate limits the way a full backfill does. It also guarantees zero resolution drift: each
range_q row is a byte-for-byte copy of its parent range row with version flipped.

Usage:
  python sync/promote_range_q.py --dry-run      # report kept counts + R by year, no write
  python sync/promote_range_q.py --apply        # wipe version='range_q', then insert
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict

import pandas as pd

sys.path.insert(0, "sync")
import trade_sync_common as tsc       # noqa: E402
import regime_ensemble as RE          # noqa: E402

HOUR_MS = 3_600_000
DROP_LO, DROP_HI = 0.20, 0.30         # exclude ensemble score in [LO, HI)
MIN_RR = 2.0
WARMUP_DAYS = 60                      # 4h warmup so the 150-bar window is full at the first trade

# the columns copied verbatim from a 'range' row into the new 'range_q' row (id + version excluded)
COPY_COLS = [
    "symbol", "trade_type", "signal_time", "signal_price", "entry_price", "sl_price",
    "tp_price", "status", "real_entry_time", "exit_time", "exit_price", "pnl_r",
    "created_at", "direction", "strategy", "quality", "confluence_score", "context",
]


def fetch_4h(symbol, start_ms):
    """Light paginated 4h klines start_ms -> now (mirrors backfill_range.fetch_4h)."""
    import json
    import urllib.request
    b = "".join(ch for ch in symbol if ch.isalnum())
    now = int(time.time() * 1000)
    out, frm = [], int(start_ms)
    for _ in range(12):
        url = f"https://fapi.binance.com/fapi/v1/klines?symbol={b}&interval=4h&startTime={frm}&limit=1500"
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                d = json.load(r)
        except Exception as e:
            print(f"    ! 4h fetch {symbol}: {e}", flush=True)
            break
        if not isinstance(d, list) or not d:
            break
        for k in d:
            if not out or int(k[0]) > int(out[-1][0]):
                out.append(k)
        last = int(d[-1][0])
        if len(d) < 1500 or last >= now - RE.FOURH_MS:
            break
        frm = last + 1
    return out


def load_range_rows():
    conn = tsc.backtest_conn(); cur = conn.cursor()
    cur.execute(f"""SELECT id, symbol, signal_time, entry_price, sl_price, tp_price, pnl_r, status
        FROM {tsc.TABLE} WHERE version='range' ORDER BY symbol, signal_time""")
    rows = cur.fetchall(); cur.close(); conn.close()
    return rows


def keep_ids(rows):
    """Return the set of range-row ids that qualify for range_q, plus per-year kept stats."""
    by_sym = defaultdict(list)
    for r in rows:
        by_sym[r[1]].append(r)
    kept, stats = [], defaultdict(lambda: [0, 0, 0.0])   # year -> [kept, resolved, totR]
    drop_band = drop_rr = no_score = 0
    for sym in sorted(by_sym):
        sym_rows = by_sym[sym]
        first_ts = min(r[2] for r in sym_rows)
        start_ms = int((pd.Timestamp(first_ts) - pd.Timedelta(days=WARMUP_DAYS)).timestamp() * 1000)
        kl = fetch_4h(sym, start_ms)
        roll = RE.build_rolling(kl) if len(kl) >= 80 else None
        sk = 0
        for _id, _sym, st, entry, sl, tp, pnl, status in sym_rows:
            fire = int(pd.Timestamp(st).timestamp() * 1000) + HOUR_MS
            sc = RE.score_at(roll, fire) if roll else float("nan")
            risk = abs(float(sl) - float(entry))
            rr = abs(float(tp) - float(entry)) / risk if risk > 0 else 0.0
            if not (isinstance(sc, float) and sc == sc):       # nan score -> can't gate, drop
                no_score += 1; continue
            if DROP_LO <= sc < DROP_HI:
                drop_band += 1; continue
            if rr < MIN_RR:
                drop_rr += 1; continue
            kept.append(_id); sk += 1
            yr = pd.Timestamp(st).year
            stats[yr][0] += 1
            if status in ("closed_tp", "closed_sl") and pnl is not None:
                stats[yr][1] += 1; stats[yr][2] += float(pnl)
        print(f"  {sym:<12} {len(sym_rows):>3} range -> {sk:>3} range_q", flush=True)
        time.sleep(0.4)                                        # courtesy gap (rate-limit safety)
    print(f"\ndropped: band[{DROP_LO},{DROP_HI})={drop_band}  RR<{MIN_RR}={drop_rr}  no-score={no_score}")
    return kept, stats


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    rows = load_range_rows()
    print(f"loaded {len(rows)} 'range' rows\n")
    kept, stats = keep_ids(rows)

    print(f"\n=== range_q (drop score[{DROP_LO},{DROP_HI}) + RR>={MIN_RR}) ===")
    print(f"{'year':>6}{'kept':>7}{'resolved':>10}{'totR':>9}{'avgR':>8}")
    for yr in sorted(stats):
        k, res, r = stats[yr]
        print(f"{yr:>6}{k:>7}{res:>10}{r:>+9.1f}{(r/res if res else 0):>+8.3f}")
    print(f"\nkept {len(kept)} / {len(rows)} range rows")

    if args.dry_run:
        print("[dry-run] no DB write.")
        return

    conn = tsc.backtest_conn(); cur = conn.cursor()
    cur.execute(f"DELETE FROM {tsc.TABLE} WHERE version='range_q'")
    wiped = cur.rowcount
    cols = ", ".join(COPY_COLS)
    cur.execute(
        f"INSERT INTO {tsc.TABLE} ({cols}, version) "
        f"SELECT {cols}, 'range_q' FROM {tsc.TABLE} WHERE version='range' AND id = ANY(%s)",
        (kept,))
    ins = cur.rowcount
    conn.commit(); cur.close(); conn.close()
    print(f"[apply] wiped {wiped} old range_q rows, inserted {ins} new range_q rows.")


if __name__ == "__main__":
    main()
