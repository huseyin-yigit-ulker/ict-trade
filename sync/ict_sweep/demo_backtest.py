"""Demo-faithful backtest for the ICT sweep strategy — LIVE rules, 2026, 7-symbol set.

Identical portfolio machinery to sync/live_exec/demo_backtest.py (ONE position per symbol, an
OPPOSITE confirmed signal REVERSES, a SAME-direction one is ignored, MAX_CONCURRENT), and the
SAME exit engine (so.resolve_scaleout: +0.5R confirmed fill, 60%@+1R, breakeven runner, runner
cap 4R/6R/8R, 3-day limit). The ONLY swap vs the Donchian demo is the signal source:
ict_sweep.strategy.generate_signals (liquidity sweep -> MSS reclaim), optionally 4h-bias gated.

    DCH_ENTRY_AT_CONFIRM=1 python sync/ict_sweep/demo_backtest.py --dry-run            # R/WR, no DB
    DCH_ENTRY_AT_CONFIRM=1 python sync/ict_sweep/demo_backtest.py --dry-run --no-htf    # no 4h bias
    DCH_ENTRY_AT_CONFIRM=1 python sync/ict_sweep/demo_backtest.py --caps 8              # write demo to DB
"""
from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parents[1]))                    # sync/  -> trade_sync_common
sys.path.insert(0, str(_HERE.parents[1] / "live_exec"))     # _bootenv (forces confirm twin)
sys.path.insert(0, str(_HERE.parents[1] / "donchian"))      # strategy, scaleout
import _bootenv                       # noqa: E402,F401  (DCH_ENTRY_AT_CONFIRM / DCH_SO_RUNNER_CAP)
import trade_sync_common as tsc       # noqa: E402
import strategy as strat              # noqa: E402
import scaleout as so                 # noqa: E402
import demo_backtest as dbt           # noqa: E402  (reuse _walk / _truncated_res / _rec / _db_rows)
import strategy as donstrat           # noqa: E402  (htf_confirm / us_hours_gate)
from ict_sweep import strategy as ict # noqa: E402

LTF = 30
# The 7-symbol "ilk izlenim" universe (user-specified).
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XAUUSDT", "XAGUSDT", "XRPUSDT", "BNBUSDT"]
# cap -> demo version tag (varchar(10)). Distinct from the Donchian demo's demo4/6/8.
CAPS = {4: "ictsw4", 6: "ictsw6", 8: "ictsw8"}
FULL_START = pd.Timestamp("2026-01-01", tz="UTC")
FULL_END = pd.Timestamp.now(tz="UTC")

_USE_HTF = True   # set by main(); 4h trend-bias gate (premium/discount)


def _signals(sym):
    """Confirmed ICT sweep signals over 2026 (entry/sl/tp + fire time), optional 4h bias gate."""
    ltf_min = strat.TF_MINUTES[so.TF]
    df = tsc.fetch_klines(sym, so.TF, int((FULL_START - so._warmup(so.TF)).timestamp() * 1000),
                          int(FULL_END.timestamp() * 1000))
    if df is None or df.empty:
        return []
    df = df[df.index + pd.Timedelta(minutes=ltf_min) <= min(FULL_END, pd.Timestamp.now(tz="UTC"))]
    sigs = [s for s in ict.generate_signals(df, sym) if FULL_START <= s.timestamp < FULL_END]
    if sigs and _USE_HTF:
        hdf = tsc.fetch_klines(sym, so.CONFIRM_HTF,
                               int((FULL_START - so._warmup(so.CONFIRM_HTF)).timestamp() * 1000),
                               int(FULL_END.timestamp() * 1000))
        sigs = donstrat.htf_confirm(sigs, so.TF, hdf, so.CONFIRM_HTF)
    return donstrat.us_hours_gate(sigs, sym, so.TF)


def _events_for_symbol(sym, caps):
    """Per cap, each confirmed signal's independent scale-out outcome (mirrors dbt._events_for_symbol)."""
    sigs = _signals(sym)
    if not sigs:
        return {c: [] for c in caps}
    m1_end = min(pd.Timestamp.now(tz="UTC"), FULL_END + so.M1_TAIL)
    df1m = so._load_1m(sym, FULL_START, m1_end)
    out = {c: [] for c in caps}
    if df1m is None or df1m.empty:
        return out
    for cap in caps:
        for s in sigs:
            res = so.resolve_scaleout(sym, s.timestamp, s.direction, s.entry, s.stop_loss,
                                      s.take_profit_1, df1m=df1m, ltf_minutes=LTF, expiry_minutes=180,
                                      runner_cap=float(cap))
            if res is None or res.get("real_entry_time") is None:
                continue
            out[cap].append({
                "symbol": sym, "direction": s.direction.lower(), "signal_ts": s.timestamp,
                "entry": s.entry, "sl": s.stop_loss, "tp": s.take_profit_1,
                "entry_eff": float(res.get("entry_eff", s.entry)),
                "cap_price": float(res.get("cap_price", s.take_profit_1)),
                "fill": pd.Timestamp(res["real_entry_time"]).tz_convert("UTC"),
                "nat_exit": pd.Timestamp(res["exit_time"]).tz_convert("UTC") if res.get("exit_time") else None,
                "nat_exit_price": float(res["exit_price"]) if res.get("exit_price") is not None else None,
                "nat_r": float(res["pnl_r"]) if res.get("pnl_r") is not None else None,
                "nat_status": res.get("status")})
    return out


