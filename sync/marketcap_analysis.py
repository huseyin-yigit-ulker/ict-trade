"""Does the TOTAL3 market-breadth regime separate our winning trades from losers —
and does it add ANYTHING the per-symbol ER band doesn't already say?

Mirror of regime_route_analysis.py, but the conditioning variable is GLOBAL market
breadth (sync/marketcap.regime_at on the TOTAL3 cap proxy) instead of the symbol's
own 4h ER. One breadth series conditions every signal (TOTAL is a market metric).

Three questions, in order of how much they should move you:

  1. SEPARATION  — bucket each crypto stream's resolved R by breadth regime at
     signal time (risk_on / neutral / risk_off). If breadth has edge, risk_off R
     should be visibly worse than risk_on R.

  2. ORTHOGONALITY (the overfit guard) — cross-tab R by (ER band) x (breadth
     regime). If every column tells the same story as the ER band alone, breadth
     is just an echo of ER and adds nothing — DO NOT ship it as a gate. It earns a
     place only if it splits R *within* an ER band (e.g. light-band trades are good
     in risk_on but bad in risk_off).

  3. GATING SPLIT — what dropping risk_off signals does to each stream's total R,
     so you can see the trade-off before wiring any gate.

CRYPTO-ONLY: metals (XAU/XAG) and stock-backed perps are excluded — a crypto
market-cap regime says nothing about them. Same as the chop study, this is a
SAME-BAR conditioning question, not forward prediction. And like every gate in
this repo: validate on 2025 OOS before trusting the 2026 numbers (KARMA and
regime-sizing both looked great in-sample and failed out-of-sample).
"""
from __future__ import annotations

import argparse

import pandas as pd

import trade_sync_common as tsc
import regime
import marketcap as mc

# Versions present with closed crypto trades in the backtest DB. v2/karma live in
# the daily-sync DB, not this snapshot — add them here if you backfill them.
VERSIONS = ["v1", "opus", "range"]
LABEL = {"v1": "MAIN", "opus": "OPUS", "range": "RANGE",
         "v2": "IMPULSE", "karma": "KARMA"}

# Non-crypto symbols: a crypto market-cap regime is meaningless for these.
NON_CRYPTO = {
    "XAUUSDT", "XAGUSDT",
    "NVDAUSDT", "METAUSDT", "AMZNUSDT", "COINUSDT", "MSTRUSDT",
    "CRCLUSDT", "PLTRUSDT", "TSLAUSDT", "INTCUSDT", "HOODUSDT",
    "MSFTUSDT", "AVGOUSDT", "BABAUSDT", "BXUSDT", "HPEUSDT",
    "AMATUSDT", "CRWDUSDT", "CRDOUSDT", "AAOIUSDT", "IWMUSDT",
}
REGIMES = ["risk_on", "neutral", "risk_off", "unknown"]
ER_BANDS = [("strong", 0.50), ("mid", 0.35), ("light", 0.20), ("chop", 0.0)]


def er_band(er):
    if er is None:
        return "n/a"
    for k, lo in ER_BANDS:
        if er >= lo:
            return k
    return "chop"


def fetch_resolved(conn, version, start, end):
    cur = conn.cursor()
    cur.execute(f"""SELECT symbol, signal_time, pnl_r FROM {tsc.TABLE}
        WHERE version=%s AND signal_time>=%s AND signal_time<%s
          AND status IN ('closed_tp','closed_sl') AND pnl_r IS NOT NULL""",
                (version, start.to_pydatetime(), end.to_pydatetime()))
    rows = [{"symbol": s, "signal_time": t, "pnl_r": float(r)}
            for s, t, r in cur.fetchall() if s not in NON_CRYPTO]
    cur.close()
    return rows


def stat(rows):
    n = len(rows)
    if not n:
        return (0, 0.0, 0.0, 0.0)
    w = sum(1 for r in rows if r["pnl_r"] > 0)
    tot = sum(r["pnl_r"] for r in rows)
    return (n, w / n * 100, tot, tot / n)


