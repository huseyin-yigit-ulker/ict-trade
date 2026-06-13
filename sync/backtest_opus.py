"""Backtest the OPUS stream(s) -> trading_signals (version='opus' + 'opus_half').

OPUS = MAIN signal set (strategies B/C/D/E) restricted PER SYMBOL to the WEEKDAY NY
session(s) where that symbol's signals carried an edge in 2026 (the sembol × seans
analysis; allowlist in sync/opus_map.py). Symbols not in the map are dropped. Same
engine / detectors / 1m resolution as the v1 main backfill — the ONLY difference is
the per-symbol weekday-session filter on emission.

Each allowed signal is resolved under BOTH exit models in one pass:
  version='opus'      -> full-TP exit
  version='opus_half' -> partial-TP + breakeven exit (½TP) — same signals/gate.

Safety: never deletes in --dry-run; a real run needs --wipe-scope {year|all|none}.
  wipe touches ONLY version='opus' and 'opus_half'.

Usage:
  python sync/backtest_opus.py --symbols BTCUSDT --start 2026-05-01 --end 2026-06-01 --dry-run
  python sync/backtest_opus.py --year 2026 --wipe-scope year
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

from opus_map import OPUS_MAP, opus_allows, opus_session                   # noqa: E402

VERSION = "opus"
HALF_VERSION = "opus_half"                 # same signals/gate, ½TP+BE exit
DAG_STRATS = [strategy_b, strategy_c, strategy_d, strategy_e]   # MAIN set
WARMUP_HOURS = 6000
SYMBOLS = sorted(OPUS_MAP)                 # only the symbols OPUS actually trades

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)


def build_symbol_rows(symbol, win_start, win_end):
    """Returns (rows_full, rows_half, info). Each allowed signal is resolved under
    BOTH exit models so OPUS (full-TP) and OPUS ½TP (partial-TP+BE) come from the
    same run — coherent entries, correct per-model exit time/price."""
    if symbol not in OPUS_MAP:
        return [], [], {"symbol": symbol, "bars": 0, "signals": 0, "skipped": True}
    end = pd.Timestamp.now(tz="UTC")
    df = tsc.fetch_1h(symbol, win_start - pd.Timedelta(hours=WARMUP_HOURS), end)
    if df.empty:
        return [], [], {"symbol": symbol, "bars": 0, "signals": 0, "skipped": True}

    signals = run_engine(symbol, df, strategies=DAG_STRATS)
    df1m = tsc.fetch_1m(symbol, win_start - pd.Timedelta(hours=2), min(win_end, end))
    rows, half_rows, status_counts = [], [], {}
    for s in signals:
        if not (win_start <= s.timestamp < win_end):
            continue
        if not opus_allows(symbol, s.timestamp):       # <-- per-symbol weekday NY-session gate
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
        status_counts[full["status"]] = status_counts.get(full["status"], 0) + 1
        sess = opus_session(s.timestamp)
        base = dict(strategy=s.strategy, quality=s.quality, confluence_score=s.confluence_score)
        row = tsc.build_row(symbol, s.timestamp, s.direction, s.entry, s.stop_loss,
                            s.take_profit_1, full, **base)
        row["version"] = VERSION; row["session"] = sess
        rows.append(row)
        hrow = tsc.build_row(symbol, s.timestamp, s.direction, s.entry, s.stop_loss,
                             s.take_profit_1, half, **base)
        hrow["version"] = HALF_VERSION; hrow["session"] = sess
        half_rows.append(hrow)
    return rows, half_rows, {"symbol": symbol, "bars": len(df), "signals": len(rows),
                             "skipped": False, "status": status_counts}


def wipe(conn, scope, win_start, win_end) -> int:
    cur = conn.cursor()
    n = 0
    for ver in (VERSION, HALF_VERSION):
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
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--wipe-scope", choices=["none", "year", "all"], default=None)
    args = ap.parse_args()

    if not args.dry_run and args.wipe_scope is None:
        raise SystemExit("Real run requires --wipe-scope {none|year|all} (or --dry-run).")

    now = pd.Timestamp.now(tz="UTC")
    win_start = pd.Timestamp(args.start, tz="UTC") if args.start else pd.Timestamp(f"{args.year}-01-01", tz="UTC")
    win_end = pd.Timestamp(args.end, tz="UTC") if args.end else min(pd.Timestamp(f"{args.year + 1}-01-01", tz="UTC"), now)

    print(f"=== {args.year} OPUS backfill (MAIN set + per-symbol NY-session gate) | "
          f"{win_start.date()}..{win_end.date()} | {len(args.symbols)} sembol | "
          f"dry_run={args.dry_run} | wipe={args.wipe_scope} ===")

    all_rows, half_rows = [], []
    for sym in args.symbols:
        rows, hrows, info = build_symbol_rows(sym, win_start, win_end)
        all_rows.extend(rows); half_rows.extend(hrows)
        sess = "/".join(OPUS_MAP.get(sym, []))
        tag = "SKIP" if info["skipped"] else f"{info['signals']} signals {info.get('status', {})}"
        print(f"  {sym:<12} [{sess:<5}] bars={info['bars']:<6} -> {tag}")
        if args.dry_run:
            for tagv, rws in ((VERSION, rows), (HALF_VERSION, hrows)):
                if rws:
                    fp = OUT / f"{tagv}_preview_{args.year}_{sym}.csv"
                    with open(fp, "w", newline="") as f:
                        w = csv.DictWriter(f, fieldnames=list(rws[0].keys()))
                        w.writeheader(); w.writerows(rws)

    def _summary(label, rws):
        r = [x for x in rws if x["status"] in ("closed_tp", "closed_sl") and x["pnl_r"] is not None]
        w = sum(1 for x in r if x["pnl_r"] > 0)
        tot = sum(x["pnl_r"] for x in r)
        print(f"{label}: sinyal={len(rws)} dolan={len(r)} W/L={w}/{len(r)-w} "
              f"WR={w/len(r)*100 if r else 0:.0f}% ortR={tot/len(r) if r else 0:+.3f} topR={tot:+.2f}")
    print()
    _summary("OPUS     (tam TP)", all_rows)
    _summary("OPUS ½TP (½TP+BE)", half_rows)

    if args.dry_run:
        print(f"\n[dry-run] previews in {OUT}/ — no DB writes.")
        return
    conn = tsc.backtest_conn()
    if args.wipe_scope in ("year", "all"):
        deleted = wipe(conn, args.wipe_scope, win_start, win_end)
        print(f"wiped {deleted} existing opus + opus_half rows (scope={args.wipe_scope})")
    n = tsc.upsert_rows(conn, all_rows + half_rows)
    conn.close()
    print(f"upserted {n} rows (opus + opus_half) into {tsc.TABLE}")


if __name__ == "__main__":
    main()
