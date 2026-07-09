"""LIVE-faithful PORTFOLIO backfill for the whole Donchian UI book.

Replaces the independent-per-signal backtests with the demo-faithful portfolio model the live
Binance bridge actually follows:
  * ONE position per symbol at a time
  * a SAME-direction signal while open is IGNORED
  * an OPPOSITE confirmed signal REVERSES (mark-to-market close, then flip)
  * NO cross-symbol concurrency cap (one-per-symbol == sync/live_exec/demo_backtest.py)
Confirm-entry (·0.5R) is forced via _bootenv (DCH_ENTRY_AT_CONFIRM=1). One continuous walk
over 2024-01-01..now (covers all 3 years; cross-year positions are not artificially cut).

Streams (signal source x exit model), full universe = strategy.SYMBOLS:
  1h family      : 1h Donchian(55) breakout, ER>=0.35, NO 4h confirm
  30m+4h family  : 30m breakout + 4h-direction confirm
  full-TP (base) : confirm_fill -> resolve_market, structural RR target (4 or 6)
  scale-out cap  : resolve_scaleout, 60% @ +1R / breakeven-runner -> +capR / 3d
  margin variants: same as scale-out caps but only signals whose breakout clears the channel
                   by >= MARGIN_MIN ATR (OOS-robust false-breakout filter; new tags *cm)

    python sync/donchian/portfolio_backfill.py --stream all --apply
    python sync/donchian/portfolio_backfill.py --stream d30so8c --dry-run
"""
from __future__ import annotations
import sys
import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent))               # sync/donchian
sys.path.insert(0, str(_HERE.parents[1]))           # sync/
sys.path.insert(0, str(_HERE.parents[1] / "live_exec"))

import pandas as pd
import _bootenv                                      # noqa: F401  forces DCH_ENTRY_AT_CONFIRM=1
import trade_sync_common as tsc                      # noqa: E402
import strategy as strat                             # noqa: E402
import scaleout as so                                # noqa: E402
from trade_sync_common import _net_r                 # noqa: E402

DEFAULT_START = pd.Timestamp("2024-01-01", tz="UTC")
MARGIN_MIN = 0.25                                    # OOS-robust breakout-clearance filter (ATR units)
SYMBOLS = list(strat.CRYPTO_METAL_SYMBOLS)           # crypto + metals (20); the 20 US-stock perps
                                                     # are dropped (2026-07-09 owner decision — the
                                                     # tokenised equities were noise). See strategy.py.
# CRYPTO-only universe (the 18 crypto perps; drops XAU/XAG + the 20 stock-perps). 2026-07-08 owner
# decision: OPUS (d30so8f3h7 — the live real-money stream) trades crypto ONLY, so its backtest book
# must mirror that universe. Gold has its own streams (MIDAS paper / TALOS-ICHI-X real money).
CRYPTO_SYMBOLS = tuple(s for s in strat.SYMBOLS[:strat.SYMBOLS.index("XAUUSDT")])
_SYMBOLS_OVERRIDE = None                             # set by --symbols (testing); beats st.symbols

# Bounded LRU of 1m frames so reverse re-resolves don't pin every symbol's full-span 1m in RAM
# at once (7GB box). build_events loads-and-drops; reverses reload from the warm pkl cache.
_M1_LRU: dict = {}
_M1_ORDER: list = []
_M1_MAX = 4


def _get_1m(sym, w_start, w_end):
    if sym in _M1_LRU:
        _M1_ORDER.remove(sym); _M1_ORDER.append(sym)
        return _M1_LRU[sym]
    m1_end = min(pd.Timestamp.now(tz="UTC"), w_end + so.M1_TAIL)
    df1m = so._load_1m(sym, w_start, m1_end)
    _M1_LRU[sym] = df1m; _M1_ORDER.append(sym)
    while len(_M1_ORDER) > _M1_MAX:
        _M1_LRU.pop(_M1_ORDER.pop(0), None)
    return df1m


