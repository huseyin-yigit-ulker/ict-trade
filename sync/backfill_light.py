"""Backfill the LIGHT band-pass variants of the core/½TP/karma streams.

The 2026 regime-routing audit (sync/regime_route_analysis.py) found our
trend-following ICT signals actually earn ~85-90% of their R in the LIGHT regime
(4h Efficiency Ratio in [0.20, 0.35)); strong/mid trend is break-even-to-negative
and the mid band is an outright loser for MAIN. So a LIGHT variant keeps ONLY the
signals fired while the symbol's 4h was in the light band — the opposite move to
"trend in trend." It never changes entry/exit/resolution; it only filters the
parent's rows, then re-tags the survivors (no engine re-run / no 1m re-fetch).

Scope = the streams the band edge was measured on (NOT opus, a session gate of its
own):
  v1 -> v1_light   v2 -> v2_light   v3 -> v3_light   v4 -> v4_light
  karma -> kma_light   karma_half -> kmah_light

Safety: real run needs --wipe-scope {year|all|none}; wipe touches ONLY the *_light
versions. --dry-run prints the comparison with no DB writes.

Usage:
  python sync/backfill_light.py --year 2026 --dry-run
  python sync/backfill_light.py --year 2026 --wipe-scope year
"""
from __future__ import annotations

import argparse

import pandas as pd

import trade_sync_common as tsc
import regime

PARENTS = ["v1", "v2", "v3", "v4", "karma", "karma_half"]
# light version tag per parent — kept <=10 chars (trading_signals.version is varchar(10)).
LIGHT_TAG = {
    "v1": "v1_light", "v2": "v2_light", "v3": "v3_light", "v4": "v4_light",
    "karma": "kma_light", "karma_half": "kmah_light",
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
    for ver in [LIGHT_TAG[b] for b in PARENTS]:
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

    parent_rows = {v: fetch_rows(conn, v, w_start, w_end) for v in PARENTS}
    symbols = sorted({r["symbol"] for rows in parent_rows.values() for r in rows})
    print(f"=== LIGHT backfill {args.year} | {len(symbols)} sembol | "
          f"{regime.LIGHT_LO}<=ER<{regime.LIGHT_HI} 4h | dry_run={args.dry_run} ===", flush=True)
    er = {}
    for s in symbols:
        er[s] = regime.build_er(s, er_start, pd.Timestamp.now(tz="UTC"))

    all_light = []
    print(f"\n{'stream':<14}{'parent':>22}   ->   {'light [0.20,0.35)':>22}   tutulan")
    for base in PARENTS:
        rows = parent_rows[base]
        light = []
        for r in rows:
            if regime.light_ok(er.get(r["symbol"]), r["signal_time"]):
                k = dict(r); k["version"] = LIGHT_TAG[base]; light.append(k)
        all_light.extend(light)
        pn, pw, pr = tot(rows); cn, cw, cr = tot(light)
        keep = len(light) / len(rows) * 100 if rows else 0
        print(f"  {base:<12} n={pn:>4} WR={pw/pn*100 if pn else 0:3.0f}% topR={pr:+7.2f}"
              f"   ->   n={cn:>4} WR={cw/cn*100 if cn else 0:3.0f}% topR={cr:+7.2f}"
              f"   %{keep:.0f} sinyal", flush=True)

    if args.dry_run:
        print(f"\n[dry-run] {len(all_light)} _light satırı yazılacaktı — DB'ye yazılmadı.")
        conn.close(); return
    if args.wipe_scope in ("year", "all"):
        print(f"\nwiped {wipe(conn, args.wipe_scope, w_start, w_end)} existing *_light rows")
    n = tsc.upsert_rows(conn, all_light)
    conn.close()
    print(f"upserted {n} *_light rows into {tsc.TABLE}")


if __name__ == "__main__":
    main()
