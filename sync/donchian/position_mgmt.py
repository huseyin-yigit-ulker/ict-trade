"""dch30_4h with POSITION MANAGEMENT (one position per symbol) — EXPERIMENT, no DB write.

Default backtest resolves every signal independently (overlapping positions allowed). This
tests the user's rule, per symbol, event-driven:
  • IN A TRADE  + new SAME-direction signal      -> cancel the new signal (no pyramiding)
  • IN A TRADE  + new OPPOSITE-direction signal   -> close the position NOW (at the new
                                                     signal's price), then activate the new
                                                     one (reverse)
  • PENDING (a fired signal whose entry hasn't filled) + ANY new signal -> drop the old
                                                     pending, the new signal becomes pending
  • FLAT        + new signal                      -> the new signal becomes pending

Each signal is first resolved INDEPENDENTLY (tsc.simulate -> fill_time, exit_time, pnl_r with
fees); the state machine then overlays the rule, and reversal-cut exits are priced with the
engine's own _net_r (round-trip fee included). Baseline (independent) total is reported in the
same run for a direct comparison.

    python sync/donchian/position_mgmt.py --start 2026-01-01
"""
from __future__ import annotations

import os
import sys
import pickle
import argparse
from pathlib import Path
from collections import defaultdict

import pandas as pd

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))
sys.path.insert(0, str(_HERE.parent))
import trade_sync_common as tsc              # noqa: E402
import strategy as strat                     # noqa: E402
from ict import config as C                  # noqa: E402
from backtester import _net_r                # noqa: E402  (fee-consistent R for reversal cuts)

CACHE = Path(os.environ.get("DONCHIAN_1M_CACHE", "/tmp/donchian1m_cache"))
EXPIRY = 180


def _warmup(tf): return pd.Timedelta(minutes=strat.TF_MINUTES[tf] * (strat.N_ENTRY + strat.ER_N) * 6)


def _load_1m(sym, start, end):
    cf = CACHE / f"{sym}.pkl"
    if cf.exists():
        return pickle.loads(cf.read_bytes())
    df = tsc.fetch_1m(sym, start - pd.Timedelta(hours=2), end)
    if df is not None and not df.empty:
        CACHE.mkdir(exist_ok=True); cf.write_bytes(pickle.dumps(df))
    return df


def _ts(x):
    if x is None:
        return None
    t = pd.Timestamp(x)
    return t.tz_localize("UTC") if t.tz is None else t.tz_convert("UTC")


