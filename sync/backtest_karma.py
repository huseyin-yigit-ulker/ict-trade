"""KARMA stream backtest: per symbol, pick the best-performing cell from the
2x2 matrix {MAIN(v1: B/C/D/E), IMPULSE(v2: B/C/D + extended D-excl)} x {full-TP, ½TP+BE}
and assemble the blended 'karma' stream from each symbol's winning cell.

Per symbol both engines run on the same 1h data (process-local D_EXCLUDE mutation,
save/restore), every signal is resolved on 1m under BOTH exit models, the 4 cell
totals are compared and the winner's rows become the karma rows. Outputs:
  out/karma_preview_2026_<SYM>.csv   (winning cell's trades, version='karma')
  out/karma_selection_2026.csv       (per-symbol matrix + chosen cell)
and, with --wipe-scope, the rows are upserted into trading_signals with
version='karma' (same safety contract as the v1-v4 backfills: a real run needs
an explicit --wipe-scope {none|year|all}; without it the run is CSV-only).

NB: E emitted 0 signals in 2026, so MAIN==IMPULSE except on the v2 D-exclusion
symbols (ADA/XAU/ETH) — most of the per-symbol choice comes from the exit model.
The blended total is IN-SAMPLE by construction (selection on the same data) — treat
it as an upper bound, not an expectation.

Usage:
  python sync/backtest_karma.py --year 2026                     # CSV-only preview
  python sync/backtest_karma.py --year 2026 --wipe-scope year   # real run -> DB
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import pandas as pd

import trade_sync_common as tsc           # adds backtest/ to sys.path
from ict import config as C               # noqa: E402

from engine import run_engine                                              # noqa: E402
from ict.strategies import strategy_b, strategy_c, strategy_d, strategy_e  # noqa: E402

from backfill_year import SYMBOLS         # MAIN production list

BASE_D_EXCL = set(C.D_EXCLUDE_SYMBOLS)                    # snapshot before any mutation
V2_EXTRA_D_EXCLUDE = {"ADAUSDT", "XAUUSDT", "ETHUSDT"}    # mirrors backfill_v2_year.py
MAIN_STRATS = [strategy_b, strategy_c, strategy_d, strategy_e]
IMP_STRATS = [strategy_b, strategy_c, strategy_d]

WARMUP_HOURS = 6000                       # ~250d detector warmup (same as backfills)
RESOLVED = ("closed_tp", "closed_sl")

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)


def _run_set(symbol, df1h, strats, d_excl):
    prev = C.D_EXCLUDE_SYMBOLS
    try:
        C.D_EXCLUDE_SYMBOLS = d_excl
        return run_engine(symbol, df1h, strategies=strats)
    finally:
        C.D_EXCLUDE_SYMBOLS = prev


def _resolve_rows(symbol, signals, df1m, win_start, win_end):
    """Resolve every in-window signal under BOTH exit models -> row dicts."""
    rows = []
    for s in signals:
        if not (win_start <= s.timestamp < win_end):
            continue
        prev = C.PARTIAL_TP_ENABLED
        try:
            C.PARTIAL_TP_ENABLED = False
            full = tsc.simulate(symbol, s.timestamp, s.direction, s.entry,
                                s.stop_loss, s.take_profit_1, df1m=df1m)
            C.PARTIAL_TP_ENABLED = True
            half = tsc.simulate(symbol, s.timestamp, s.direction, s.entry,
                                s.stop_loss, s.take_profit_1, df1m=df1m)
        finally:
            C.PARTIAL_TP_ENABLED = prev
        row = tsc.build_row(symbol, s.timestamp, s.direction, s.entry, s.stop_loss,
                            s.take_profit_1, full, strategy=s.strategy,
                            quality=s.quality, confluence_score=s.confluence_score)
        # keep the COMPLETE ½TP outcome too (not just pnl_r) so KARMA ½TP rows carry
        # the correct partial/breakeven exit time+price, not the full-TP ones.
        row["pnl_r_half"] = half["pnl_r"]
        row["status_half"] = half["status"]
        row["real_entry_time_half"] = half["real_entry_time"]
        row["exit_time_half"] = half["exit_time"]
        row["exit_price_half"] = half["exit_price"]
        rows.append(row)
    return rows


# helper columns carried on resolved rows that must NOT leak into a DB/CSV row
_HALF_HELPERS = ("pnl_r_half", "status_half", "real_entry_time_half",
                 "exit_time_half", "exit_price_half", "pnl_r_alt", "status_alt")


def _tot(rows, exit_model):
    key, skey = ("pnl_r", "status") if exit_model == "tam" else ("pnl_r_half", "status_half")
    vals = [r[key] for r in rows if r[skey] in RESOLVED and r[key] is not None]
    return sum(vals), len(vals), sum(1 for v in vals if v > 0)


def run_symbol(symbol, win_start, win_end):
    end = pd.Timestamp.now(tz="UTC")
    df1h = tsc.fetch_1h(symbol, win_start - pd.Timedelta(hours=WARMUP_HOURS), end)
    if df1h.empty:
        print(f"  {symbol:<13} SKIP (no data)", flush=True)
        return None
    df1m = tsc.fetch_1m(symbol, win_start - pd.Timedelta(hours=2), min(win_end, end))

    sigs_main = _run_set(symbol, df1h, MAIN_STRATS, BASE_D_EXCL)
    rows_main = _resolve_rows(symbol, sigs_main, df1m, win_start, win_end)
    n_e = sum(1 for s in sigs_main if "e_" in (s.strategy or "").lower())
    if symbol not in V2_EXTRA_D_EXCLUDE and n_e == 0:
        rows_imp = rows_main                      # identical sets -> reuse (E emitted 0)
    else:
        sigs_imp = _run_set(symbol, df1h, IMP_STRATS, BASE_D_EXCL | V2_EXTRA_D_EXCLUDE)
        rows_imp = _resolve_rows(symbol, sigs_imp, df1m, win_start, win_end)

    cells = {}
    for set_name, rows in (("main", rows_main), ("impulse", rows_imp)):
        for exit_model in ("tam", "yarim"):
            tot, n, w = _tot(rows, exit_model)
            cells[(set_name, exit_model)] = {"totR": tot, "n": n, "w": w, "rows": rows}

    # winner: max totR; ties prefer main + tam (production defaults)
    order = [("main", "tam"), ("impulse", "tam"), ("main", "yarim"), ("impulse", "yarim")]
    best = max(order, key=lambda k: cells[k]["totR"])
    bset, bexit = best

    karma_rows = []
    for r in cells[best]["rows"]:
        k = dict(r)
        k["version"] = "karma"
        if bexit == "yarim":                      # winner exit becomes the headline pnl
            k["pnl_r"], k["status"] = r["pnl_r_half"], r["status_half"]
            k["real_entry_time"] = r["real_entry_time_half"]
            k["exit_time"], k["exit_price"] = r["exit_time_half"], r["exit_price_half"]
            k["pnl_r_alt"], k["status_alt"] = r["pnl_r"], r["status"]
        else:
            k["pnl_r_alt"], k["status_alt"] = r["pnl_r_half"], r["status_half"]
        for c in _HALF_HELPERS:
            if c not in ("pnl_r_alt", "status_alt"):
                k.pop(c, None)
        k["karma_set"], k["karma_exit"] = bset, bexit
        karma_rows.append(k)

    # KARMA ½TP: SAME per-symbol source set as karma, but ALWAYS the ½TP+BE exit
    # (the analog of MAIN ½TP/v3 and IMPULSE ½TP/v4). Built from the same run so it
    # stays coherent with the karma rows above; exit time/price come from the ½TP sim.
    karma_half_rows = []
    for r in cells[best]["rows"]:
        k = dict(r)
        k["version"] = "karma_half"
        k["pnl_r"], k["status"] = r["pnl_r_half"], r["status_half"]
        k["real_entry_time"] = r["real_entry_time_half"]
        k["exit_time"], k["exit_price"] = r["exit_time_half"], r["exit_price_half"]
        for c in _HALF_HELPERS:
            k.pop(c, None)
        k["karma_set"], k["karma_exit"] = bset, "yarim"
        karma_half_rows.append(k)

    sel = {"symbol": symbol,
           "main_tam": round(cells[("main", "tam")]["totR"], 2),
           "main_yarim": round(cells[("main", "yarim")]["totR"], 2),
           "impulse_tam": round(cells[("impulse", "tam")]["totR"], 2),
           "impulse_yarim": round(cells[("impulse", "yarim")]["totR"], 2),
           "secim_set": bset, "secim_exit": bexit,
           "secim_totR": round(cells[best]["totR"], 2),
           "n": cells[best]["n"], "w": cells[best]["w"]}
    c = cells[best]
    print(f"  {symbol:<13} main: tam={cells[('main','tam')]['totR']:+7.2f} "
          f"yarim={cells[('main','yarim')]['totR']:+7.2f} | "
          f"imp: tam={cells[('impulse','tam')]['totR']:+7.2f} "
          f"yarim={cells[('impulse','yarim')]['totR']:+7.2f} "
          f"-> KARMA {bset}/{bexit} n={c['n']} totR={c['totR']:+.2f}", flush=True)
    return karma_rows, karma_half_rows, sel


def wipe(conn, scope, win_start, win_end, versions=("karma", "karma_half")) -> int:
    cur = conn.cursor()
    n = 0
    for ver in versions:
        if scope == "all":
            cur.execute(f"DELETE FROM {tsc.TABLE} WHERE version = %s", (ver,))
        elif scope == "year":
            cur.execute(
                f"DELETE FROM {tsc.TABLE} WHERE version = %s AND signal_time >= %s AND signal_time < %s",
                (ver, win_start.to_pydatetime(), win_end.to_pydatetime()))
        n += cur.rowcount
    conn.commit()
    cur.close()
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="*", default=SYMBOLS)
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--start", type=str, default=None)
    ap.add_argument("--end", type=str, default=None)
    ap.add_argument("--wipe-scope", choices=["none", "year", "all"], default=None,
                    help="real run -> DB upsert (omit = CSV-only preview)")
    args = ap.parse_args()

    now = pd.Timestamp.now(tz="UTC")
    win_start = pd.Timestamp(args.start, tz="UTC") if args.start else pd.Timestamp(f"{args.year}-01-01", tz="UTC")
    win_end = pd.Timestamp(args.end, tz="UTC") if args.end else min(pd.Timestamp(f"{args.year + 1}-01-01", tz="UTC"), now)

    print(f"=== KARMA backtest (per-symbol best of main/impulse x tam/½TP) | "
          f"{win_start.date()}..{win_end.date()} | {len(args.symbols)} sembol | CSV-only ===", flush=True)

    all_rows, half_rows, sels = [], [], []
    sel_fp = OUT / f"karma_selection_{args.year}.csv"
    for sym in args.symbols:
        res = run_symbol(sym, win_start, win_end)
        if res is None:
            continue
        rows, hrows, sel = res
        all_rows.extend(rows)
        half_rows.extend(hrows)
        sels.append(sel)
        for tag, rws in (("karma", rows), ("karma_half", hrows)):
            if rws:
                fp = OUT / f"{tag}_preview_{args.year}_{sym}.csv"
                with open(fp, "w", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=list(rws[0].keys()))
                    w.writeheader(); w.writerows(rws)
        # rewrite the selection table after EVERY symbol so a mid-run crash loses nothing
        with open(sel_fp, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(sels[0].keys()))
            w.writeheader(); w.writerows(sels)

    def _summary(label, rws):
        r = [x for x in rws if x["status"] in RESOLVED and x["pnl_r"] is not None]
        w = sum(1 for x in r if x["pnl_r"] > 0)
        tot = sum(x["pnl_r"] for x in r)
        print(f"{label}: sinyal={len(rws)} dolan={len(r)} W/L={w}/{len(r)-w} "
              f"WR={w/len(r)*100 if r else 0:.0f}% ortR={tot/len(r) if r else 0:+.3f} topR={tot:+.2f}")

    print()
    _summary("KARMA      (tam/seçili)", all_rows)
    _summary("KARMA ½TP  (hep ½TP)   ", half_rows)
    for nm, key_set in [("saf main/tam", "main_tam"), ("saf main/yarim", "main_yarim"),
                        ("saf impulse/tam", "impulse_tam"), ("saf impulse/yarim", "impulse_yarim")]:
        print(f"  {nm:<18}: {sum(s[key_set] for s in sels):+8.2f}R")
    print(f"\npreviews: {OUT}/karma_preview_* + karma_half_preview_* + karma_selection_{args.year}.csv")

    if args.wipe_scope is None:
        print("[CSV-only] --wipe-scope verilmedi, DB'ye yazilmadi.")
        return
    conn = tsc.backtest_conn()
    if args.wipe_scope in ("year", "all"):
        deleted = wipe(conn, args.wipe_scope, win_start, win_end)
        print(f"wiped {deleted} existing karma + karma_half rows (scope={args.wipe_scope})")
    n = tsc.upsert_rows(conn, all_rows + half_rows)
    conn.close()
    print(f"upserted {n} rows (karma + karma_half) into {tsc.TABLE}")


if __name__ == "__main__":
    main()
