"""Does our (trend-following ICT) strategy earn its R in TRENDING regimes?

Buckets each strategy's 2026 resolved signals by the 4h Efficiency-Ratio band AT
SIGNAL TIME (as-of lookup — the same no-lookahead gate the chop filter uses):

    strong  ER >= 0.50      mid  0.35–0.50      light  0.20–0.35      chop  < 0.20

This is a SAME-BAR conditioning question (how do signals fired in band X resolve),
not the forward-prediction question regime_accuracy.py answers. The chop study
already showed ER>=0.25 helps, so we expect R to concentrate in the higher bands.

It then evaluates the user's routing idea — run our trend strategy only in
strong+mid (ER>=0.35), hand light+chop to a range strategy — by splitting each
stream's R into the "trend zone" (kept) vs the "range zone" (handed off). Routing
only helps if a range strategy can beat what we'd give up in the range zone.
"""
from __future__ import annotations

import pandas as pd

import trade_sync_common as tsc
import regime

YEAR = 2026
VERSIONS = ["v1", "v2", "karma", "v3", "v4", "karma_half"]
LABEL = {"v1": "MAIN", "v2": "IMPULSE", "karma": "KARMA",
         "v3": "MAIN ½TP", "v4": "IMPULSE ½TP", "karma_half": "KARMA ½TP"}
RESOLVED = ("closed_tp", "closed_sl")
# band key by floor; order high->low
BANDS = [("strong", 0.50), ("mid", 0.35), ("light", 0.20), ("chop", 0.0)]


def band_of(er):
    if er is None:
        return "n/a"
    for k, lo in BANDS:
        if er >= lo:
            return k
    return "chop"


def fetch_resolved(conn, version, start, end):
    cur = conn.cursor()
    cur.execute(f"""SELECT symbol, signal_time, pnl_r FROM {tsc.TABLE}
        WHERE version=%s AND signal_time>=%s AND signal_time<%s
          AND status IN ('closed_tp','closed_sl') AND pnl_r IS NOT NULL""",
                (version, start.to_pydatetime(), end.to_pydatetime()))
    rows = [{"symbol": s, "signal_time": t, "pnl_r": float(r)} for s, t, r in cur.fetchall()]
    cur.close()
    return rows


def stat(rows):
    n = len(rows)
    if not n:
        return (0, 0.0, 0.0, 0.0)
    w = sum(1 for r in rows if r["pnl_r"] > 0)
    tot = sum(r["pnl_r"] for r in rows)
    return (n, w / n * 100, tot, tot / n)


def main():
    start = pd.Timestamp(f"{YEAR}-01-01", tz="UTC")
    end = pd.Timestamp(f"{YEAR + 1}-01-01", tz="UTC")
    conn = tsc.backtest_conn()

    all_rows = {v: fetch_resolved(conn, v, start, end) for v in VERSIONS}
    symbols = sorted({r["symbol"] for rows in all_rows.values() for r in rows})
    print(f"Building 4h ER for {len(symbols)} symbols...", flush=True)
    er = {s: regime.build_er(s, start - pd.Timedelta(days=30), pd.Timestamp.now(tz="UTC"))
          for s in symbols}

    for r_list in all_rows.values():
        for r in r_list:
            r["band"] = band_of(regime._er_at(er.get(r["symbol"]), r["signal_time"]))

    print(f"\n=== R by regime band at signal time ({YEAR}, resolved trades) ===")
    hdr = f'{"stream":<13}' + "".join(f'{b.upper():>26}' for b, _ in BANDS) + f'{"TOTAL":>16}'
    print(hdr)
    print(f'{"":13}' + "".join(f'{"n  WR%   totR   avgR":>26}' for _ in BANDS) + f'{"n    totR":>16}')
    for v in VERSIONS:
        rows = all_rows[v]
        line = f'{LABEL[v]:<13}'
        for b, _ in BANDS:
            n, wr, tot, avg = stat([r for r in rows if r["band"] == b])
            line += f'{n:>5}{wr:>4.0f}{tot:>8.1f}{avg:>+7.2f}  ' if n else f'{"·":>26}'
        n, wr, tot, avg = stat(rows)
        line += f'{n:>6}{tot:>9.1f}'
        print(line)

    # ---- Routing split: trend zone (strong+mid, ER>=0.35) vs range zone (light+chop) ----
    print(f"\n=== Routing split: TREND zone (ER>=0.35) vs RANGE zone (ER<0.35) ===")
    print(f'{"stream":<13}{"trend n":>9}{"trend R":>10}{"range n":>9}{"range R":>10}'
          f'{"all R":>9}{"drop range%R":>14}')
    for v in VERSIONS:
        rows = all_rows[v]
        trend = [r for r in rows if r["band"] in ("strong", "mid")]
        rng = [r for r in rows if r["band"] in ("light", "chop")]
        tn, _, tr, _ = stat(trend)
        rn, _, rr, _ = stat(rng)
        _, _, ar, _ = stat(rows)
        # what dropping the range zone alone (no range strategy) does to total R
        delta = tr - ar
        print(f'{LABEL[v]:<13}{tn:>9}{tr:>+10.1f}{rn:>9}{rr:>+10.1f}{ar:>+9.1f}{delta:>+14.1f}')

    # also report the current chop gate split (ER>=0.25) for reference
    print(f"\n=== For reference: current chop gate (keep ER>=0.25) ===")
    print(f'{"stream":<13}{"keep n":>8}{"keep R":>9}{"drop n":>8}{"drop R":>9}{"all R":>9}')
    for v in VERSIONS:
        rows = all_rows[v]
        keep, drop = [], []
        for r in rows:
            e = regime._er_at(er.get(r["symbol"]), r["signal_time"])
            (keep if (e is None or e >= regime.ER_MIN) else drop).append(r)
        kn, _, kr, _ = stat(keep)
        dn, _, dr, _ = stat(drop)
        _, _, ar, _ = stat(rows)
        print(f'{LABEL[v]:<13}{kn:>8}{kr:>+9.1f}{dn:>8}{dr:>+9.1f}{ar:>+9.1f}')

    conn.close()


if __name__ == "__main__":
    main()