# _truncated_res reads FULL_START/M1_TAIL from ITS module (dbt, 2024 start). Rebind it here so the
# reverse-close re-resolves load 1m from OUR 2026 window (avoids a multi-year XAG 1m fetch).
def _truncated_res(sym, p, t, cap):
    horizon = t - p["fill"]
    if horizon <= pd.Timedelta(0):
        return None
    df1m = so._load_1m(sym, FULL_START, min(pd.Timestamp.now(tz="UTC"), FULL_END + so.M1_TAIL))
    return so.resolve_scaleout(sym, p["signal_ts"], p["direction"], p["entry"], p["sl"], p["tp"],
                               df1m=df1m, ltf_minutes=LTF, expiry_minutes=180,
                               runner_cap=float(cap), horizon=horizon, active_if_incomplete=False)


def _walk(events, cap, max_concurrent):
    """Chronological 1-position-per-symbol + reverse walk (copy of dbt._walk, local _truncated_res)."""
    evs = sorted(events, key=lambda e: e["fill"])
    open_pos, realized = {}, []

    def close_before(tm):
        for sym, p in list(open_pos.items()):
            if p["nat_exit"] is not None and p["nat_exit"] <= tm:
                realized.append(dbt._rec(p, p["nat_exit"], p["nat_r"], p["nat_status"], p["nat_exit_price"]))
                del open_pos[sym]

    for e in evs:
        t = e["fill"]
        close_before(t)
        sym = e["symbol"]
        if sym in open_pos:
            p = open_pos[sym]
            if p["direction"] == e["direction"]:
                continue
            res = _truncated_res(sym, p, t, cap)
            r = float(res["pnl_r"]) if res and res.get("pnl_r") is not None else 0.0
            exit_t = pd.Timestamp(res["exit_time"]).tz_convert("UTC") if res and res.get("exit_time") else t
            ep = float(res["exit_price"]) if res and res.get("exit_price") is not None else None
            realized.append(dbt._rec(p, exit_t, r, "closed_tp" if r >= 0 else "closed_sl", ep))
            del open_pos[sym]
        if len(open_pos) >= max_concurrent:
            continue
        open_pos[sym] = e
    for sym, p in open_pos.items():
        if p["nat_exit"] is not None:
            realized.append(dbt._rec(p, p["nat_exit"], p["nat_r"], p["nat_status"], p["nat_exit_price"]))
        else:
            realized.append(dbt._rec(p, None, None, "active", None))
    return realized


def main():
    global _USE_HTF
    ap = argparse.ArgumentParser()
    ap.add_argument("--caps", nargs="*", type=int, default=sorted(CAPS))
    ap.add_argument("--symbols", nargs="*", default=SYMBOLS)
    ap.add_argument("--no-htf", action="store_true", help="drop the 4h trend-bias gate")
    ap.add_argument("--dry-run", action="store_true", help="resolve + walk, DON'T upsert to DB")
    args = ap.parse_args()
    _USE_HTF = not args.no_htf
    caps = [c for c in args.caps if c in CAPS]
    syms = args.symbols
    print(f"=== ICT sweep demo-faithful backtest | caps={caps} | {len(syms)} symbols | "
          f"4h-bias={'ON' if _USE_HTF else 'OFF'} | swing_n={ict.SWING_N} disp={ict.DISP} | "
          f"{FULL_START.date()}..{FULL_END.date()} ===", flush=True)

    ev_by_cap = {c: [] for c in caps}
    for sym in syms:
        try:
            per = _events_for_symbol(sym, caps)
            for c in caps:
                ev_by_cap[c] += per[c]
            print(f"  {sym:<12} {len(per[caps[0]])} confirmed signals", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {sym}: {e}", flush=True)

    all_rows = []
    for c in caps:
        version = CAPS[c]
        realized = _walk(ev_by_cap[c], c, max_concurrent=len(syms))
        rows = dbt._db_rows(realized, version)
        all_rows += rows
        closed = [r for r in realized if r["r"] is not None]
        tot_r = sum(r["r"] for r in closed)
        wins = sum(1 for r in closed if r["r"] > 0)
        wr = round(100 * wins / len(closed)) if closed else 0
        print(f"  [{version}] cap{c}R -> {len(rows)} rows · R={tot_r:+.1f} · WR={wr}% "
              f"· trades={len(closed)} · active={len(realized) - len(closed)}", flush=True)

    if args.dry_run:
        print(f"\n  [dry-run] {len(all_rows)} rows would upsert (no DB write).")
        return
    bt = tsc.backtest_conn()
    for c in caps:                                  # wipe each version before re-upsert
        cur = bt.cursor()
        cur.execute(f"DELETE FROM {tsc.TABLE} WHERE version=%s", (CAPS[c],))
        bt.commit(); cur.close()
    n = tsc.upsert_rows(bt, all_rows)
    bt.close()
    print(f"\n  upserted {n} rows into {tsc.TABLE} (versions: {', '.join(CAPS[c] for c in caps)})")


if __name__ == "__main__":
    main()
