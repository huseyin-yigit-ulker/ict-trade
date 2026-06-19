"""No-lookahead (future-data) check for the LIVE Donchian streams, via time truncation.

The repo already ships backtest/validation/lookahead_check.py for the retired ICT engine
(strategy_b/c/d/e). The four CURRENTLY-LIVE streams — donchian (1h), dch30_4h, dch30_4h6,
d30_4h_so (all 30m+4h) — run a different signal path (strategy.generate_signals +
strategy.htf_confirm) and had no truncation test. This is it.

Premise (truncation invariance): if signal generation at bar i uses ONLY data available by
that bar's CLOSE, then regenerating on data truncated to "everything closed by time T" must
reproduce EXACTLY the full-history run's signals whose FIRE time (bar close) is <= T — same
bars, directions and entry/SL/TP prices. We truncate BOTH frames (the base tf and, for the
hybrid, the 4h confirm tf) to bars closed by T, exactly as the live emitter sees them.

  - a full-run signal MISSING from the truncated run  -> emission needed future bars (leak)
  - a truncated-run signal ABSENT from the full run    -> future bars VETO/alter it    (leak)

Covers BOTH live paths:
  * 1h base            : generate_signals(df_1h)                         -> 'donchian'
  * 30m + 4h-confirm   : htf_confirm(generate_signals(df_30m), 4h)       -> dch30_4h / _6 / so
    (RR only sets take_profit = entry +/- RR*risk at the fire bar; it does not touch the
     causal break/confirm logic, so RR=4 and RR=6 share this proof. d30_4h_so reuses these
     exact signals; its scale-out legs are a FORWARD 1m walk from the fill = simulation,
     not look-ahead.)

Usage:
  python sync/donchian/lookahead_check.py                       # crypto core, 2026
  python sync/donchian/lookahead_check.py --year 2025 --symbols BTCUSDT ETHUSDT XAUUSDT
  python sync/donchian/lookahead_check.py --cuts 26            # denser (bi-weekly-ish) cuts
"""
from __future__ import annotations

import sys
import argparse
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))   # sync/         -> trade_sync_common
sys.path.insert(0, str(_HERE.parent))        # sync/donchian -> strategy
import trade_sync_common as tsc              # noqa: E402
import strategy as strat                     # noqa: E402

DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XAUUSDT"]


