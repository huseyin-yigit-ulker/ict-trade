"""Live-vs-backtest signal parity for the LIVE Donchian streams.

Proves the dashboard's live rows are exactly what the backtest engine would have produced —
i.e. live and backtest share one signal path, so backtest R is what live will realise.

For every row in ict_trade.signals (mode in donchian / dch30_4h / dch30_4h6) we re-fetch the
same Binance klines and re-run the PRODUCTION signal path
(strategy.generate_signals -> htf_confirm -> us_hours_gate), then:

  FORWARD (geometry parity, strict): every live row must be reproduced by the backtest engine
    at the same (signal_time, direction) with entry/SL/TP equal within REL_TOL. A live row with
    no backtest twin, or a price mismatch, is a PARITY BREAK (live diverged from backtest).

  REVERSE (emission completeness, diagnostic): every backtest breakout in the live window that
    (a) passes the directional-confirm gate on 1m and (b) is old enough that its cron+lookback
    window has fully passed, should exist in live. Anything missing is reported — but note a
    just-confirmed signal can legitimately be awaiting the next cron run, so reverse is advisory.

This is the Donchian analogue of backtest/validation/live_parity_check.py (which covers the
retired ICT engine, mode='live').

Usage:
  python sync/donchian/live_parity.py
  python sync/donchian/live_parity.py --grace-min 95
"""
from __future__ import annotations

import sys
import argparse
from collections import defaultdict
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))   # sync/         -> trade_sync_common
sys.path.insert(0, str(_HERE.parent))        # sync/donchian -> strategy
import trade_sync_common as tsc              # noqa: E402
import strategy as strat                     # noqa: E402

REL_TOL = 1e-4
# mode -> (base_tf, htf_tf, rr)
MODES = {
    "donchian":  ("1h",  None, strat.RR),
    "dch30_4h":  ("30m", "4h", strat.RR),
    "dch30_4h6": ("30m", "4h", 6.0),
}


def rel_eq(a, b) -> bool:
    a, b = float(a), float(b)
    return abs(a - b) <= REL_TOL * max(abs(a), abs(b), 1e-12)


def fetch_live():
    conn = tsc.live_conn(); cur = conn.cursor()
    cur.execute("""SELECT symbol, signal_time, direction, entry, sl, tp, mode
                   FROM ict_trade.signals WHERE mode = ANY(%s) ORDER BY mode, symbol, signal_time""",
                (list(MODES),))
    rows = []
    for sym, st, d, e, sl, tp, mode in cur.fetchall():
        ts = pd.Timestamp(st)
        ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
        rows.append({"symbol": sym, "ts": ts, "dir": d.lower(),
                     "entry": float(e), "sl": float(sl), "tp": float(tp), "mode": mode})
    cur.close(); conn.close()
    return rows