@dataclass(frozen=True)
class Stream:
    version: str
    tf: str                 # "1h" | "30m"
    confirm_htf: Optional[str]   # "4h" for the 30m family, None for 1h
    exit: str               # "fulltp" | "scaleout"
    rr: float = 4.0         # structural RR (full-TP) / signal geometry (scale-out)
    cap: Optional[float] = None  # runner cap for scale-out
    margin: bool = False    # require margin >= MARGIN_MIN
    close_frac: Optional[float] = None  # scale-out: fraction booked at TP1 (None -> so.CLOSE_FRAC=0.6)
    horizon_days: Optional[int] = None  # scale-out: runner/whole-trade time limit (None -> so.HORIZON=3d)
    symbols: Optional[tuple] = None     # restrict the universe (None -> full SYMBOLS). OPUS = crypto-only.


STREAMS = {
    # ── 1h family (no 4h confirm) ──
    "donchianc": Stream("donchianc", "1h", None, "fulltp", rr=4.0),
    "d1h_so4c":  Stream("d1h_so4c",  "1h", None, "scaleout", cap=4.0),
    "d1h_so6c":  Stream("d1h_so6c",  "1h", None, "scaleout", cap=6.0),
    "d1h_so8c":  Stream("d1h_so8c",  "1h", None, "scaleout", cap=8.0),
    # ── 30m + 4h family ──
    "dch30_4hc":  Stream("dch30_4hc",  "30m", "4h", "fulltp", rr=4.0),
    "dch30_4h6c": Stream("dch30_4h6c", "30m", "4h", "fulltp", rr=6.0),
    "d30_4h_soc": Stream("d30_4h_soc", "30m", "4h", "scaleout", cap=4.0),
    "d30so6c":    Stream("d30so6c",    "30m", "4h", "scaleout", cap=6.0),
    "d30so8c":    Stream("d30so8c",    "30m", "4h", "scaleout", cap=8.0),
    # ── margin>=0.25 variants (new tags, scale-out caps only) ──
    "d1hso4cm": Stream("d1hso4cm", "1h", None, "scaleout", cap=4.0, margin=True),
    "d1hso6cm": Stream("d1hso6cm", "1h", None, "scaleout", cap=6.0, margin=True),
    "d1hso8cm": Stream("d1hso8cm", "1h", None, "scaleout", cap=8.0, margin=True),
    "d30so4cm": Stream("d30so4cm", "30m", "4h", "scaleout", cap=4.0, margin=True),
    "d30so6cm": Stream("d30so6cm", "30m", "4h", "scaleout", cap=6.0, margin=True),
    "d30so8cm": Stream("d30so8cm", "30m", "4h", "scaleout", cap=8.0, margin=True),
    # ── close_frac=0.3 variants (book LESS at TP1, ride more on the runner) — new tags ──
    "d30so4f3": Stream("d30so4f3", "30m", "4h", "scaleout", cap=4.0, close_frac=0.3),
    "d30so6f3": Stream("d30so6f3", "30m", "4h", "scaleout", cap=6.0, close_frac=0.3),
    "d30so8f3": Stream("d30so8f3", "30m", "4h", "scaleout", cap=8.0, close_frac=0.3),
    # ── d30so8f3 + 7-day time-stop (runner gets more room before the mark-to-market exit) ──
    # OPUS = the live real-money stream: CRYPTO-ONLY universe (2026-07-08 owner decision).
    "d30so8f3h7": Stream("d30so8f3h7", "30m", "4h", "scaleout", cap=8.0, close_frac=0.3,
                         horizon_days=7, symbols=CRYPTO_SYMBOLS),
}


