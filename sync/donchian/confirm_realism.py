"""Directional-entry-confirmation REALISM stress test — EXPERIMENT (no DB write).

The shipped streams gate a breakout on ENTRY_CONFIRM_BUF (0.5R): take the trade only if price
extends +0.5R FAVOURABLY before -0.5R adversely. But the recorded entry stays at the breakout
close, and the limit fill (low<=entry) is resolved INDEPENDENTLY of the gate — so a trade can
fill BEFORE the confirmation prints. This re-simulates each ALREADY-CONFIRMED signal on 1m to
quantify how optimistic that entry model is.

Anchored on the SHIPPED confirmed set: it reads the real `dch30_4h` rows from the backtest DB
(already gated, exact entry/sl/tp) and only re-derives the entry-shift effect on 1m. Models:

  baseline : entry = breakout close (ship). Recomputed GROSS here for apples-to-apples; the DB's
             net pnl_r is printed alongside as a cross-check.
  variantA : realistic "market-enter on confirmation" — real entry = the +0.5R level (where you'd
             actually act). SL/TP prices unchanged; R measured against the ACTUAL risk taken
             (entryA->SL = 1.5R), i.e. RR collapses 4 -> ~2.33. Re-simulated (it also catches the
             runaway breakouts the limit-fill baseline cancels), plus a raw-R_orig view.
  variantB : causal limit fill — entry stays at the breakout close (RR4 kept), but the fill may
             only count AT/AFTER the confirmation bar. Isolates the fill-before-confirm optimism.

Scope: cached-1m universe (liquid crypto + XAU), 2026. Gross R (no fee) so the three models are
apples-to-apples.

    python sync/donchian/confirm_realism.py
    python sync/donchian/confirm_realism.py --version dch30_4h --start 2026-01-01 --buf 0.5
"""
from __future__ import annotations

import os
import sys
import pickle
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import dotenv_values
import psycopg2

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))
sys.path.insert(0, str(_HERE.parent))
import trade_sync_common as tsc              # noqa: E402
import strategy as strat                     # noqa: E402
from ict import config as C                  # noqa: E402

CACHE = Path(os.environ.get("DONCHIAN_1M_CACHE", "/tmp/donchian1m_cache"))
EXPIRY_MIN = tsc.EXPIRY_MINUTES               # entry-fill / confirm window (180)
MAX_HOLD = strat.MAX_HOLD_MINUTES             # 3-day time stop


def cached_symbols():
    return sorted(p.stem for p in CACHE.glob("*.pkl"))


def load_1m(sym):
    df = pickle.loads((CACHE / f"{sym}.pkl").read_bytes())
    if df.index.tz is None:
        df = df.copy(); df.index = df.index.tz_localize("UTC")
    return df


def fetch_confirmed(version, syms, start, end):
    env = dotenv_values(_HERE.parents[2] / ".env")
    conn = psycopg2.connect(env["BACKTESTING_DB_CONNECTION_STRING"])
    cur = conn.cursor()
    cur.execute(
        f"""select symbol, direction, trade_type, signal_time, entry_price, sl_price, tp_price, status, pnl_r
           from {tsc.TABLE}
           where version=%s and signal_time>=%s and signal_time<%s and symbol = ANY(%s)
             and lower(status) in ('closed_tp','closed_sl')
           order by symbol, signal_time""",
        (version, start, end, list(syms)),
    )
    rows = cur.fetchall()
    cur.close(); conn.close()
    out = []
    for sym, direction, tt, st, e, sl, tp, status, pnl in rows:
        d = (direction or tt or "").lower()
        d = "long" if d in ("long", "buy") else "short"
        out.append({"symbol": sym, "dir": d, "ts": pd.Timestamp(st),
                    "entry": float(e), "sl": float(sl), "tp": float(tp),
                    "status": status.lower(), "pnl_r": float(pnl) if pnl is not None else 0.0})
    return out


# ---- 1m resolvers (gross R, intrabar) ------------------------------------------------------
def confirm_bar(H, L, p0, p1, long, fav, adv):
    for i in range(p0, p1):
        adv_hit = (L[i] <= adv) if long else (H[i] >= adv)
        fav_hit = (H[i] >= fav) if long else (L[i] <= fav)
        if adv_hit:
            return None
        if fav_hit:
            return i
    return None


def limit_resolve(H, L, Cl, idxv, start_p, long, entry, sl, tp, risk, expiry_min, max_hold):
    n = len(H); sign = 1.0 if long else -1.0
    t0 = idxv[start_p]; entry_p = None
    for i in range(start_p, n):
        if (idxv[i] - t0) > np.timedelta64(expiry_min, "m"):
            return "expired", 0.0
        et = (L[i] <= entry) if long else (H[i] >= entry)
        tpt = (H[i] >= tp) if long else (L[i] <= tp)
        slt = (L[i] <= sl) if long else (H[i] >= sl)
        if not et and (tpt or slt):
            return "invalidated", 0.0
        if et:
            entry_p = i; break
    if entry_p is None:
        return "expired", 0.0
    te = idxv[entry_p]
    for j in range(entry_p, n):
        tpt = (H[j] >= tp) if long else (L[j] <= tp)
        slt = (L[j] <= sl) if long else (H[j] >= sl)
        if (tpt and slt) or slt:
            return "sl", (sl - entry) / risk * sign
        if tpt:
            return "tp", (tp - entry) / risk * sign
        if (idxv[j] - te) > np.timedelta64(max_hold, "m"):
            return "time", (Cl[j] - entry) / risk * sign
    return "active", 0.0


