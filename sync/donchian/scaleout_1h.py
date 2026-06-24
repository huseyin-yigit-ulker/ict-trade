"""Donchian 1h SCALE-OUT stream — the 1h sibling of scaleout.py. versions d1h_so{4,6,8}c.

Same scale-out + breakeven-runner mechanic as the 30m+4h stream (scaleout.py), but the
ENTRY is the plain 1h Donchian(55) breakout (ER>=0.35 gated, NO 4h-direction confirm) — i.e.
the exact entry of the `donchian` (1h) base stream, just resolved under the high-WR scale-out
exit instead of the full-TP exit. The 30m+4h stream uses a 4h-direction gate; the 1h stream
uses its own-TF ER gate (donchianc), so this is the 1h family's scale-out twin.

Mechanic (identical to scaleout.resolve_scaleout, reused verbatim):
  entry = 1h breakout (+0.5R confirmation fill), risk = 2*ATR (stop = -1R)
  * FIRST target +1R: close 60% (CLOSE_FRAC) -> sets the WR, runner stop -> breakeven
  * RUNNER (40%) exits at the FIRST of: +RUNNER_CAP R / breakeven / 3-day mark-to-market
RUNNER_CAP is the only knob: 4R / 6R / 8R -> versions d1h_so4c / d1h_so6c / d1h_so8c.

Naming (deliberately explicit so it never collides with the 30m+4h 'd30so*' family):
  d1h_so<cap>c   d1h = donchian 1h | so = scale-out | <cap> = runner cap R | c = +0.5R confirm
All three caps share the SAME 1h signals + SAME +0.5R fill (only the runner cap differs).

    DCH_ENTRY_AT_CONFIRM=1 DCH_SO_RUNNER_CAP=8 \
        python sync/donchian/scaleout_1h.py --dry-run --start 2024-01-01 --end 2025-01-01
    DCH_ENTRY_AT_CONFIRM=1 DCH_SO_RUNNER_CAP=8 \
        python sync/donchian/scaleout_1h.py --apply  --start 2024-01-01
"""
from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))   # sync/         -> trade_sync_common
sys.path.insert(0, str(_HERE.parent))        # sync/donchian -> strategy / scaleout
import trade_sync_common as tsc              # noqa: E402
import strategy as strat                     # noqa: E402
import scaleout as so                        # noqa: E402  (reuse resolve_scaleout / _load_1m / SO_SYMBOLS)
from ict import config as C                  # noqa: E402

TF = "1h"
CONFIRM_HTF = None                            # 1h family: own-TF ER gate, NO higher-tf confirm
_SO_CAP = int(float(os.environ.get("DCH_SO_RUNNER_CAP", "4.0")))
# Explicit, number-tagged version so the 1h scale-out never collides with the 30m+4h 'd30so*'
# family: d1h_so4c / d1h_so6c / d1h_so8c (varchar(10): 8 chars). 'c' = +0.5R confirm twin.
VERSION = f"d1h_so{_SO_CAP}" + (
    "c" if (getattr(C, "ENTRY_AT_CONFIRM", False) and getattr(C, "ENTRY_CONFIRM_BUF", 0.0) > 0) else "")

DEFAULT_START = pd.Timestamp("2025-06-16", tz="UTC")