def _write_json(year, all_rows, pooled):
    """Merge this year's analysis into src/assets/data/marketcap_analysis.json (the
    UI reads it). Keyed by year so 2025 + 2026 runs build one combined file."""
    import json
    from pathlib import Path

    asset = Path(__file__).resolve().parents[1] / "src" / "assets" / "data" / "marketcap_analysis.json"
    doc = json.loads(asset.read_text()) if asset.exists() else {"years": {}}

    ortho = []
    for b, _ in ER_BANDS:
        brows = [r for r in pooled if r["er_band"] == b]
        cells = {}
        for g in REGIMES[:3]:
            n, wr, tot, avg = stat([r for r in brows if r["regime"] == g])
            cells[g] = {"n": n, "totR": round(tot, 1), "avgR": round(avg, 2)}
        ortho.append({"band": b, "cells": cells})

    sep = {}
    for v in VERSIONS:
        rows = all_rows[v]
        row = {}
        for g in REGIMES[:3]:
            n, wr, tot, avg = stat([r for r in rows if r["regime"] == g])
            row[g] = {"n": n, "totR": round(tot, 1), "avgR": round(avg, 2)}
        n, wr, tot, avg = stat(rows)
        row["total"] = {"n": n, "totR": round(tot, 1)}
        sep[LABEL[v]] = row

    doc["years"][str(year)] = {"orthogonality": ortho, "separation": sep,
                               "in_sample": year == 2026}
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_text(json.dumps(doc, indent=2))
    print(f"\nwrote {asset.relative_to(asset.parents[3])}  (year {year})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--json", action="store_true", help="also write the UI asset JSON")
    args = ap.parse_args()

    start = pd.Timestamp(f"{args.year}-01-01", tz="UTC")
    end = pd.Timestamp(f"{args.year + 1}-01-01", tz="UTC")
    now = pd.Timestamp.now(tz="UTC")
    conn = tsc.backtest_conn()

    all_rows = {v: fetch_resolved(conn, v, start, end) for v in VERSIONS}
    symbols = sorted({r["symbol"] for rows in all_rows.values() for r in rows})

    print("Building TOTAL3 market-cap regime (proxy)...", flush=True)
    mcdf = mc.build_marketcap(start - pd.Timedelta(days=20), now)
    if mcdf is None:
        raise SystemExit("no market-cap data")

    print(f"Building 4h ER for {len(symbols)} crypto symbols...", flush=True)
    er = {s: regime.build_er(s, start - pd.Timedelta(days=30), now) for s in symbols}

    for rows in all_rows.values():
        for r in rows:
            r["regime"] = mc.regime_at(mcdf, r["signal_time"])
            r["er_band"] = er_band(regime._er_at(er.get(r["symbol"]), r["signal_time"]))

    # ---- 1. SEPARATION: R by breadth regime at signal time -------------------
    print(f"\n=== 1. R by TOTAL3 breadth regime at signal time ({args.year}, crypto) ===")
    hdr = f'{"stream":<10}' + "".join(f'{g.upper():>22}' for g in REGIMES) + f'{"TOTAL":>14}'
    print(hdr)
    print(f'{"":10}' + "".join(f'{"n  WR%  totR  avgR":>22}' for _ in REGIMES) + f'{"n   totR":>14}')
    for v in VERSIONS:
        rows = all_rows[v]
        line = f'{LABEL[v]:<10}'
        for g in REGIMES:
            n, wr, tot, avg = stat([r for r in rows if r["regime"] == g])
            line += f'{n:>4}{wr:>4.0f}{tot:>7.1f}{avg:>+6.2f} ' if n else f'{"·":>22}'
        n, wr, tot, avg = stat(rows)
        line += f'{n:>5}{tot:>9.1f}'
        print(line)

    # ---- 2. ORTHOGONALITY: pooled R by (ER band) x (breadth regime) ----------
    pooled = [r for rows in all_rows.values() for r in rows]
    print(f"\n=== 2. Orthogonality — pooled R by ER band x breadth regime ===")
    print("   (does breadth split R WITHIN an ER band? if rows read the same across")
    print("    columns, breadth just echoes ER and adds nothing.)")
    print(f'{"ER band":<10}' + "".join(f'{g.upper():>20}' for g in REGIMES[:3]) + f'{"row TOTAL":>14}')
    print(f'{"":10}' + "".join(f'{"n   totR  avgR":>20}' for _ in REGIMES[:3]) + f'{"n   totR":>14}')
    for b, _ in ER_BANDS:
        line = f'{b:<10}'
        brows = [r for r in pooled if r["er_band"] == b]
        for g in REGIMES[:3]:
            n, wr, tot, avg = stat([r for r in brows if r["regime"] == g])
            line += f'{n:>5}{tot:>8.1f}{avg:>+6.2f} ' if n else f'{"·":>20}'
        n, _, tot, _ = stat(brows)
        line += f'{n:>6}{tot:>8.1f}'
        print(line)

    # ---- 3. GATING SPLIT: drop risk_off ------------------------------------
    print(f"\n=== 3. Gating split: keep (not risk_off) vs drop (risk_off) ===")
    print(f'{"stream":<10}{"keep n":>8}{"keep R":>9}{"drop n":>8}{"drop R":>9}'
          f'{"all R":>9}{"Δ vs all":>10}')
    for v in VERSIONS:
        rows = all_rows[v]
        keep = [r for r in rows if r["regime"] != "risk_off"]
        drop = [r for r in rows if r["regime"] == "risk_off"]
        kn, _, kr, _ = stat(keep)
        dn, _, dr, _ = stat(drop)
        _, _, ar, _ = stat(rows)
        print(f'{LABEL[v]:<10}{kn:>8}{kr:>+9.1f}{dn:>8}{dr:>+9.1f}{ar:>+9.1f}{kr - ar:>+10.1f}')

    if args.json:
        _write_json(args.year, all_rows, pooled)

    conn.close()
    print("\nNB: 2026 is IN-SAMPLE. Re-run with --year 2025 before trusting any of this.")


if __name__ == "__main__":
    main()