def backtest_signals(sym: str, base_tf: str, htf_tf, rr: float,
                     start: pd.Timestamp, now: pd.Timestamp) -> dict:
    warm = strat.TF_MINUTES[base_tf] * (strat.N_ENTRY + strat.ER_N) * 8
    df = tsc.fetch_klines(sym, base_tf, int((start - pd.Timedelta(minutes=warm)).timestamp() * 1000),
                          int(now.timestamp() * 1000))
    if df is None or df.empty:
        return {}
    sigs = strat.generate_signals(df, sym, rr=rr)
    if htf_tf is not None:
        hwarm = strat.TF_MINUTES[htf_tf] * (strat.N_ENTRY + strat.ER_N) * 8
        hdf = tsc.fetch_klines(sym, htf_tf,
                               int((start - pd.Timedelta(minutes=hwarm)).timestamp() * 1000),
                               int(now.timestamp() * 1000))
        sigs = strat.htf_confirm(sigs, base_tf, hdf, htf_tf)
    sigs = strat.us_hours_gate(sigs, sym, base_tf)
    return {(s.timestamp, s.direction): s for s in sigs}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grace-min", type=int, default=95,
                    help="reverse check: a backtest signal counts as 'should be live' only once "
                         "fire+grace has passed (cron :00/:30 + lookback). Default 95.")
    args = ap.parse_args()
    now = pd.Timestamp.now(tz="UTC")
    live = fetch_live()
    by_mode_sym = defaultdict(lambda: defaultdict(list))
    for r in live:
        by_mode_sym[r["mode"]][r["symbol"]].append(r)
    print(f"=== Donchian live-parity @ {now:%Y-%m-%d %H:%M}Z | live rows={len(live)} "
          f"| tol={REL_TOL:g} ===", flush=True)

    reproduced = mism = miss_bt = 0          # forward
    rev_missing = 0                          # reverse (diagnostic)
    for mode, (base_tf, htf_tf, rr) in MODES.items():
        sym_rows = by_mode_sym.get(mode, {})
        if not sym_rows:
            print(f"  [{mode}] no live rows", flush=True)
            continue
        for sym, rows in sym_rows.items():
            start = min(r["ts"] for r in rows)
            bt = backtest_signals(sym, base_tf, htf_tf, rr, start, now)
            base_bar = pd.Timedelta(minutes=strat.TF_MINUTES[base_tf])
            # FORWARD: each live row reproduced by a backtest signal at the same bar+dir
            live_keys = set()
            for r in rows:
                key = (r["ts"], r["dir"]); live_keys.add(key)
                s = bt.get(key)
                if s is None:
                    miss_bt += 1
                    print(f"    PARITY-BREAK [{mode}] {sym} {r['ts']:%m-%d %H:%M} {r['dir']} "
                          f"— live row has NO backtest twin", flush=True)
                elif rel_eq(r["entry"], s.entry) and rel_eq(r["sl"], s.stop_loss) and rel_eq(r["tp"], s.take_profit_1):
                    reproduced += 1
                else:
                    mism += 1
                    print(f"    PRICE-MISMATCH [{mode}] {sym} {r['ts']:%m-%d %H:%M} {r['dir']} "
                          f"live(e/sl/tp)={r['entry']:.6g}/{r['sl']:.6g}/{r['tp']:.6g} "
                          f"bt={s.entry:.6g}/{s.stop_loss:.6g}/{s.take_profit_1:.6g}", flush=True)
            # REVERSE: a backtest breakout that PASSES the directional-confirm gate (the same
            # filter the live emitter applies) and is old enough to be due must be in live.
            # Apply the gate here so we compare like-for-like (gate-rejected breakouts SHOULD be
            # absent from live — that's the gate working, not a parity break).
            cand = [(ts, d, s) for (ts, d), s in bt.items()
                    if (ts, d) not in live_keys and ts >= start
                    and (ts + base_bar + pd.Timedelta(minutes=args.grace_min)) <= now]
            if cand:
                df1m = None
                try:
                    df1m = tsc.fetch_1m(sym, start + base_bar - pd.Timedelta(minutes=2), now)
                except Exception:  # noqa: BLE001
                    df1m = None
                for ts, d, s in cand:
                    cts = ts + base_bar
                    confirmed = (df1m is not None and not df1m.empty and tsc.entry_confirmed(
                        df1m, cts, d, s.entry, s.stop_loss, expiry_minutes=s.expiry_minutes))
                    if confirmed:
                        rev_missing += 1
                        print(f"    REVERSE-MISSING [{mode}] {sym} {ts:%m-%d %H:%M} {d} "
                              f"— CONFIRMED backtest breakout absent from live (real gap)", flush=True)

    print("\n" + "=" * 60)
    print(f"FORWARD  reproduced(live≡backtest)={reproduced}  price-mismatch={mism}  "
          f"live-without-backtest-twin={miss_bt}")
    print(f"REVERSE  backtest-due-but-not-in-live={rev_missing} (diagnostic; confirm-gate/cron timing)")
    ok = (mism == 0 and miss_bt == 0)
    print("\nRESULT:", "PASS — canlı Donchian sinyalleri ≡ backtest (geometri)"
          if ok else "FAIL — yukarıdaki parite farkları")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
