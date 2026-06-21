"""Parity report — live-intent levels vs sync/donchian/scaleout.resolve_scaleout (the source of truth).

For every dch30_4h signal in a window it computes the executor's INTENDED levels (levels.py) and
the authoritative resolve_scaleout result on the SAME 1m data, then diffs:
  - eff_entry  (our confirm-level)   vs  resolve_scaleout entry_eff
  - cap        (our +8R structural)  vs  resolve_scaleout cap_price  (the row tp_price)
A non-empty mismatch list means the live layer would diverge from the backtest — the Faz-0
blocking gate is "0 mismatches". Run it for any window; defaults to the last 14 days.

    python sync/live_exec/parity_report.py
    python sync/live_exec/parity_report.py --start 2026-05-01 --end 2026-06-01
"""
from __future__ import annotations

import sys
import argparse
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parents[1]))
sys.path.insert(0, str(_HERE.parents[1] / "donchian"))
import _bootenv                                      # noqa: E402,F401  -- MUST precede tsc/scaleout/ict.config
import trade_sync_common as tsc                      # noqa: E402
import config as cfgmod                              # noqa: E402
import levels as lvl                                 # noqa: E402
import scaleout as so                                # noqa: E402

TOL = 1e-6


def _signals(live, symbols, w_start, w_end):
    cur = live.cursor()
    cur.execute("""
        SELECT symbol, signal_time, direction, entry, sl, tp
        FROM ict_trade.signals
        WHERE mode='dch30_4h' AND signal_time >= %s AND signal_time < %s AND symbol = ANY(%s)
        ORDER BY symbol, signal_time
    """, (w_start.to_pydatetime(), w_end.to_pydatetime(), list(symbols)))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    args = ap.parse_args()
    cfg = cfgmod.load_cfg()
    now = pd.Timestamp.now(tz="UTC")
    w_end = pd.Timestamp(args.end, tz="UTC") if args.end else now
    w_start = pd.Timestamp(args.start, tz="UTC") if args.start else now - pd.Timedelta(days=14)

    # parity is defined for the confirmed-entry model (the d30so8c track-record)
    from ict import config as C
    if not (getattr(C, "ENTRY_AT_CONFIRM", False) and cfg.entry_mode == "B"):
        print("[warn] run with DCH_ENTRY_AT_CONFIRM=1 and LIVE_ENTRY_MODE=B for d30so8c parity.")

    live = tsc.live_conn()
    sigs = _signals(live, cfg.symbols, w_start, w_end)
    print(f"=== parity [{w_start.date()}..{w_end.date()}) | {len(sigs)} dch30_4h signals | "
          f"cap={cfg.runner_cap_r:g}R mode={cfg.entry_mode} ===")

    checked = mism = 0
    for sig in sigs:
        fire = pd.Timestamp(sig["signal_time"]).tz_convert("UTC") + pd.Timedelta(minutes=30)
        df1m = tsc.fetch_1m(sig["symbol"], fire - pd.Timedelta(minutes=2),
                            min(now, fire + so.HORIZON + pd.Timedelta(days=1)))
        if df1m is None or df1m.empty:
            continue
        res = so.resolve_scaleout(sig["symbol"], pd.Timestamp(sig["signal_time"]), sig["direction"],
                                  float(sig["entry"]), float(sig["sl"]), float(sig["tp"]),
                                  df1m=df1m, ltf_minutes=30, expiry_minutes=cfg.expiry_min)
        if res is None:        # failed confirmation -> backtest writes no row; live takes no trade
            continue
        lv = lvl.compute_levels(sig["direction"], float(sig["entry"]), float(sig["sl"]),
                                entry_mode=cfg.entry_mode, confirm_buf=cfg.confirm_buf,
                                first_r=cfg.first_r, close_frac=cfg.close_frac,
                                runner_cap_r=cfg.runner_cap_r)
        checked += 1
        d_entry = abs(lv.eff_entry - float(res.get("entry_eff", lv.eff_entry)))
        d_cap = abs(lv.cap - float(res.get("cap_price", lv.cap)))
        rel = max(lv.risk0, 1e-9)
        if d_entry / rel > TOL or d_cap / rel > TOL:
            mism += 1
            print(f"  MISMATCH {sig['symbol']} {sig['signal_time']}: "
                  f"entry Δ={d_entry:.2e} cap Δ={d_cap:.2e} "
                  f"(ours entry={lv.eff_entry:.6g} cap={lv.cap:.6g} | "
                  f"so entry={res.get('entry_eff'):.6g} cap={res.get('cap_price'):.6g})")
    live.close()
    print(f"\n=== checked {checked} | mismatches {mism} -> {'PASS' if mism == 0 else 'FAIL'} ===")


if __name__ == "__main__":
    main()
