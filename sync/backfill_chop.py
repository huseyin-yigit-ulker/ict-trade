"""Backfill the CHOP-filtered variants of every strategy stream.

A CHOP variant is its parent stream MINUS the signals fired while the symbol's 4h
was choppy (Efficiency Ratio < regime.ER_MIN). The chop filter only REMOVES signals
— it never changes entry/exit/resolution — so each `<base>_chop` stream is exactly
the parent's rows filtered by the regime gate. No engine re-run / no 1m re-fetch:
we read the parent rows straight from trading_signals and re-tag the survivors.

Parents -> chop version tag:
  v1 -> v1_chop   v2 -> v2_chop   v3 -> v3_chop   v4 -> v4_chop
  karma -> karma_chop   karma_half -> karma_half_chop
  opus  -> opus_chop    opus_half  -> opus_half_chop

Safety: real run needs --wipe-scope {year|all|none}; wipe touches ONLY the *_chop
versions. --dry-run prints the comparison with no DB writes.

Usage:
  python sync/backfill_chop.py --year 2026 --dry-run
  python sync/backfill_chop.py --year 2026 --wipe-scope year
"""
from __future__ import annotations

import argparse

import pandas as pd

import trade_sync_common as tsc
import regime

PARENTS = ["v1", "v2", "v3", "v4", "karma", "karma_half", "opus", "opus_half"]
# chop version tag per parent — kept <=10 chars (trading_signals.version is varchar(10)).
CHOP_TAG = {
    "v1": "v1_chop", "v2": "v2_chop", "v3": "v3_chop", "v4": "v4_chop",
    "karma": "kma_chop", "karma_half": "kmah_chop", "opus": "ops_chop", "opus_half": "opsh_chop",
}
RESOLVED = ("closed_tp", "closed_sl")


def fetch_rows(conn, version, w_start, w_end):
    cur = conn.cursor()
    cur.execute(f"""SELECT {", ".join(tsc._COLS)} FROM {tsc.TABLE}
        WHERE version=%s AND signal_time>=%s AND signal_time<%s""",
                (version, w_start.to_pydatetime(), w_end.to_pydatetime()))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return rows


def wipe(conn, scope, w_start, w_end):
    cur = conn.cursor(); n = 0
    for ver in [CHOP_TAG[b] for b in PARENTS]:
        if scope == "all":
            cur.execute(f"DELETE FROM {tsc.TABLE} WHERE version=%s", (ver,))
        elif scope == "year":
            cur.execute(f"DELETE FROM {tsc.TABLE} WHERE version=%s AND signal_time>=%s AND signal_time<%s",
                        (ver, w_start.to_pydatetime(), w_end.to_pydatetime()))
        n += cur.rowcount
    conn.commit(); cur.close()
    return n


def tot(rows):
    res = [r for r in rows if r["status"] in RESOLVED and r["pnl_r"] is not None]
    w = sum(1 for r in res if r["pnl_r"] > 0)
    return len(res), w, sum(float(r["pnl_r"]) for r in res)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--wipe-scope", choices=["none", "year", "all"], default=None)
    args = ap.parse_args()
    if not args.dry_run and args.wipe_scope is None:
        raise SystemExit("Real run requires --wipe-scope {none|year|all} (or --dry-run).")

    w_start = pd.Timestamp(f"{args.year}-01-01", tz="UTC")
    w_end = pd.Timestamp(f"{args.year + 1}-01-01", tz="UTC")
    er_start = w_start - pd.Timedelta(days=30)
    conn = tsc.backtest_conn()

    # gather parent rows + the union of symbols, build one ER series per symbol
    parent_rows = {v: fetch_rows(conn, v, w_start, w_end) for v in PARENTS}
    symbols = sorted({r["symbol"] for rows in parent_rows.values() for r in rows})
    print(f"=== CHOP backfill {args.year} | {len(symbols)} sembol | ER>={regime.ER_MIN} 4h | "
          f"dry_run={args.dry_run} ===", flush=True)
    er = {}
    for s in symbols:
        er[s] = regime.build_er(s, er_start, pd.Timestamp.now(tz="UTC"))

    all_chop = []
    print(f"\n{'stream':<14}{'parent':>22}   ->   {'chop (ER>=0.25)':>22}   tutulan")
    for base in PARENTS:
        rows = parent_rows[base]
        chop = []
        for r in rows:
            if regime.chop_ok(er.get(r["symbol"]), r["signal_time"]):
                k = dict(r); k["version"] = CHOP_TAG[base]; chop.append(k)
        all_chop.extend(chop)
        pn, pw, pr = tot(rows); cn, cw, cr = tot(chop)
        keep = len(chop) / len(rows) * 100 if rows else 0
        print(f"  {base:<12} n={pn:>4} WR={pw/pn*100 if pn else 0:3.0f}% topR={pr:+7.2f}"
              f"   ->   n={cn:>4} WR={cw/cn*100 if cn else 0:3.0f}% topR={cr:+7.2f}"
              f"   %{keep:.0f} sinyal", flush=True)

    if args.dry_run:
        print(f"\n[dry-run] {len(all_chop)} _chop satırı yazılacaktı — DB'ye yazılmadı.")
        conn.close(); return
    if args.wipe_scope in ("year", "all"):
        print(f"\nwiped {wipe(conn, args.wipe_scope, w_start, w_end)} existing *_chop rows")
    n = tsc.upsert_rows(conn, all_chop)
    conn.close()
    print(f"upserted {n} *_chop rows into {tsc.TABLE}")


if __name__ == "__main__":
    main()
