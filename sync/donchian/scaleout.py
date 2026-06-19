"""Donchian 30m+4h SCALE-OUT stream — the HIGH-WIN-RATE variant. version='d30_4h_so'.

Goal: a high-WR Donchian model (user prefers WR over total R). The trend book (dch30_4h6,
RR=6) is ~18% WR / large winners; this is the opposite end of the same edge — a ~54% WR
curve, still OOS-positive every year.

Mechanic (validated 2024+2025+2026 OOS on crypto, /tmp/wr_sweep.py + /tmp/scaleout_sweep.py;
runner cap/time-box added 2026-06-19 by user decision, /tmp/so_cap_sweep.py):
  entry = 30m breakout (4h-direction confirmed), risk = 2*ATR (stop = -1R)
  * FIRST target = +1R: close CLOSE_FRAC (60%) of the position there  -> this sets the WR
  * move the stop on the (1-CLOSE_FRAC) RUNNER to breakeven (entry)
  * the RUNNER exits at the FIRST of: +RUNNER_CAP R (take-profit, default 4R), breakeven
    (price back to entry), or the RUNNER_HORIZON time-exit (default 3 days, mark-to-market).
    The 2024-2026 cap sweep chose 4R/3d: WR is unchanged (set by FIRST_R) and every year stays
    OOS-positive (cap4/3d ~+2438R vs the old uncapped/20d +2776R) while bounding runner duration
    to <=3d and per-trade R to 0.6*1 + 0.4*4 = 2.2R. (+4R == the dch30_4h signal's own TP.)
WR is set entirely by the FIRST target; the runner only adds R, not WR.

Faithfulness note: a trade that within HORIZON reaches NEITHER +1R nor -1R is counted as a
-1R loss (closed_sl) — exactly as the validated sweep did. It is a tiny population (a 2*ATR
stop almost always resolves within 20 days) but we replicate it so the DB R matches the
reported OOS numbers (Tf=1.0R/w1=0.6/ride: 2024 +327R, 2025 +234R, 2026 +143R; WR ~50-56%).

    python sync/donchian/scaleout.py --dry-run                  # per-symbol R, no write
    python sync/donchian/scaleout.py --dry-run --start 2025-01-01 --end 2026-01-01
    python sync/donchian/scaleout.py --apply --start 2024-01-01 --end 2025-01-01 --no-wipe
"""
from __future__ import annotations

import os
import sys
import pickle
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))   # sync/         -> trade_sync_common
sys.path.insert(0, str(_HERE.parent))        # sync/donchian -> strategy
import trade_sync_common as tsc              # noqa: E402
import strategy as strat                     # noqa: E402
from ict import config as C                  # noqa: E402  (path added by tsc)

VERSION = "d30_4h_so"        # <=10 chars (varchar(10)): donchian 30m+4h scale-out
TF = "30m"
CONFIRM_HTF = "4h"
FIRST_R = 1.0                # first take-profit, in R (sets the win rate)
CLOSE_FRAC = 0.6             # fraction of the position booked at +FIRST_R
HORIZON = pd.Timedelta(days=int(os.environ.get("DCH_SO_HORIZON_DAYS", "20")))  # +1R/-1R detection window (sets WR)
# Runner (the 1-CLOSE_FRAC remainder) is now CAPPED + TIME-BOXED (2026-06-19, user decision): it
# exits at +RUNNER_CAP R (take-profit), at breakeven if price returns to entry, or at the
# RUNNER_HORIZON time-exit (mark-to-market) — whichever comes first. Sweep over 2024-2026 chose
# cap=4R / 3d: keeps WR (set by FIRST_R, unchanged) and stays OOS-positive every year while
# bounding runner duration and per-trade R (uncapped/20d was +2776R, cap4/3d ~+2438R). Note
# +4R coincides with the dch30_4h signal's own TP (RR=4), so the runner's cap == the signal TP line.
RUNNER_CAP = float(os.environ.get("DCH_SO_RUNNER_CAP", "4.0"))                 # runner take-profit, in R
RUNNER_HORIZON = pd.Timedelta(days=int(os.environ.get("DCH_SO_RUNNER_DAYS", "3")))  # runner time exit
BIG = 10**9

DEFAULT_START = pd.Timestamp("2025-06-16", tz="UTC")
CACHE = Path(os.environ.get("DONCHIAN_1M_CACHE", "/tmp/donchian1m_cache"))

# Validated universe (the 19 symbols the 2024-2026 OOS sweep ran on: crypto + XAU). The
# stock-perps are net-negative in the base donchian book and XAG was not in the sweep, so
# the scale-out stream ships crypto+XAU only (mirrors how RANGE shipped a curated subset).
SO_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
    "1000PEPEUSDT", "WIFUSDT", "SUIUSDT",
    "NEARUSDT", "FETUSDT", "ADAUSDT", "SUSDT",
    "ARBUSDT", "ORDIUSDT", "ONDOUSDT",
    "XRPUSDT", "DOGEUSDT", "LINKUSDT", "AVAXUSDT",
    "XAUUSDT",
]