def _signals(sym, st: Stream, w_start, w_end):
    """Stream-correct historical signals (no-lookahead), optionally margin-filtered."""
    ltf_min = strat.TF_MINUTES[st.tf]
    df = tsc.fetch_klines(sym, st.tf, int((w_start - so._warmup(st.tf)).timestamp() * 1000),
                          int(w_end.timestamp() * 1000))
    if df is None or df.empty:
        return [], None
    df = df[df.index + pd.Timedelta(minutes=ltf_min) <= min(w_end, pd.Timestamp.now(tz="UTC"))]
    if df.empty:
        return [], None
    sigs = [s for s in strat.generate_signals(df, sym, rr=st.rr) if w_start <= s.timestamp < w_end]
    if sigs and st.confirm_htf:
        hdf = tsc.fetch_klines(sym, st.confirm_htf,
                               int((w_start - so._warmup(st.confirm_htf)).timestamp() * 1000),
                               int(w_end.timestamp() * 1000))
        sigs = strat.htf_confirm(sigs, st.tf, hdf, st.confirm_htf)
    sigs = strat.us_hours_gate(sigs, sym, st.tf)
    if st.margin and sigs:
        a = strat.atr(df)
        hi = df["high"].rolling(strat.N_ENTRY).max().shift(1)
        lo = df["low"].rolling(strat.N_ENTRY).min().shift(1)
        pos = {ts: i for i, ts in enumerate(df.index)}
        kept = []
        for s in sigs:
            i = pos.get(s.timestamp)
            if i is None or not (a.iloc[i] > 0):
                continue
            margin = ((s.entry - hi.iloc[i]) if s.direction == "long"
                      else (lo.iloc[i] - s.entry)) / float(a.iloc[i])
            if margin >= MARGIN_MIN:
                kept.append(s)
        sigs = kept
    return sigs, ltf_min


def build_events(sym, st: Stream, w_start, w_end):
    """Each taken signal -> a portfolio event with its natural outcome + geometry for reverses."""
    sigs, ltf_min = _signals(sym, st, w_start, w_end)
    if not sigs:
        return []
    df1m = _get_1m(sym, w_start, w_end)
    if df1m is None or df1m.empty:
        return []
    out = []
    for s in sigs:
        if st.exit == "scaleout":
            res = so.resolve_scaleout(sym, s.timestamp, s.direction, s.entry, s.stop_loss,
                                      s.take_profit_1, df1m=df1m, ltf_minutes=ltf_min,
                                      expiry_minutes=s.expiry_minutes, runner_cap=float(st.cap),
                                      close_frac=(st.close_frac if st.close_frac is not None else so.CLOSE_FRAC),
                                      horizon=(pd.Timedelta(days=st.horizon_days) if st.horizon_days else so.HORIZON))
            if res is None or res.get("real_entry_time") is None:
                continue
            disp_entry = float(res.get("entry_eff", s.entry))
            disp_tp = float(res.get("cap_price", s.take_profit_1))
            nat_exit = pd.Timestamp(res["exit_time"]).tz_convert("UTC") if res.get("exit_time") else None
            nat_r = float(res["pnl_r"]) if res.get("pnl_r") is not None else None
            nat_exit_price = float(res["exit_price"]) if res.get("exit_price") is not None else None
            nat_status = res.get("status")
        else:  # full-TP via confirm-fill + resolve_market
            cts = (pd.Timestamp(s.timestamp).tz_convert("UTC")
                   if pd.Timestamp(s.timestamp).tz else pd.Timestamp(s.timestamp).tz_localize("UTC")) \
                  + pd.Timedelta(minutes=ltf_min)
            cf = tsc.confirm_fill(df1m, cts, s.direction, s.entry, s.stop_loss,
                                  expiry_minutes=s.expiry_minutes)
            if cf is None:
                continue
            fill_ts, entry_eff, risk_eff = cf
            res = tsc.resolve_market(df1m, fill_ts, s.direction, entry_eff, s.stop_loss,
                                     s.take_profit_1, risk_eff, max_hold_minutes=3 * 24 * 60)
            if res.get("real_entry_time") is None:
                continue
            disp_entry = float(entry_eff)
            disp_tp = float(s.take_profit_1)
            nat_exit = pd.Timestamp(res["exit_time"]).tz_convert("UTC") if res.get("exit_time") else None
            nat_r = float(res["pnl_r"]) if res.get("pnl_r") is not None else None
            nat_exit_price = float(res["exit_price"]) if res.get("exit_price") is not None else None
            nat_status = res.get("status")
        out.append({
            "symbol": sym, "direction": s.direction.lower(), "signal_ts": s.timestamp,
            # raw geometry (scale-out reverse re-resolve re-applies the confirm shift itself)
            "raw_entry": float(s.entry), "sl": float(s.stop_loss), "raw_tp": float(s.take_profit_1),
            # display geometry stored to the DB row
            "entry": disp_entry, "tp": disp_tp,
            "risk_eff": abs(disp_entry - float(s.stop_loss)),
            "fill": pd.Timestamp(res["real_entry_time"]).tz_convert("UTC"),
            "nat_exit": nat_exit, "nat_r": nat_r, "nat_exit_price": nat_exit_price,
            "nat_status": nat_status,
            "strategy": getattr(s, "strategy", None), "quality": getattr(s, "quality", None),
            "confluence_score": getattr(s, "confluence_score", None),
            "ltf_min": ltf_min})
    return out