def run_symbol(sym, w_start, w_end):
    """Return (managed_rows, baseline_total) for one symbol."""
    df = tsc.fetch_klines(sym, "30m", int((w_start - _warmup("30m")).timestamp() * 1000),
                          int(w_end.timestamp() * 1000))
    if df is None or df.empty:
        return [], 0.0
    sigs = [s for s in strat.generate_signals(df, sym) if w_start <= s.timestamp < w_end]
    hdf = tsc.fetch_klines(sym, "4h", int((w_start - _warmup("4h")).timestamp() * 1000),
                           int(w_end.timestamp() * 1000))
    sigs = strat.htf_confirm(sigs, "30m", hdf, "4h")
    if not sigs:
        return [], 0.0
    df1m = _load_1m(sym, w_start, w_end)
    if df1m is None or df1m.empty:
        return [], 0.0

    prev = C.PARTIAL_TP_ENABLED; C.PARTIAL_TP_ENABLED = False
    base_tot = 0.0
    events = []   # one dict per signal, time-ordered
    try:
        for s in sigs:
            res = tsc.simulate(sym, s.timestamp, s.direction, s.entry, s.stop_loss,
                               s.take_profit_1, df1m=df1m, ltf_minutes=30, expiry_minutes=EXPIRY)
            r = res["pnl_r"]
            if res["status"] in ("closed_tp", "closed_sl") and r is not None:
                base_tot += float(r)
            events.append({
                "fire": s.timestamp + pd.Timedelta(minutes=30), "dir": s.direction,
                "entry": float(s.entry), "sl": float(s.stop_loss),
                "risk": abs(float(s.entry) - float(s.stop_loss)),
                "fill": _ts(res["real_entry_time"]), "exit": _ts(res["exit_time"]),
                "status": res["status"], "pnl": (float(r) if r is not None else None),
                "deadline": s.timestamp + pd.Timedelta(minutes=30 + EXPIRY),
            })
    finally:
        C.PARTIAL_TP_ENABLED = prev
    events.sort(key=lambda e: e["fire"])

    # --- state machine: flat / pending / in_trade ---
    rows = []     # (pnl_r, kind)
    state, cur, pend = "flat", None, None
    n_rev = n_skip = n_repl = 0
    for s in events:
        t = s["fire"]
        # settle prior state up to t
        if state == "pending":
            p = pend
            if p["fill"] is not None and p["fill"] <= t:
                cur, pend, state = p, None, "in_trade"
            elif p["fill"] is None and p["deadline"] <= t:
                pend, state = None, "flat"               # entry never filled -> cancelled
        if state == "in_trade":
            c = cur
            if c["exit"] is not None and c["exit"] <= t:
                if c["pnl"] is not None:
                    rows.append((c["pnl"], "natural"))
                cur, state = None, "flat"
        # apply the rule with the new signal s
        if state == "flat":
            pend, state = s, "pending"
        elif state == "pending":
            pend = s; n_repl += 1                          # newest pending wins
        elif state == "in_trade":
            if s["dir"] == cur["dir"]:
                n_skip += 1                                # same dir -> cancel new
            else:                                          # opposite -> close now, reverse
                r = _net_r(cur["entry"], s["entry"], cur["risk"], cur["dir"])
                rows.append((r, "reversed")); n_rev += 1
                cur, pend, state = None, s, "pending"
    # settle whatever's left at end of data (resolve naturally)
    if state == "in_trade" and cur["pnl"] is not None:
        rows.append((cur["pnl"], "natural"))
    elif state == "pending" and pend["fill"] is not None and pend["pnl"] is not None:
        rows.append((pend["pnl"], "natural"))
    return rows, base_tot, n_rev, n_skip, n_repl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-01-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--symbols", nargs="*", default=strat.SYMBOLS)
    args = ap.parse_args()
    w_start = pd.Timestamp(args.start, tz="UTC")
    w_end = pd.Timestamp(args.end, tz="UTC") if args.end else pd.Timestamp.now(tz="UTC")
    print(f"=== dch30_4h POSITION-MGMT [{w_start.date()}..{w_end.date()}) | {len(args.symbols)} symbols ===",
          flush=True)

    all_rows, base_total = [], 0.0
    tot_rev = tot_skip = tot_repl = 0
    for sym in args.symbols:
        try:
            rows, bt, nrev, nskip, nrepl = run_symbol(sym, w_start, w_end)
            all_rows += rows; base_total += bt
            tot_rev += nrev; tot_skip += nskip; tot_repl += nrepl
            print(f"  {sym:<10} managed {len(rows):>3} (rev {nrev}, skip {nskip}, repl {nrepl})", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {sym}: {e}", flush=True)

    n = len(all_rows); tot = sum(r for r, _ in all_rows)
    wins = sum(1 for r, _ in all_rows if r > 0)
    rev_r = sum(r for r, k in all_rows if k == "reversed")
    print(f"\n=== BASELINE (independent, overlap):  totR = {base_total:+.1f} ===")
    print(f"=== MANAGED (1 pos/symbol + reverse):  totR = {tot:+.1f}  | {n} trades  WR {100*wins/n if n else 0:.0f}% ===")
    print(f"    reversals: {tot_rev} (toplam {rev_r:+.1f}R)  | same-dir skipped: {tot_skip}  | pending replaced: {tot_repl}")
    print(f"    fark: {tot - base_total:+.1f}R")


if __name__ == "__main__":
    main()