def run_symbol(sym: str, w_start: pd.Timestamp, w_end: pd.Timestamp):
    """Return (rows, resolved_n, total_r) for one symbol — 1h breakout, scale-out exit."""
    ltf_min = strat.TF_MINUTES[TF]
    df = tsc.fetch_klines(sym, TF, int((w_start - so._warmup(TF)).timestamp() * 1000),
                          int(w_end.timestamp() * 1000))
    if df is None or df.empty:
        print(f"  {sym:<10} SKIP (no {TF})", flush=True)
        return [], 0, 0.0
    # Only FULLY-CLOSED bars (mirror the live emitter / 30m stream).
    df = df[df.index + pd.Timedelta(minutes=ltf_min) <= min(w_end, pd.Timestamp.now(tz="UTC"))]
    if df.empty:
        print(f"  {sym:<10} SKIP (no closed {TF})", flush=True)
        return [], 0, 0.0
    sigs = [s for s in strat.generate_signals(df, sym) if w_start <= s.timestamp < w_end]
    sigs = strat.us_hours_gate(sigs, sym, TF)   # no-op for the crypto+XAU scale-out universe
    if not sigs:
        print(f"  {sym:<10} 0 breakouts", flush=True)
        return [], 0, 0.0
    m1_end = min(pd.Timestamp.now(tz="UTC"), w_end + so.M1_TAIL)
    df1m = so._load_1m(sym, w_start, m1_end)
    if df1m is None or df1m.empty:
        print(f"  {sym:<10} SKIP (no 1m)", flush=True)
        return [], 0, 0.0
    rows, resolved, tot = [], 0, 0.0
    for s in sigs:
        res = so.resolve_scaleout(sym, s.timestamp, s.direction, s.entry, s.stop_loss,
                                  s.take_profit_1, df1m=df1m, ltf_minutes=ltf_min,
                                  expiry_minutes=s.expiry_minutes, runner_cap=float(_SO_CAP))
        if res is None:                       # failed directional confirmation -> no row
            continue
        row = tsc.build_row(sym, s.timestamp, s.direction, res.get("entry_eff", s.entry),
                            s.stop_loss, res.get("cap_price", s.take_profit_1), res,
                            strategy=s.strategy, quality=s.quality,
                            confluence_score=s.confluence_score)
        row["version"] = VERSION
        rows.append(row)
        if res["status"] in ("closed_tp", "closed_sl") and res["pnl_r"] is not None:
            resolved += 1
            tot += float(res["pnl_r"])
    wr = 100 * sum(1 for r in rows if r["status"] == "closed_tp") / resolved if resolved else 0
    print(f"  {sym:<10} {len(sigs):>3} breakouts -> resolved {resolved:>3} "
          f"WR={wr:>3.0f}%  totR={tot:+6.1f}", flush=True)
    return rows, resolved, tot


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    ap.add_argument("--symbols", nargs="*", default=so.SO_SYMBOLS)
    ap.add_argument("--start", default=None, help="YYYY-MM-DD (default 2025-06-16)")
    ap.add_argument("--end", default=None, help="YYYY-MM-DD (default now)")
    ap.add_argument("--no-wipe", action="store_true",
                    help="append: skip the version wipe (for multi-window backfill)")
    args = ap.parse_args()

    w_start = pd.Timestamp(args.start, tz="UTC") if args.start else DEFAULT_START
    w_end = pd.Timestamp(args.end, tz="UTC") if args.end else pd.Timestamp.now(tz="UTC")
    print(f"=== Donchian 1h SCALE-OUT [{w_start.date()} .. {w_end.date()}) "
          f"| {TF} (ER-gated, no htf) | first=+{so.FIRST_R:g}R close={so.CLOSE_FRAC:g} "
          f"runner cap{_SO_CAP}R / {so.HORIZON.days}d limit "
          f"| {len(args.symbols)} symbols | version='{VERSION}' ===", flush=True)

    all_rows, tot_n, tot_r = [], 0, 0.0
    for sym in args.symbols:
        try:
            rows, n, r = run_symbol(sym, w_start, w_end)
            all_rows += rows; tot_n += n; tot_r += r
        except Exception as e:  # noqa: BLE001
            print(f"  ! {sym}: {e}", flush=True)

    wr = 100 * sum(1 for r in all_rows if r["status"] == "closed_tp") / tot_n if tot_n else 0
    print(f"\n=== TOTAL resolved={tot_n}  WR={wr:.0f}%  totR={tot_r:+.1f} ===")

    if args.dry_run:
        print("[dry-run] no DB write.")
        return

    conn = tsc.backtest_conn()
    if not args.no_wipe:
        cur = conn.cursor()
        cur.execute(f"DELETE FROM {tsc.TABLE} WHERE version=%s", (VERSION,))
        print(f"  wiped {cur.rowcount} existing '{VERSION}' rows")
        conn.commit(); cur.close()
    else:
        print(f"  [--no-wipe] appending {len(all_rows)} rows (no wipe)")
    n = tsc.upsert_rows(conn, all_rows)
    conn.close()
    print(f"  upserted {n} '{VERSION}' rows into {tsc.TABLE}")


if __name__ == "__main__":
    main()