def _reverse_r(p, t, st: Stream, w_start, w_end):
    """R of position p force-closed at time t (opposite signal)."""
    df1m = _get_1m(p["symbol"], w_start, w_end)
    if st.exit == "scaleout":
        horizon = t - p["fill"]
        if horizon <= pd.Timedelta(0):
            return 0.0, None
        res = so.resolve_scaleout(p["symbol"], p["signal_ts"], p["direction"], p["raw_entry"],
                                  p["sl"], p["raw_tp"], df1m=df1m, ltf_minutes=p["ltf_min"],
                                  expiry_minutes=180, runner_cap=float(st.cap),
                                  close_frac=(st.close_frac if st.close_frac is not None else so.CLOSE_FRAC),
                                  horizon=horizon, active_if_incomplete=False)
        r = float(res["pnl_r"]) if res and res.get("pnl_r") is not None else 0.0
        ep = float(res["exit_price"]) if res and res.get("exit_price") is not None else None
        return r, ep
    sub = df1m.loc[df1m.index <= t]
    if sub.empty or p["risk_eff"] <= 0:
        return 0.0, None
    px = float(sub["close"].iloc[-1])
    return float(_net_r(p["entry"], px, p["risk_eff"], p["direction"])), px


def walk(events, st: Stream, w_start, w_end):
    """Chronological one-pos/symbol + reverse walk -> realized trade dicts."""
    evs = sorted(events, key=lambda e: e["fill"])
    open_pos, realized = {}, []

    def rec(p, exit_t, r, status, exit_price):
        realized.append({**p, "exit": exit_t, "r": r, "status": status, "exit_price": exit_price})

    def close_before(t):
        for sym, p in list(open_pos.items()):
            if p["nat_exit"] is not None and p["nat_exit"] <= t:
                rec(p, p["nat_exit"], p["nat_r"], p["nat_status"], p["nat_exit_price"])
                del open_pos[sym]

    for e in evs:
        t = e["fill"]
        close_before(t)
        sym = e["symbol"]
        if sym in open_pos:
            p = open_pos[sym]
            if p["direction"] == e["direction"]:
                continue
            r, ep = _reverse_r(p, t, st, w_start, w_end)
            rec(p, t, r, "closed_tp" if r >= 0 else "closed_sl", ep)
            del open_pos[sym]
        open_pos[sym] = e
    for sym, p in open_pos.items():
        if p["nat_exit"] is not None:
            rec(p, p["nat_exit"], p["nat_r"], p["nat_status"], p["nat_exit_price"])
        else:
            rec(p, None, None, "active", None)
    return realized


def _pf(x):
    """Coerce numpy scalars -> native python float (psycopg2 can't render np.float64)."""
    return float(x) if x is not None else None


def to_rows(realized, st: Stream):
    rows = []
    for r in realized:
        outcome = {
            "status": r["status"],
            "real_entry_time": r["fill"].to_pydatetime() if r["fill"] is not None else None,
            "exit_time": r["exit"].to_pydatetime() if r["exit"] is not None else None,
            "exit_price": _pf(r["exit_price"]),
            "pnl_r": _pf(r["r"]),
        }
        row = tsc.build_row(r["symbol"], r["signal_ts"],
                            "LONG" if r["direction"] == "long" else "SHORT",
                            _pf(r["entry"]), _pf(r["sl"]), _pf(r["tp"]), outcome,
                            strategy=r.get("strategy"), quality=r.get("quality"),
                            confluence_score=r.get("confluence_score"))
        row["version"] = st.version
        rows.append(row)
    return rows


