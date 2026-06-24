"""Demo-faithful backtest engine — replays the LIVE executor's portfolio logic over history.

Unlike sync/donchian/scaleout.py (which resolves EVERY signal independently), this reproduces the
real demo behaviour: ONE position per symbol, an OPPOSITE confirmed signal REVERSES (close+flip),
a SAME-direction one is ignored, capped by MAX_CONCURRENT. Runs all three runner caps (4R/6R/8R)
over the validated SO_SYMBOLS universe and **upserts the realized trades into the SAME backtest
table the dashboard reads** (ict_trade.trading_signals), tagged version='<cap>_demo' — exactly the
backtest row shape (build_row), so the Demo view is just a backtest stream with the portfolio rule.

    DCH_ENTRY_AT_CONFIRM=1 python sync/live_exec/demo_backtest.py             # all caps -> DB
    DCH_ENTRY_AT_CONFIRM=1 python sync/live_exec/demo_backtest.py --caps 8    # just 8R (faster)
    DCH_ENTRY_AT_CONFIRM=1 python sync/live_exec/demo_backtest.py --dry-run   # resolve, no DB write
"""
from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parents[1]))
sys.path.insert(0, str(_HERE.parents[1] / "donchian"))
import _bootenv                       # noqa: E402,F401  (forces DCH_ENTRY_AT_CONFIRM=1)
import trade_sync_common as tsc       # noqa: E402
import strategy as strat              # noqa: E402
import scaleout as so                 # noqa: E402

LTF = 30
# cap -> (UI strategy key, label). version written = '<key>_demo'. Keys match Sidebar.jsx GROUPS.
CAPS = {
    4: ("d30_4h_soc", "DONCHIAN 30m+4h·WR 4R ·0.5R"),
    6: ("d30so6c", "DONCHIAN 30m+4h·WR 6R ·0.5R"),
    8: ("d30so8c", "DONCHIAN 30m+4h·WR 8R ·0.5R"),
}
YEARS = [
    ("2024", pd.Timestamp("2024-01-01", tz="UTC"), pd.Timestamp("2025-01-01", tz="UTC")),
    ("2025", pd.Timestamp("2025-01-01", tz="UTC"), pd.Timestamp("2026-01-01", tz="UTC")),
    ("2026", pd.Timestamp("2026-01-01", tz="UTC"), pd.Timestamp("2026-06-22", tz="UTC")),
]
FULL_START = YEARS[0][1]
FULL_END = YEARS[-1][2]


def _signals(sym):
    """Confirmed 30m+4h breakouts over the full span (entry/sl/tp + fire time)."""
    ltf_min = strat.TF_MINUTES[so.TF]
    df = tsc.fetch_klines(sym, so.TF, int((FULL_START - so._warmup(so.TF)).timestamp() * 1000),
                          int(FULL_END.timestamp() * 1000))
    if df is None or df.empty:
        return []
    df = df[df.index + pd.Timedelta(minutes=ltf_min) <= min(FULL_END, pd.Timestamp.now(tz="UTC"))]
    sigs = [s for s in strat.generate_signals(df, sym) if FULL_START <= s.timestamp < FULL_END]
    if sigs:
        hdf = tsc.fetch_klines(sym, so.CONFIRM_HTF, int((FULL_START - so._warmup(so.CONFIRM_HTF)).timestamp() * 1000),
                               int(FULL_END.timestamp() * 1000))
        sigs = strat.htf_confirm(sigs, so.TF, hdf, so.CONFIRM_HTF)
    return strat.us_hours_gate(sigs, sym, so.TF)


def _events_for_symbol(sym, caps):
    """Per cap, the confirmed signals' independent outcomes (fill / natural exit / natural R)."""
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
                # RAW signal geometry — fed back into resolve_scaleout for reverse-close re-resolves
                # (it re-applies the +0.5R confirm shift itself; passing entry_eff would double-shift).
                "symbol": sym, "direction": s.direction.lower(), "signal_ts": s.timestamp,
                "entry": s.entry, "sl": s.stop_loss, "tp": s.take_profit_1,
                # DISPLAY geometry — exactly what the backtest row stores (sync_daily.py build_row):
                # the +0.5R confirmed fill (entry_eff) and the runner cap (cap_price), so the card +
                # chart draw the SAME levels as backtest (TP1 = entry_eff+1R, not the raw-entry +1R).
                "entry_eff": float(res.get("entry_eff", s.entry)),
                "cap_price": float(res.get("cap_price", s.take_profit_1)),
                "fill": pd.Timestamp(res["real_entry_time"]).tz_convert("UTC"),
                "nat_exit": pd.Timestamp(res["exit_time"]).tz_convert("UTC") if res.get("exit_time") else None,
                "nat_exit_price": float(res["exit_price"]) if res.get("exit_price") is not None else None,
                "nat_r": float(res["pnl_r"]) if res.get("pnl_r") is not None else None,
                "nat_status": res.get("status")})   # 'closed_tp' / 'closed_sl' / 'active' (DB form)
    return out