def _warmup(tf: str) -> pd.Timedelta:
    return pd.Timedelta(minutes=strat.TF_MINUTES[tf] * (strat.N_ENTRY + strat.ER_N) * 6)


# How far PAST the window end the 1m data must reach so a signal fired right at the window
# edge still has its FULL resolution window covered (20d partial-detection + 3d runner) — else
# its runner/partial gets marked at the data edge instead of its true exit. Capped at "now"
# in run_symbol (can't fetch the future).
M1_TAIL = HORIZON + RUNNER_HORIZON + pd.Timedelta(days=1)   # 20d + 3d + slack


def _load_1m(sym: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """1m frame covering [start, end]. If a cached frame ends before `end` (e.g. an old cache
    built only to the window boundary), FETCH the missing tail and append — so runner/partial
    windows near the window edge are resolved against complete data, not the stale cache end."""
    cf = CACHE / f"{sym}.pkl"
    if cf.exists():
        df = pickle.loads(cf.read_bytes())
        if df is not None and not df.empty:
            last = df.index[-1]
            if last.tz is None:
                df = df.copy(); df.index = df.index.tz_localize("UTC"); last = df.index[-1]
            if last < end - pd.Timedelta(minutes=1):                # cache stops short of `end`
                tail = tsc.fetch_1m(sym, last + pd.Timedelta(minutes=1), end)
                if tail is not None and not tail.empty:
                    if tail.index.tz is None:
                        tail.index = tail.index.tz_localize("UTC")
                    df = pd.concat([df, tail[tail.index > last]])
                    CACHE.mkdir(exist_ok=True)
                    cf.write_bytes(pickle.dumps(df))
            return df
    df = tsc.fetch_1m(sym, start - pd.Timedelta(hours=2), end)
    if df is not None and not df.empty:
        CACHE.mkdir(exist_ok=True)
        cf.write_bytes(pickle.dumps(df))
    return df


def resolve_scaleout(symbol: str, ts, direction: str, entry: float, sl: float, tp: float, *,
                     df1m: pd.DataFrame, ltf_minutes: int, expiry_minutes: int,
                     first_r: float = FIRST_R, close_frac: float = CLOSE_FRAC,
                     horizon: pd.Timedelta = HORIZON,
                     runner_cap: float = RUNNER_CAP, runner_horizon: pd.Timedelta = RUNNER_HORIZON,
                     active_if_incomplete: bool = False) -> dict:
    """Resolve one breakout under the scale-out + breakeven-ride model on 1m bars.

    Reuses tsc.simulate ONLY for the entry-fill / invalidation / expiry decision (identical
    to every other stream), then walks the 1m path from the fill for the scale-out legs.
    Returns the same dict shape as tsc._resolve (status / real_entry_time / exit_time /
    exit_price / pnl_r / raw_status).

    active_if_incomplete: when True (LIVE daily resolution), a trade whose 20-day runner
    window is not yet fully covered by `df1m` (and which has neither stopped nor returned to
    breakeven) is left ACTIVE instead of marked-to-market — so a still-riding runner is not
    booked early; it resolves on a later run once the horizon completes. The backfill passes
    False (sim-faithful: mark-to-market / -1R at the data end), reproducing the OOS numbers.

    Returns None when the breakout FAILS directional confirmation (ict.config.ENTRY_CONFIRM_BUF)
    — the caller skips it so no DB row is written for an unconfirmed signal."""
    cts = pd.Timestamp(ts)
    cts = (cts.tz_localize("UTC") if cts.tz is None else cts.tz_convert("UTC")) + pd.Timedelta(minutes=ltf_minutes)
    if not tsc.entry_confirmed(df1m, cts, direction, entry, sl, expiry_minutes=expiry_minutes):
        return None
    base = tsc.simulate(symbol, ts, direction, entry, sl, tp, df1m=df1m,
                        ltf_minutes=ltf_minutes, expiry_minutes=expiry_minutes)
    ft = base["real_entry_time"]
    if ft is None:                                   # never filled -> no trade taken; pass through
        return base
    idx = df1m.index
    if idx.tz is None:
        df1m = df1m.copy(); df1m.index = idx = idx.tz_localize("UTC")
    ftp = pd.Timestamp(ft)
    ftp = ftp.tz_localize("UTC") if ftp.tz is None else ftp.tz_convert("UTC")
    p0 = int(idx.searchsorted(ftp))
    p1 = int(idx.searchsorted(ftp + horizon))
    risk = abs(float(entry) - float(sl))
    if risk <= 0 or p0 >= len(idx) or p1 <= p0:
        base.update(status="active", exit_time=None, exit_price=None, pnl_r=None,
                    raw_status="active")
        return base
    lng = direction.lower() == "long"
    H = df1m["high"].values; L = df1m["low"].values; Cl = df1m["close"].values
    hi = H[p0:p1]; lo = L[p0:p1]
    fav = ((hi - entry) if lng else (entry - lo)) / risk     # per-bar favourable extreme (R)
    adv = ((entry - lo) if lng else (hi - entry)) / risk     # per-bar adverse extreme (R)
    favcum = np.maximum.accumulate(fav)
    t_stop = int(np.argmax(adv >= 1.0)) if (adv >= 1.0).any() else BIG
    t_tf = int(np.argmax(favcum >= first_r)) if (favcum >= first_r).any() else BIG
    fee = C.FEE_PCT_PER_SIDE * (2 * entry) / risk           # round-trip fee on full notional, in R
    bar = pd.Timedelta(minutes=1)
    full_horizon = bool(idx[-1] >= ftp + horizon)           # 20-day runner window fully covered by df1m?

    def close_at(i):
        return (df1m.index[p0 + i] + bar).to_pydatetime()

    def still_active():
        base.update(status="active", exit_time=None, exit_price=None, pnl_r=None,
                    raw_status="active")
        return base

    if t_stop <= t_tf:                                      # stopped (or neither) before the first target
        if t_stop < BIG:                                    # real -1R stop
            base.update(status="closed_sl", exit_time=close_at(t_stop), exit_price=float(sl),
                        pnl_r=float(-1.0 - fee), raw_status="sl_hit")
            return base
        if active_if_incomplete and not full_horizon:       # neither +1R nor -1R yet, window open -> wait
            return still_active()
        base.update(status="closed_sl", exit_time=close_at(p1 - 1 - p0), exit_price=float(sl),
                    pnl_r=float(-1.0 - fee), raw_status="sl_hit")  # neither within horizon -> -1R (faithful)
        return base

    # partial books close_frac at +first_r; the runner (1-close_frac) exits at the FIRST of:
    #   * +runner_cap R (take-profit) | * breakeven (price returns to entry) | * runner_horizon
    #   time-exit (mark-to-market). All forward-walking; same-bar BE+cap tie -> breakeven (pessimistic).
    gross = close_frac * first_r
    rbars = int(runner_horizon / pd.Timedelta(minutes=1))   # 1m bars in the runner window
    dl = t_tf + 1 + rbars                                    # runner deadline index (rel to p0), exclusive
    covered = dl <= len(adv)                                 # df1m spans the full runner window?
    hi_i = min(dl, len(adv))
    be_seg = adv[t_tf + 1:hi_i] >= 0.0                       # back to entry (breakeven)
    cap_seg = favcum[t_tf + 1:hi_i] >= runner_cap            # runner reached +runner_cap R
    t_be = (t_tf + 1 + int(np.argmax(be_seg))) if be_seg.any() else BIG
    t_cap = (t_tf + 1 + int(np.argmax(cap_seg))) if cap_seg.any() else BIG
    if min(t_be, t_cap) < BIG:
        if t_be <= t_cap:                                   # breakeven first -> runner 0R
            base.update(status="closed_tp", exit_time=close_at(t_be), exit_price=float(entry),
                        pnl_r=float(gross - fee), raw_status="tp_hit")
        else:                                               # runner ran to +runner_cap
            cap_px = entry + runner_cap * risk * (1 if lng else -1)
            base.update(status="closed_tp", exit_time=close_at(t_cap), exit_price=float(cap_px),
                        pnl_r=float(gross + (1 - close_frac) * runner_cap - fee), raw_status="tp_hit")
        return base
    if active_if_incomplete and not covered:                # runner still riding inside the window -> wait
        return still_active()
    j = hi_i - 1                                            # neither cap nor BE -> mark to market at deadline
    last = (Cl[p0 + j] - entry) / risk * (1 if lng else -1)
    gross += (1 - close_frac) * max(last, 0.0)
    base.update(status="closed_tp", exit_time=close_at(j), exit_price=float(Cl[p0 + j]),
                pnl_r=float(gross - fee), raw_status="tp_hit")
    return base


def run_symbol(sym: str, w_start: pd.Timestamp, w_end: pd.Timestamp):
    """Return (rows, resolved_n, total_r) for one symbol under the scale-out model."""
    ltf_min = strat.TF_MINUTES[TF]
    df = tsc.fetch_klines(sym, TF, int((w_start - _warmup(TF)).timestamp() * 1000),
                          int(w_end.timestamp() * 1000))
    if df is None or df.empty:
        print(f"  {sym:<10} SKIP (no {TF})", flush=True)
        return [], 0, 0.0
    sigs = [s for s in strat.generate_signals(df, sym) if w_start <= s.timestamp < w_end]
    if sigs:
        hdf = tsc.fetch_klines(sym, CONFIRM_HTF, int((w_start - _warmup(CONFIRM_HTF)).timestamp() * 1000),
                               int(w_end.timestamp() * 1000))
        sigs = strat.htf_confirm(sigs, TF, hdf, CONFIRM_HTF)
    sigs = strat.us_hours_gate(sigs, sym, TF)
    if not sigs:
        print(f"  {sym:<10} 0 breakouts", flush=True)
        return [], 0, 0.0
    # Extend the 1m window PAST w_end so edge-of-window signals get their full runner/partial
    # resolution (capped at now — the future isn't fetchable).
    m1_end = min(pd.Timestamp.now(tz="UTC"), w_end + M1_TAIL)
    df1m = _load_1m(sym, w_start, m1_end)
    if df1m is None or df1m.empty:
        print(f"  {sym:<10} SKIP (no 1m)", flush=True)
        return [], 0, 0.0
    rows, resolved, tot = [], 0, 0.0
    for s in sigs:
        res = resolve_scaleout(sym, s.timestamp, s.direction, s.entry, s.stop_loss,
                               s.take_profit_1, df1m=df1m, ltf_minutes=ltf_min,
                               expiry_minutes=s.expiry_minutes)
        if res is None:                       # failed directional confirmation -> no row
            continue
        row = tsc.build_row(sym, s.timestamp, s.direction, s.entry, s.stop_loss,
                            s.take_profit_1, res, strategy=s.strategy,
                            quality=s.quality, confluence_score=s.confluence_score)
        row["version"] = VERSION
        rows.append(row)
        if res["status"] in ("closed_tp", "closed_sl") and res["pnl_r"] is not None:
            resolved += 1
            tot += float(res["pnl_r"])
    wr = 100 * sum(1 for r in rows if r["status"] == "closed_tp") / resolved if resolved else 0
    print(f"  {sym:<10} {len(sigs):>3} breakouts -> resolved {resolved:>3} "
          f"WR={wr:>3.0f}%  totR={tot:+6.1f}", flush=True)
    return rows, resolved, tot


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    ap.add_argument("--symbols", nargs="*", default=SO_SYMBOLS)
    ap.add_argument("--start", default=None, help="YYYY-MM-DD (default 2025-06-16)")
    ap.add_argument("--end", default=None, help="YYYY-MM-DD (default now)")
    ap.add_argument("--no-wipe", action="store_true",
                    help="append: skip the version wipe (for multi-window backfill)")
    args = ap.parse_args()

    w_start = pd.Timestamp(args.start, tz="UTC") if args.start else DEFAULT_START
    w_end = pd.Timestamp(args.end, tz="UTC") if args.end else pd.Timestamp.now(tz="UTC")
    print(f"=== Donchian SCALE-OUT [{w_start.date()} .. {w_end.date()}) "
          f"| {TF}+{CONFIRM_HTF} | first=+{FIRST_R:g}R close={CLOSE_FRAC:g} "
          f"runner cap{RUNNER_CAP:g}R/{RUNNER_HORIZON.days}d "
          f"| {len(args.symbols)} symbols | version='{VERSION}' ===", flush=True)

    all_rows, tot_n, tot_r = [], 0, 0.0
    for sym in args.symbols:
        try:
            rows, n, r = run_symbol(sym, w_start, w_end)
            all_rows += rows; tot_n += n; tot_r += r
        except Exception as e:  # noqa: BLE001
            print(f"  ! {sym}: {e}", flush=True)

    wr = 100 * sum(1 for r in all_rows if r["status"] == "closed_tp") / tot_n if tot_n else 0
    print(f"\n=== TOTAL resolved={tot_n}  WR={wr:.0f}%  totR={tot_r:+.1f} ===")

    if args.dry_run:
        print("[dry-run] no DB write.")
        return

    conn = tsc.backtest_conn()
    if not args.no_wipe:
        cur = conn.cursor()
        cur.execute(f"DELETE FROM {tsc.TABLE} WHERE version=%s", (VERSION,))
        print(f"  wiped {cur.rowcount} existing '{VERSION}' rows")
        conn.commit(); cur.close()
    else:
        print(f"  [--no-wipe] appending {len(all_rows)} rows (no wipe)")
    n = tsc.upsert_rows(conn, all_rows)
    conn.close()
    print(f"  upserted {n} '{VERSION}' rows into {tsc.TABLE}")


if __name__ == "__main__":
    main()