def run_stream(name, w_start, w_end, apply):
    st = STREAMS[name]
    # universe: CLI --symbols (testing) > per-stream restriction (OPUS = crypto-only) > full SYMBOLS
    syms = _SYMBOLS_OVERRIDE or (list(st.symbols) if st.symbols else SYMBOLS)
    print(f"\n=== [{name}] {st.tf}{'+'+st.confirm_htf if st.confirm_htf else ''} "
          f"{st.exit}{(' cap'+str(int(st.cap))+'R') if st.cap else (' RR'+str(int(st.rr)))}"
          f"{' margin>=%.2f'%MARGIN_MIN if st.margin else ''} "
          f"| [{w_start.date()}..{w_end.date()}) | {len(syms)} symbols"
          f"{' (CRYPTO-ONLY)' if st.symbols else ''} ===", flush=True)
    events = []
    for sym in syms:
        try:
            ev = build_events(sym, st, w_start, w_end)
            events += ev
            if ev:
                print(f"  {sym:<12} {len(ev):>4} taken", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {sym}: {type(e).__name__}: {e}", flush=True)
    realized = walk(events, st, w_start, w_end)
    rows = to_rows(realized, st)
    closed = [r for r in realized if r["r"] is not None]
    tot = sum(r["r"] for r in closed)
    wins = sum(1 for r in closed if r["r"] > 0)
    wr = round(100 * wins / len(closed)) if closed else 0
    act = len(realized) - len(closed)
    print(f"  -> {len(rows)} rows · closed={len(closed)} · R={tot:+.1f} · WR={wr}% · active={act}",
          flush=True)
    if apply:
        conn = tsc.backtest_conn()                  # fresh conn per stream (avoid idle timeout)
        cur = conn.cursor()
        cur.execute(f"DELETE FROM {tsc.TABLE} WHERE version = %s", (name,))
        deleted = cur.rowcount
        conn.commit()
        cur.close()
        n = tsc.upsert_rows(conn, rows)
        conn.close()
        print(f"  [DB] deleted {deleted} old rows, upserted {n} portfolio rows for '{name}'", flush=True)
    return tot, len(rows)


# default run order: existing streams first (replace), then margin variants (new)
ALL_ORDER = ["donchianc", "d1h_so4c", "d1h_so6c", "d1h_so8c",
             "dch30_4hc", "dch30_4h6c", "d30_4h_soc", "d30so6c", "d30so8c",
             "d30so4cm", "d30so6cm", "d30so8cm", "d1hso4cm", "d1hso6cm", "d1hso8cm",
             "d30so4f3", "d30so6f3", "d30so8f3", "d30so8f3h7"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stream", default="all", help="stream version tag or 'all'")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--symbols", nargs="*", default=None, help="restrict universe (testing)")
    args = ap.parse_args()
    if args.symbols:
        global SYMBOLS, _SYMBOLS_OVERRIDE
        SYMBOLS = [s.upper() for s in args.symbols]
        _SYMBOLS_OVERRIDE = SYMBOLS                  # also beat a stream's own universe restriction
    w_start = pd.Timestamp(args.start, tz="UTC") if args.start else DEFAULT_START
    w_end = pd.Timestamp(args.end, tz="UTC") if args.end else pd.Timestamp.now(tz="UTC")
    names = ALL_ORDER if args.stream == "all" else [args.stream]
    bad = [n for n in names if n not in STREAMS]
    if bad:
        raise SystemExit(f"unknown stream(s): {bad}")
    summary = []
    for nm in names:
        tot, nrows = run_stream(nm, w_start, w_end, args.apply)
        summary.append((nm, tot, nrows))
    print("\n=== SUMMARY (portfolio-walk, live rules) ===")
    for nm, tot, nrows in summary:
        print(f"  {nm:<12} R={tot:+8.1f}  rows={nrows}")
    if args.dry_run:
        print("\n[dry-run] no DB writes.")


if __name__ == "__main__":
    main()