def market_resolve(H, L, Cl, idxv, start_p, long, entry, sl, tp, risk, max_hold):
    n = len(H); sign = 1.0 if long else -1.0; te = idxv[start_p]
    for j in range(start_p, n):
        tpt = (H[j] >= tp) if long else (L[j] <= tp)
        slt = (L[j] <= sl) if long else (H[j] >= sl)
        if (tpt and slt) or slt:
            return "sl", (sl - entry) / risk * sign
        if tpt:
            return "tp", (tp - entry) / risk * sign
        if (idxv[j] - te) > np.timedelta64(max_hold, "m"):
            return "time", (Cl[j] - entry) / risk * sign
    return "active", 0.0


def agg(rs):
    closed = [r for r in rs if r is not None]
    n = len(closed); wins = [r for r in closed if r > 0]; tot = sum(closed)
    gw = sum(wins); gl = -sum(r for r in closed if r <= 0)
    return {"n": n, "wr": 100 * len(wins) / n if n else 0.0, "totR": tot,
            "avg": tot / n if n else 0.0, "pf": (gw / gl) if gl > 0 else float("inf")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="dch30_4h")
    ap.add_argument("--start", default="2026-01-01")
    ap.add_argument("--end", default="2026-12-31")
    ap.add_argument("--buf", type=float, default=None)
    args = ap.parse_args()

    buf = args.buf if args.buf is not None else getattr(C, "ENTRY_CONFIRM_BUF", 0.5)
    syms = cached_symbols()
    sigs = fetch_confirmed(args.version, syms, args.start, args.end)
    print(f"=== ENTRY-CONFIRM REALISM | {args.version} (shipped confirmed set) | buf={buf} | "
          f"[{args.start}..{args.end}) | {len(syms)} cached syms | {len(sigs)} trades ===", flush=True)

    acc = {"dbnet": [], "base": [], "vA": [], "vAraw": [], "vB": []}
    by_sym = {}
    no_confirm = 0
    m1 = {}
    for s in sigs:
        sym = s["symbol"]
        if sym not in m1:
            df = load_1m(sym)
            m1[sym] = (df.index.values, df["high"].values, df["low"].values, df["close"].values)
        idxv, H, L, Cl = m1[sym]
        long = s["dir"] == "long"
        entry, sl, tp = s["entry"], s["sl"], s["tp"]
        risk = abs(entry - sl)
        if risk <= 0:
            continue
        close_ts = np.datetime64(s["ts"].tz_convert("UTC").tz_localize(None)) + np.timedelta64(30, "m")
        p0 = int(np.searchsorted(idxv, close_ts))
        p1 = int(np.searchsorted(idxv, close_ts + np.timedelta64(EXPIRY_MIN, "m")))
        if p0 >= len(idxv) or p1 <= p0:
            continue
        fav = entry + buf * risk if long else entry - buf * risk
        adv = entry - buf * risk if long else entry + buf * risk
        cidx = confirm_bar(H, L, p0, p1, long, fav, adv)
        if cidx is None:
            no_confirm += 1
            continue
        acc["dbnet"].append(s["pnl_r"])
        st, r = limit_resolve(H, L, Cl, idxv, p0, long, entry, sl, tp, risk, EXPIRY_MIN, MAX_HOLD)
        if st in ("tp", "sl", "time"):
            acc["base"].append(r)
        riskA = abs(fav - sl)
        stA, rA = market_resolve(H, L, Cl, idxv, cidx, long, fav, sl, tp, riskA, MAX_HOLD)
        if stA in ("tp", "sl", "time"):
            acc["vA"].append(rA); acc["vAraw"].append(rA * riskA / risk)
        stB, rB = limit_resolve(H, L, Cl, idxv, cidx, long, entry, sl, tp, risk, EXPIRY_MIN, MAX_HOLD)
        if stB in ("tp", "sl", "time"):
            acc["vB"].append(rB)
        by_sym.setdefault(sym, []).append(r if st in ("tp", "sl", "time") else 0.0)

    print(f"  re-confirmed on cached 1m: {len(acc['dbnet'])}/{len(sigs)} "
          f"(failed my confirm reproduction: {no_confirm})\n")
    print(f"  {'model':<28} {'n':>5} {'WR':>6} {'totR':>9} {'avgR':>7} {'PF':>6}")
    print("  " + "-" * 66)
    rows = [
        ("DB net (shipped, w/ fee)", acc["dbnet"]),
        ("baseline gross (entry@close)", acc["base"]),
        ("variantA norm (entry@+0.5R)", acc["vA"]),
        ("variantA raw (R_orig units)", acc["vAraw"]),
        ("variantB (causal fill@close)", acc["vB"]),
    ]
    for name, rs in rows:
        a = agg(rs); pf = "inf" if a["pf"] == float("inf") else f"{a['pf']:.2f}"
        print(f"  {name:<28} {a['n']:>5} {a['wr']:>5.0f}% {a['totR']:>+8.1f} {a['avg']:>+6.2f} {pf:>6}")
    base = agg(acc["base"]); vA = agg(acc["vA"]); vAraw = agg(acc["vAraw"]); vB = agg(acc["vB"])
    if base["totR"]:
        print(f"\n  variantA (realistic, norm) vs baseline: {vA['totR']:+.1f} vs {base['totR']:+.1f} "
              f"({100*(vA['totR']-base['totR'])/abs(base['totR']):+.0f}%)")
        print(f"  variantA raw (same size)   vs baseline: {vAraw['totR']:+.1f} vs {base['totR']:+.1f} "
              f"({100*(vAraw['totR']-base['totR'])/abs(base['totR']):+.0f}%)")
        print(f"  variantB (causal fill)     vs baseline: {vB['totR']:+.1f} vs {base['totR']:+.1f} "
              f"({100*(vB['totR']-base['totR'])/abs(base['totR']):+.0f}%), trades {vB['n']} vs {base['n']}")


if __name__ == "__main__":
    main()
