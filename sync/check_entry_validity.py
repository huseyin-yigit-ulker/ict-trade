"""Check / enforce the pending-limit entry rule on the backtest table.

Rule (user): at signal fire (= signal bar CLOSE), price must be on the retrace
side of the entry limit:
  LONG  -> close > entry   (price above entry, limit waits below)
  SHORT -> close < entry   (price below entry, limit waits above)

Trades that violate this are setups where price had already passed the entry — not a
clean pending limit. By default this only REPORTS the impact (counts, R, WR, status
mix). Pass --delete to surgically remove ONLY the violating rows (valid rows untouched).

Usage:
  python sync/check_entry_validity.py                       # report only (v1 + v1-dyn)
  python sync/check_entry_validity.py --versions v1
  python sync/check_entry_validity.py --delete              # report + delete violators
"""
from __future__ import annotations

import argparse
import pandas as pd

import trade_sync_common as tsc           # adds backtest/ to sys.path

VERSIONS = ["v1", "v1-dyn"]
HISTORY_START = pd.Timestamp("2025-01-01", tz="UTC")


def _close_at(closes: pd.Series, st) -> float | None:
    ts = pd.Timestamp(st)
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    idx = closes.index
    if ts in idx:
        return float(closes.loc[ts])
    pos = idx.searchsorted(ts, side="right") - 1          # bar containing the signal
    return float(closes.iloc[pos]) if pos >= 0 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--versions", nargs="*", default=VERSIONS)
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--delete", action="store_true",
                    help="DELETE the violating rows (surgical; valid rows untouched)")
    args = ap.parse_args()
    only = set(args.symbols) if args.symbols else None

    conn = tsc.backtest_conn()
    end = pd.Timestamp.now(tz="UTC")

    for version in args.versions:
        cur = conn.cursor()
        cur.execute(f"SELECT DISTINCT symbol FROM {tsc.TABLE} WHERE version = %s", (version,))
        syms = sorted(r[0] for r in cur.fetchall())
        cur.close()
        if only:
            syms = [s for s in syms if s in only]

        agg = {"valid": 0, "invalid": 0, "rv": 0.0, "ri": 0.0, "vw": 0, "iw": 0, "miss": 0}
        inv_status = {}
        to_delete = []
        for sym in syms:
            df = tsc.fetch_1h(sym, HISTORY_START - pd.Timedelta(hours=200), end)
            if df.empty:
                continue
            closes = df["close"]
            cur = conn.cursor()
            cur.execute(
                f"SELECT signal_time, direction, entry_price, pnl_r, status "
                f"FROM {tsc.TABLE} WHERE version = %s AND symbol = %s", (version, sym))
            rows = cur.fetchall()
            cur.close()
            for st, direction, entry, pnl_r, status in rows:
                close = _close_at(closes, st)
                if close is None or entry is None:
                    agg["miss"] += 1
                    continue
                d = (direction or "").upper()
                ok = (close > float(entry)) if d == "LONG" else (close < float(entry))
                r = float(pnl_r or 0)
                win = 1 if r > 0 else 0
                if ok:
                    agg["valid"] += 1; agg["rv"] += r; agg["vw"] += win
                else:
                    agg["invalid"] += 1; agg["ri"] += r; agg["iw"] += win
                    inv_status[status] = inv_status.get(status, 0) + 1
                    to_delete.append((version, sym, st, direction))

        tot = agg["valid"] + agg["invalid"]
        if tot == 0:
            print(f"\n=== {version}: no rows ===")
            continue
        vw = agg["vw"] / agg["valid"] * 100 if agg["valid"] else 0
        iw = agg["iw"] / agg["invalid"] * 100 if agg["invalid"] else 0
        print(f"\n=== {version} | trades={tot} (miss={agg['miss']}) ===")
        print(f"  VALID (rule OK):   {agg['valid']:>4}  R={agg['rv']:+8.1f}  WR={vw:4.0f}%")
        print(f"  INVALID (violate): {agg['invalid']:>4}  R={agg['ri']:+8.1f}  WR={iw:4.0f}%   "
              f"({agg['invalid']/tot*100:.1f}% of all)")
        print(f"  -> valid-only TOTAL R = {agg['rv']:+.1f}  (was {agg['rv']+agg['ri']:+.1f})")
        print(f"  invalid status mix: {dict(sorted(inv_status.items(), key=lambda x:-x[1]))}")

        if args.delete and to_delete:
            dcur = conn.cursor()
            dcur.executemany(
                f"DELETE FROM {tsc.TABLE} WHERE version = %s AND symbol = %s "
                f"AND signal_time = %s AND direction = %s", to_delete)
            conn.commit()
            dcur.close()
            print(f"  >>> DELETED {len(to_delete)} violating rows from {version}")

    conn.close()


if __name__ == "__main__":
    main()
