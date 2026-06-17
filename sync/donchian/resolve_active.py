"""Re-resolve stuck 'active' dch30_4h backtest rows. One-off DB repair (not an experiment).

Year-scoped 1m caches during the OOS backfill left some entered trades stuck 'active' — the
cached 1m window ended at the year boundary before the trade hit TP/SL. This re-resolves each
active row against a bounded fresh 1m window [signal, min(signal+45d, now)] so it closes to its
real TP/SL outcome. Genuinely-open recent trades (window reaches 'now' unresolved) correctly
stay active. Updates ict_trade.trading_signals in place (version='dch30_4h').

    python sync/donchian/resolve_active.py --dry-run
    python sync/donchian/resolve_active.py --apply
"""
from __future__ import annotations

import sys
import argparse
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import trade_sync_common as tsc           # noqa: E402

VERSION = "dch30_4h"
WINDOW = pd.Timedelta(days=45)


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    now = pd.Timestamp.now(tz="UTC")
    conn = tsc.backtest_conn(); cur = conn.cursor()
    cur.execute(f"""SELECT symbol, signal_time, direction, entry_price, sl_price, tp_price,
                   strategy, quality, confluence_score
                   FROM {tsc.TABLE}
                   WHERE version=%s AND lower(coalesce(status,'')) IN ('active','pending')
                   ORDER BY signal_time""", (VERSION,))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    print(f"=== {len(rows)} active/pending dch30_4h rows to re-resolve ===", flush=True)

    out, changed, still = [], 0, 0
    for w in rows:
        st = pd.Timestamp(w["signal_time"]); st = st.tz_localize("UTC") if st.tz is None else st.tz_convert("UTC")
        end = min(st + WINDOW, now)
        close_ts = st + pd.Timedelta(minutes=30)
        df1m = tsc.fetch_1m(w["symbol"], close_ts, end)
        res = tsc.simulate(w["symbol"], st, w["direction"], float(w["entry_price"]),
                           float(w["sl_price"]), float(w["tp_price"]), df1m=df1m, ltf_minutes=30,
                           expiry_minutes=180)
        new = res["status"]
        if new in ("closed_tp", "closed_sl"):
            changed += 1
        else:
            still += 1
        if new != "active" or (now - st) > WINDOW:        # log resolved + still-stuck-old
            age = (now - st).days
            print(f"  {w['symbol']:<10} {w['direction']:<5} {st:%Y-%m-%d %H:%M} age={age}d -> {new}"
                  f" R={res['pnl_r']}", flush=True)
        row = tsc.build_row(w["symbol"], st, w["direction"], w["entry_price"], w["sl_price"],
                            w["tp_price"], res, strategy=w.get("strategy"), quality=w.get("quality"),
                            confluence_score=w.get("confluence_score"))
        row["version"] = VERSION
        out.append(row)

    print(f"\n=== resolved {changed} to TP/SL, {still} still open/pending ===")
    if args.dry_run:
        print("[dry-run] no DB write."); conn.close(); return
    n = tsc.upsert_rows(conn, out); conn.close()
    print(f"  upserted {n} dch30_4h rows (in-place update)")


if __name__ == "__main__":
    main()