def _fetch(sym: str, tf: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    return tsc.fetch_klines(sym, tf, int(start.timestamp() * 1000), int(end.timestamp() * 1000))


def sig_key(s) -> tuple:
    return (s.timestamp.isoformat(), s.direction,
            f"{s.entry:.8g}", f"{s.stop_loss:.8g}", f"{s.take_profit_1:.8g}")


def gen(df_base: pd.DataFrame, base_tf: str, sym: str,
        hdf: pd.DataFrame | None, htf_tf: str | None) -> list:
    """Full live signal path for a (base_tf [, htf_tf]) config: breakout -> 4h-confirm -> US-gate."""
    sigs = strat.generate_signals(df_base, sym)
    if htf_tf is not None:
        sigs = strat.htf_confirm(sigs, base_tf, hdf, htf_tf)
    return strat.us_hours_gate(sigs, sym, base_tf)


def closed_by(df: pd.DataFrame, tf: str, T: pd.Timestamp) -> pd.DataFrame:
    """Rows whose bar CLOSE (index + tf bar) is <= T — i.e. all that is known at time T."""
    bar = pd.Timedelta(minutes=strat.TF_MINUTES[tf])
    return df[df.index + bar <= T]


def check_config(sym: str, base_tf: str, htf_tf: str | None,
                 win_start: pd.Timestamp, win_end: pd.Timestamp, n_cuts: int) -> tuple[int, int]:
    """Return (n_signals_in_window, n_lookahead_diffs) for one (symbol, config)."""
    warm = strat.TF_MINUTES[base_tf] * (strat.N_ENTRY + strat.ER_N) * 8
    start = win_start - pd.Timedelta(minutes=warm)
    df = _fetch(sym, base_tf, start, win_end)
    if df is None or df.empty:
        print(f"    {sym:<10} {base_tf}{'+'+htf_tf if htf_tf else '':<3} SKIP (no base data)")
        return 0, 0
    hdf = None
    if htf_tf is not None:
        hwarm = strat.TF_MINUTES[htf_tf] * (strat.N_ENTRY + strat.ER_N) * 8
        hdf = _fetch(sym, htf_tf, win_start - pd.Timedelta(minutes=hwarm), win_end)
        if hdf is None or hdf.empty:
            print(f"    {sym:<10} {base_tf}+{htf_tf} SKIP (no htf data)")
            return 0, 0

    base_bar = pd.Timedelta(minutes=strat.TF_MINUTES[base_tf])
    full = gen(df, base_tf, sym, hdf, htf_tf)
    full = [s for s in full if win_start <= s.timestamp < win_end]
    full_fire = {sig_key(s): (s.timestamp + base_bar) for s in full}

    # Even cut times across the window (each = a wall-clock "now" the live emitter could see).
    cut_times = pd.date_range(win_start, win_end, periods=n_cuts + 2, tz="UTC")[1:-1]
    bad = 0
    for T in cut_times:
        bt = closed_by(df, base_tf, T)
        ht = closed_by(hdf, htf_tf, T) if htf_tf is not None else None
        trunc = gen(bt, base_tf, sym, ht, htf_tf)
        tk = {sig_key(s) for s in trunc
              if win_start <= s.timestamp and (s.timestamp + base_bar) <= T}
        fk = {k for k, fire in full_fire.items() if fire <= T}
        missing, extra = fk - tk, tk - fk
        if missing or extra:
            bad += len(missing) + len(extra)
            print(f"    {sym:<10} {base_tf}{('+'+htf_tf) if htf_tf else '   '} "
                  f"cut@{T:%Y-%m-%d %H:%M}: missing={len(missing)} extra={len(extra)} FAIL")
            for k in sorted(missing)[:3]:
                print(f"        MISSING (leak-emit): {k}")
            for k in sorted(extra)[:3]:
                print(f"        EXTRA   (leak-veto): {k}")
    tag = f"{base_tf}+{htf_tf}" if htf_tf else base_tf
    print(f"    {sym:<10} {tag:<7} signals={len(full):>3} cuts={len(cut_times)} "
          f"diffs={bad} {'OK' if bad == 0 else 'FAIL'}", flush=True)
    return len(full), bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="*", default=DEFAULT_SYMBOLS)
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--cuts", type=int, default=14, help="truncation points across the window")
    args = ap.parse_args()

    win_start = pd.Timestamp(f"{args.year}-01-01", tz="UTC")
    win_end = (pd.Timestamp(f"{args.year + 1}-01-01", tz="UTC")
               if args.year < pd.Timestamp.now(tz='UTC').year
               else pd.Timestamp.now(tz="UTC"))
    # the live signal configs: 1h base, and 30m+4h hybrid (shared by dch30_4h/_6/d30_4h_so).
    configs = [("1h", None), ("30m", "4h")]
    print(f"=== DONCHIAN no-lookahead truncation check | {args.year} "
          f"[{win_start.date()}..{win_end.date()}) | cuts={args.cuts} | configs={configs} ===",
          flush=True)

    total_sig, total_bad = 0, 0
    for base_tf, htf_tf in configs:
        print(f"  -- config {base_tf}{('+'+htf_tf) if htf_tf else ''} --", flush=True)
        for sym in args.symbols:
            try:
                n, bad = check_config(sym, base_tf, htf_tf, win_start, win_end, args.cuts)
                total_sig += n
                total_bad += bad
            except Exception as e:  # noqa: BLE001
                print(f"    {sym:<10} {base_tf} ERROR: {e}", flush=True)

    print(f"\n=== checked {total_sig} signals across {len(args.symbols)} symbols x "
          f"{len(configs)} configs ===")
    print("RESULT:", "PASS — Donchian sinyal üretimi gelecek veri görmüyor"
          if total_bad == 0 else f"FAIL — {total_bad} fark (lookahead)")
    sys.exit(0 if total_bad == 0 else 1)


if __name__ == "__main__":
    main()
