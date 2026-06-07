"""Daily ETL: transfer resolved LIVE signals -> backtest trading_signals.

Runs end-of-day on the Oracle VM (needs Binance, which US GitHub runners can't reach).
"One day behind": today's signals are skipped (not yet resolved). Each run (re)processes
the last N=3 full days and upserts — so a signal still 'active' yesterday gets re-evaluated
and updated to its terminal status on a later run. A safety-net pass also re-resolves any
row still 'active' in trading_signals regardless of age.

Idempotent: upsert key (symbol, signal_time, trade_type, version) — re-running never
duplicates; it only updates status/exit/pnl when they change.

Usage:
  python sync/sync_daily.py                 # real run (cron)
  python sync/sync_daily.py --dry-run       # preview, no DB writes
  python sync/sync_daily.py --days 3 --no-active-rescan
"""
from __future__ import annotations

import argparse
from collections import defaultdict

import pandas as pd

import trade_sync_common as tsc

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT",
    "1000PEPEUSDT", "WIFUSDT", "SUIUSDT",
    "NEARUSDT", "FETUSDT", "ADAUSDT", "SUSDT",
    "ARBUSDT", "ORDIUSDT", "ONDOUSDT",
    "XAUUSDT", "XAGUSDT",
    # Stock-backed perps (underlying equities)
    "TSLAUSDT", "NVDAUSDT", "METAUSDT", "GOOGLUSDT",
    "AMZNUSDT", "COINUSDT", "PLTRUSDT", "MSTRUSDT",
]


def fetch_live_window(conn, w_start, w_end) -> list[dict]:
    """mode='live' signals with signal_time in [w_start, w_end)."""
    cur = conn.cursor()
    cur.execute("""
        SELECT symbol, signal_time, direction, entry, sl, tp, strategy, quality, confluence_score
        FROM ict_trade.signals
        WHERE mode = 'live' AND symbol = ANY(%s)
          AND signal_time >= %s AND signal_time < %s
        ORDER BY symbol, signal_time
    """, (SYMBOLS, w_start.to_pydatetime(), w_end.to_pydatetime()))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return rows


def fetch_active_rows(conn) -> list[dict]:
    """trading_signals rows still 'active' (entered, unresolved) — re-check them."""
    cur = conn.cursor()
    cur.execute(f"""
        SELECT symbol, signal_time, direction, entry_price AS entry, sl_price AS sl,
               tp_price AS tp, strategy, quality, confluence_score
        FROM {tsc.TABLE}
        WHERE version = %s AND lower(coalesce(status,'')) = 'active'
    """, (tsc.VERSION,))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3, help="trailing full days to (re)process")
    ap.add_argument("--no-active-rescan", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--symbols", nargs="*", default=None)
    args = ap.parse_args()
    symbols = set(args.symbols) if args.symbols else set(SYMBOLS)

    now = pd.Timestamp.now(tz="UTC")
    today0 = now.normalize()                       # today 00:00 UTC
    w_end = today0                                 # exclude today => "1 day behind"
    w_start = today0 - pd.Timedelta(days=args.days)
    print(f"=== daily sync | window [{w_start.date()} .. {w_end.date()}) "
          f"| dry_run={args.dry_run} ===")

    live = tsc.live_conn()
    work = fetch_live_window(live, w_start, w_end)
    live.close()
    print(f"  live mode='live' signals in window: {len(work)}")

    bt = tsc.backtest_conn()
    if not args.no_active_rescan:
        active = fetch_active_rows(bt)
        print(f"  active rows to re-check: {len(active)}")
        work += active

    # dedup by (symbol, signal_time-hour, direction); keep first (live window before active)
    seen, deduped = set(), []
    for w in work:
        if w["symbol"] not in symbols:
            continue
        st = pd.Timestamp(w["signal_time"]).tz_convert("UTC").floor("h")
        key = (w["symbol"], st, (w["direction"] or "").upper())
        if key in seen:
            continue
        seen.add(key)
        w["_st"] = st
        deduped.append(w)
    work = deduped

    by_sym = defaultdict(list)
    for w in work:
        by_sym[w["symbol"]].append(w)

    rows, status_counts, skipped = [], {}, 0
    for sym, items in by_sym.items():
        earliest = min(w["_st"] for w in items)
        df1m = tsc.fetch_1m(sym, earliest - pd.Timedelta(minutes=2), now)
        if df1m.empty:
            print(f"  {sym}: no klines, skipping {len(items)}")
            skipped += len(items)
            continue
        for w in items:
            st = w["_st"]
            outcome = tsc.simulate(sym, st, w["direction"],
                                   float(w["entry"]), float(w["sl"]), float(w["tp"]), df1m=df1m)
            status_counts[outcome["status"]] = status_counts.get(outcome["status"], 0) + 1
            rows.append(tsc.build_row(
                sym, st, w["direction"], w["entry"], w["sl"], w["tp"], outcome,
                strategy=w.get("strategy"), quality=w.get("quality"),
                confluence_score=w.get("confluence_score")))

    print(f"  resolved {len(rows)} rows, status={status_counts}, skipped={skipped}")

    if args.dry_run:
        for r in rows[:12]:
            print(f"    {r['symbol']} {r['signal_time']} {r['trade_type']} "
                  f"{r['status']} pnl_r={r['pnl_r']}")
        print(f"  [dry-run] no DB writes ({len(rows)} rows would upsert).")
        bt.close()
        return

    n = tsc.upsert_rows(bt, rows)
    bt.close()
    print(f"  upserted {n} rows into {tsc.TABLE}")


if __name__ == "__main__":
    main()
