"""Demo-faithful backtest engine — replays the LIVE executor's portfolio logic over history.

Unlike sync/donchian/scaleout.py (which resolves EVERY signal independently), this reproduces the
real demo behaviour: ONE position per symbol, an OPPOSITE confirmed signal REVERSES (close+flip),
a SAME-direction one is ignored, capped by MAX_CONCURRENT. Runs all three runner caps (4R/6R/8R)
× three years (2024/2025/2026) on the validated SO_SYMBOLS universe and writes a compact JSON the
dashboard imports (src/data/demoBacktest.json) — no DB, no grant.

    DCH_ENTRY_AT_CONFIRM=1 python sync/live_exec/demo_backtest.py            # all caps × years -> JSON
    DCH_ENTRY_AT_CONFIRM=1 python sync/live_exec/demo_backtest.py --caps 8   # just 8R (faster)
"""
from __future__ import annotations

import os
import sys
import json
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

OUT = _HERE.parents[2] / "src" / "data" / "demoBacktest.json"
LTF = 30
# cap -> (UI strategy key, label). Keys match src/components/layout/Sidebar.jsx GROUPS.
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
                "symbol": sym, "direction": s.direction.lower(), "signal_ts": s.timestamp,
                "entry": s.entry, "sl": s.stop_loss, "tp": s.take_profit_1,
                "fill": pd.Timestamp(res["real_entry_time"]).tz_convert("UTC"),
                "nat_exit": pd.Timestamp(res["exit_time"]).tz_convert("UTC") if res.get("exit_time") else None,
                "nat_r": float(res["pnl_r"]) if res.get("pnl_r") is not None else 0.0})
    return out


def _truncated_r(sym, p, t, cap):
    """R if a position is closed at time t (a reverse) instead of its natural exit."""
    horizon = t - p["fill"]
    if horizon <= pd.Timedelta(0):
        return 0.0
    df1m = so._load_1m(sym, FULL_START, min(pd.Timestamp.now(tz="UTC"), FULL_END + so.M1_TAIL))
    res = so.resolve_scaleout(sym, p["signal_ts"], p["direction"], p["entry"], p["sl"], p["tp"],
                              df1m=df1m, ltf_minutes=LTF, expiry_minutes=180,
                              runner_cap=float(cap), horizon=horizon, active_if_incomplete=False)
    return float(res["pnl_r"]) if res and res.get("pnl_r") is not None else 0.0


def _walk(events, cap, max_concurrent):
    """Chronological one-position-per-symbol + reverse walk. Returns realized trades [(exit, r, sym)]."""
    evs = sorted(events, key=lambda e: e["fill"])
    open_pos, realized = {}, []

    def close_before(t):
        for sym, p in list(open_pos.items()):
            if p["nat_exit"] is not None and p["nat_exit"] <= t:
                realized.append((p["nat_exit"], p["nat_r"], sym))
                del open_pos[sym]

    for e in evs:
        t = e["fill"]
        close_before(t)
        sym = e["symbol"]
        if sym in open_pos:
            p = open_pos[sym]
            if p["direction"] == e["direction"]:
                continue
            realized.append((t, _truncated_r(sym, p, t, cap), sym))   # reverse-close
            del open_pos[sym]
        if len(open_pos) >= max_concurrent:
            continue
        open_pos[sym] = e
    for sym, p in open_pos.items():
        realized.append((p["nat_exit"] or FULL_END, p["nat_r"], sym))
    return realized


def _aggregate(realized):
    """Per-year totals, all-time, per-symbol, and a monthly cumulative-R equity curve."""
    realized = sorted(realized, key=lambda x: x[0])
    years = {y: {"totalR": 0.0, "trades": 0, "wins": 0, "sym": {}} for y, _, _ in YEARS}
    allsym = {}
    cum, equity = 0.0, []
    month_cum = {}
    for exit_t, r, sym in realized:
        cum += r
        ym = f"{exit_t.year}-{exit_t.month:02d}"
        month_cum[ym] = cum
        y = str(exit_t.year)
        if y in years:
            a = years[y]; a["totalR"] += r; a["trades"] += 1; a["wins"] += (r > 0)
            s = a["sym"].setdefault(sym, {"r": 0.0, "n": 0, "w": 0})
            s["r"] += r; s["n"] += 1; s["w"] += (r > 0)
        g = allsym.setdefault(sym, {"r": 0.0, "n": 0, "w": 0})
        g["r"] += r; g["n"] += 1; g["w"] += (r > 0)
    equity = [{"m": m, "cumR": round(v, 2)} for m, v in sorted(month_cum.items())]

    def sym_list(d):
        return sorted([{"s": k, "r": round(v["r"], 1), "n": v["n"],
                        "wr": round(100 * v["w"] / v["n"]) if v["n"] else 0}
                       for k, v in d.items()], key=lambda x: -x["r"])

    out_years = {}
    tot_r = tot_n = tot_w = 0
    for y, a in years.items():
        wr = round(100 * a["wins"] / a["trades"]) if a["trades"] else 0
        out_years[y] = {"totalR": round(a["totalR"], 1), "trades": a["trades"], "wr": wr,
                        "perSymbol": sym_list(a["sym"])}
        tot_r += a["totalR"]; tot_n += a["trades"]; tot_w += a["wins"]
    return {
        "allTime": {"totalR": round(tot_r, 1), "trades": tot_n,
                    "wr": round(100 * tot_w / tot_n) if tot_n else 0},
        "years": out_years, "equity": equity, "perSymbolAll": sym_list(allsym),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--caps", nargs="*", type=int, default=sorted(CAPS))
    ap.add_argument("--symbols", nargs="*", default=so.SO_SYMBOLS)
    args = ap.parse_args()
    caps = [c for c in args.caps if c in CAPS]
    syms = args.symbols
    print(f"=== demo-faithful backtest | caps={caps} | {len(syms)} symbols | "
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

    result = {"generated": pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%d'),
              "universe": list(syms), "caps": {}}
    for c in caps:
        key, label = CAPS[c]
        realized = _walk(ev_by_cap[c], c, max_concurrent=len(syms))
        agg = _aggregate(realized)
        result["caps"][key] = {"key": key, "label": label, "capR": c, **agg}
        at = agg["allTime"]
        print(f"  [{key}] cap{c}R -> allTime R={at['totalR']:+.1f} trades={at['trades']} WR={at['wr']}% "
              f"| 2024 {agg['years']['2024']['totalR']:+.0f} 2025 {agg['years']['2025']['totalR']:+.0f} "
              f"2026 {agg['years']['2026']['totalR']:+.0f}", flush=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2))
    print(f"\n  wrote {OUT}")


if __name__ == "__main__":
    main()
