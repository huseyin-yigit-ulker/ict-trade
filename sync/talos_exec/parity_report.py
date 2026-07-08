"""Parity report — the TALOS executor's exit engine vs the authoritative backtest (Faz-0 gate).

The executor manages every open position with sync/talos/strategy.track_open — the SAME function the
paper canli.py drives. This report proves that replay reproduces the backtest walk() to the decimal:
for every SETTLED trade in the window it replays track_open from the trade's own fill and diffs the
exit price, exit reason and net R against generate_trades() (which uses walk()). A non-empty mismatch
list means the live engine would diverge from the track-record — the blocking gate is "0 mismatches".

    python sync/talos_exec/parity_report.py                      # last 21 days
    python sync/talos_exec/parity_report.py --start 2026-05-01 --end 2026-06-01
    python sync/talos_exec/parity_report.py --live               # also diff vs the paper mode='talos' feed
"""
from __future__ import annotations

import sys
import json
import argparse
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parents[1]))
sys.path.insert(0, str(_HERE.parents[1] / "talos"))
import trade_sync_common as tsc                      # noqa: E402
import strategy as M                                 # noqa: E402

PX_TOL = 1e-4        # relative price tolerance
R_TOL = 1e-3         # absolute R tolerance


def _check_backtest(w_start, w_end) -> int:
    trades = [t for t in M.generate_trades(w_start, w_end) if t.reason != "open"]
    print(f"=== parity [{w_start.date()}..{w_end.date()}) | {len(trades)} settled backtest trades ===")
    mism = 0
    for t in trades:
        now_r = t.exit_time + pd.Timedelta(minutes=2)
        res = M.track_open(t.entry_time, t.side, float(t.entry), float(t.stop), now_r)
        if res is None or res.get("status") != "closed":
            mism += 1
            print(f"  MISMATCH {t.entry_time:%m-%d %H:%M} {('long' if t.side>0 else 'short')}: "
                  f"track_open did not settle (got {res and res.get('status')})")
            continue
        d_px = abs(float(res["exit_px"]) - float(t.exit_px)) / max(abs(t.exit_px), 1e-9)
        d_r = abs(float(res["pnl_r"]) - float(t.pnl_r))
        bad = d_px > PX_TOL or d_r > R_TOL or res["reason"] != t.reason
        if bad:
            mism += 1
            print(f"  MISMATCH {t.entry_time:%m-%d %H:%M} {('long' if t.side>0 else 'short')}: "
                  f"exit Δ={d_px:.2e} R Δ={d_r:.2e} reason {res['reason']}!={t.reason} "
                  f"(walk exit={t.exit_px:.2f} R={t.pnl_r:+.3f} | track exit={res['exit_px']:.2f} R={res['pnl_r']:+.3f})")
    print(f"  backtest-vs-track_open: checked {len(trades)} | mismatches {mism} -> {'PASS' if mism==0 else 'FAIL'}")
    return mism


def _check_live(now) -> int:
    """Diff the paper mode='talos' feed's stored result vs a fresh track_open replay (they share the
    function, so this validates the STORED inputs/context, not the math)."""
    live = tsc.live_conn()
    cur = live.cursor()
    cur.execute("""SELECT symbol, signal_time, direction, entry, sl, context
                   FROM ict_trade.signals WHERE mode='talos'
                   AND COALESCE(context->>'pos','open')='closed'
                   AND signal_time >= %s ORDER BY signal_time""",
                ((now - pd.Timedelta(days=14)).to_pydatetime(),))
    rows = cur.fetchall(); cur.close(); live.close()
    print(f"=== live paper feed | {len(rows)} closed mode='talos' rows ===")
    mism = 0
    for sym, stime, d, entry, sl, ctx in rows:
        ctx = ctx if isinstance(ctx, dict) else (json.loads(ctx) if ctx else {})
        stored = ctx.get("pnl_r")
        side = 1 if str(d).upper() == "LONG" else -1
        res = M.track_open(pd.Timestamp(stime) + pd.Timedelta(minutes=1), side,
                           float(entry), float(sl), now)
        if res is None or res.get("status") != "closed" or stored is None:
            continue
        if abs(float(res["pnl_r"]) - float(stored)) > 2e-2:
            mism += 1
            print(f"  MISMATCH {sym} {stime:%m-%d %H:%M} {d}: stored {stored:+.2f}R vs replay {res['pnl_r']:+.2f}R")
    print(f"  live-vs-track_open: checked {len(rows)} | mismatches {mism} -> {'PASS' if mism==0 else 'FAIL'}")
    return mism


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()
    now = pd.Timestamp.now(tz="UTC")
    w_end = pd.Timestamp(args.end, tz="UTC") if args.end else now
    w_start = pd.Timestamp(args.start, tz="UTC") if args.start else now - pd.Timedelta(days=21)

    total = _check_backtest(w_start, w_end)
    if args.live:
        total += _check_live(now)
    print(f"\n=== TOTAL mismatches {total} -> {'PASS' if total==0 else 'FAIL'} ===")
    sys.exit(1 if total else 0)


if __name__ == "__main__":
    main()