def _truncated_res(sym, p, t, cap):
    """The resolve result if a position is force-closed at time t (a reverse) — its truncated
    R / exit time / exit price come from a horizon-limited re-resolve on the RAW signal geometry."""
    horizon = t - p["fill"]
    if horizon <= pd.Timedelta(0):
        return None
    df1m = so._load_1m(sym, FULL_START, min(pd.Timestamp.now(tz="UTC"), FULL_END + so.M1_TAIL))
    return so.resolve_scaleout(sym, p["signal_ts"], p["direction"], p["entry"], p["sl"], p["tp"],
                               df1m=df1m, ltf_minutes=LTF, expiry_minutes=180,
                               runner_cap=float(cap), horizon=horizon, active_if_incomplete=False)


def _rec(p, exit_t, r, status, exit_price):
    """A realized demo trade -> the fields build_row needs for a backtest DB row.

    Stores the DISPLAY geometry (entry_eff confirmed fill + cap_price runner cap) — exactly what the
    backtest row stores (sync_daily build_row) — so card + chart match. `status` is the DB form
    ('closed_tp'/'closed_sl'/'active'); a reverse-close maps to closed_tp/closed_sl by its R sign."""
    return {"sym": p["symbol"], "dir": p["direction"], "entry": p["entry_eff"], "sl": p["sl"],
            "tp": p["cap_price"], "signal_ts": p["signal_ts"], "fill": p["fill"], "exit": exit_t,
            "exit_price": exit_price, "r": (float(r) if r is not None else None), "status": status}


def _walk(events, cap, max_concurrent):
    """Chronological one-position-per-symbol + reverse walk. Returns realized trade dicts (see _rec).

    A position leaves the book by its natural scale-out exit, by a reverse (an opposite confirmed
    signal force-closes it early at its truncated R), or stays 'active' at the data edge."""
    evs = sorted(events, key=lambda e: e["fill"])
    open_pos, realized = {}, []

    def close_before(t):
        for sym, p in list(open_pos.items()):
            if p["nat_exit"] is not None and p["nat_exit"] <= t:
                realized.append(_rec(p, p["nat_exit"], p["nat_r"], p["nat_status"], p["nat_exit_price"]))
                del open_pos[sym]

    for e in evs:
        t = e["fill"]
        close_before(t)
        sym = e["symbol"]
        if sym in open_pos:
            p = open_pos[sym]
            if p["direction"] == e["direction"]:
                continue
            res = _truncated_res(sym, p, t, cap)                       # reverse-close
            r = float(res["pnl_r"]) if res and res.get("pnl_r") is not None else 0.0
            exit_t = pd.Timestamp(res["exit_time"]).tz_convert("UTC") if res and res.get("exit_time") else t
            ep = float(res["exit_price"]) if res and res.get("exit_price") is not None else None
            realized.append(_rec(p, exit_t, r, "closed_tp" if r >= 0 else "closed_sl", ep))
            del open_pos[sym]
        if len(open_pos) >= max_concurrent:
            continue
        open_pos[sym] = e
    for sym, p in open_pos.items():
        if p["nat_exit"] is not None:
            realized.append(_rec(p, p["nat_exit"], p["nat_r"], p["nat_status"], p["nat_exit_price"]))
        else:                                                          # still riding at the data edge
            realized.append(_rec(p, None, None, "active", None))
    return realized


def _db_rows(realized, version):
    """build_row per realized trade, tagged with the demo `version` — the same backtest table shape."""
    rows = []
    for r in realized:
        outcome = {
            "status": r["status"],
            "real_entry_time": r["fill"].to_pydatetime() if r["fill"] is not None else None,
            "exit_time": r["exit"].to_pydatetime() if r["exit"] is not None else None,
            "exit_price": r["exit_price"],
            "pnl_r": r["r"],
        }
        row = tsc.build_row(r["sym"], r["signal_ts"], "LONG" if r["dir"] == "long" else "SHORT",
                            r["entry"], r["sl"], r["tp"], outcome)
        row["version"] = version
        rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--caps", nargs="*", type=int, default=sorted(CAPS))
    ap.add_argument("--symbols", nargs="*", default=so.SO_SYMBOLS)
    ap.add_argument("--dry-run", action="store_true", help="resolve + walk but DON'T upsert to the DB")
    args = ap.parse_args()
    caps = [c for c in args.caps if c in CAPS]
    syms = args.symbols
    print(f"=== demo-faithful backtest -> DB | caps={caps} | {len(syms)} symbols | "
          f"{FULL_START.date()}..{FULL_END.date()} ===", flush=True)

    # collect events once per symbol (1m loaded once), reused across caps
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
        version = f"demo{c}"          # varchar(10): 'demo4' / 'demo6' / 'demo8'
        realized = _walk(ev_by_cap[c], c, max_concurrent=len(syms))
        rows = _db_rows(realized, version)
        all_rows += rows
        closed = [r for r in realized if r["r"] is not None]
        tot_r = sum(r["r"] for r in closed)
        wins = sum(1 for r in closed if r["r"] > 0)
        wr = round(100 * wins / len(closed)) if closed else 0
        print(f"  [{version}] cap{c}R -> {len(rows)} rows · R={tot_r:+.1f} · WR={wr}% "
              f"· active={len(realized) - len(closed)}", flush=True)

    if args.dry_run:
        print(f"\n  [dry-run] {len(all_rows)} rows would upsert (no DB write).")
        return
    bt = tsc.backtest_conn()
    n = tsc.upsert_rows(bt, all_rows)
    bt.close()
    print(f"\n  upserted {n} rows into {tsc.TABLE} (versions: {', '.join(f'demo{c}' for c in caps)})")


if __name__ == "__main__":
    main()
