"""Daily ETL: transfer resolved LIVE signals -> backtest trading_signals.

Runs end-of-day on the Oracle VM (needs Binance, which US GitHub runners can't reach).
"One day behind": today's signals are skipped (not yet resolved). Each run (re)processes
the last N=3 full days and upserts — so a signal still 'active' yesterday gets re-evaluated
and updated to its terminal status on a later run. A safety-net pass also re-resolves any
row still 'active' in trading_signals regardless of age.

Live streams, each -> its own backtest version tag:
  - main         : mode='live'    -> version='v1'     (1h, static set, ltf 60m, dedup floor 1h)
  - impulse      : mode='impulse' -> version='v2'     (1h, static set, ltf 60m, dedup floor 1h)
  - main_half    : mode='live'    -> version='v3'     (SAME live signals as main, resolved
  - impulse_half : mode='impulse' -> version='v4'      under the partial-TP + breakeven exit
                                                       model — PARTIAL_TP_ENABLED per stream)
  - karma        : per-symbol blend -> version='karma' (source mode AND exit model
                                                       chosen per symbol by sync/karma_map.py)
  - karma_half   : per-symbol blend -> version='karma_half' (same per-symbol source set
                                                       as karma, but ALWAYS the ½TP+BE exit)
  - opus         : MAIN signals -> version='opus' (kept only for the per-symbol NY
                                                   session(s) in sync/opus_map.py)
  - radar_legacy : mode='dynamic' -> version='v1-dyn' (RETIRED dynamic-symbol stream)
  - pulse        : mode='pulse'   -> version='v1-15m' (RETIRED 15m stream)

Idempotent: upsert key (symbol, signal_time, trade_type, version) — re-running never
duplicates; it only updates status/exit/pnl when they change.

Usage:
  python sync/sync_daily.py                       # all 3 streams (cron)
  python sync/sync_daily.py --stream pulse        # one stream only
  python sync/sync_daily.py --dry-run             # preview, no DB writes
  python sync/sync_daily.py --days 3 --no-active-rescan
"""
from __future__ import annotations

import argparse
from collections import defaultdict

import pandas as pd

import trade_sync_common as tsc
from ict import config as C   # backtest/ict (path added by tsc) — partial-TP exit-model flag

# Curated static set (MAIN + PULSE). RADAR picks are dynamic -> no allow-list.
# 2026-06-10: DOGE/GOOGL/PLTR/TSLA removed after the 2026 Jan-Jun v1 audit
# (mirrors dag/dag.py SYMBOLS). 2026-06-12: PLTR/TSLA re-added by user decision
# with the tokenized-equity expansion.
STATIC_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
    "1000PEPEUSDT", "WIFUSDT", "SUIUSDT",
    "NEARUSDT", "FETUSDT", "ADAUSDT", "SUSDT",
    "ARBUSDT", "ORDIUSDT", "ONDOUSDT",
    "XAUUSDT", "XAGUSDT",
    # Stock-backed perps (underlying equities)
    "NVDAUSDT", "METAUSDT",
    "AMZNUSDT", "COINUSDT", "MSTRUSDT",
    # 2026-06-12 tokenized-equity expansion (PLTR/TSLA re-added by user decision,
    # reversing the 2026-06-10 cut). Listings span 2026-01-28 .. 2026-06-08.
    "CRCLUSDT", "PLTRUSDT", "TSLAUSDT", "INTCUSDT", "HOODUSDT",
    "MSFTUSDT", "AVGOUSDT", "BABAUSDT", "BXUSDT", "HPEUSDT",
    "AMATUSDT", "CRWDUSDT", "CRDOUSDT", "AAOIUSDT", "IWMUSDT",
]

# Each live stream resolves the SAME way (emitted live signals + still-active rows
# -> outcomes on 1m), differing only in source mode, bar timeframe (-> ltf_minutes
# + dedup floor), symbol scope and exit model ("partial": resolve under the
# partial-TP + breakeven model — ½TP streams v3/v4 read the SAME live signals as
# main/impulse, only the exit differs).
STREAMS = {
    "main":         {"mode": "live",    "version": "v1",     "ltf_min": 60, "floor": "h",     "symbols": STATIC_SYMBOLS},
    "impulse":      {"mode": "impulse", "version": "v2",     "ltf_min": 60, "floor": "h",     "symbols": STATIC_SYMBOLS},
    "main_half":    {"mode": "live",    "version": "v3",     "ltf_min": 60, "floor": "h",     "symbols": STATIC_SYMBOLS, "partial": True},
    "impulse_half": {"mode": "impulse", "version": "v4",     "ltf_min": 60, "floor": "h",     "symbols": STATIC_SYMBOLS, "partial": True},
    "radar_legacy": {"mode": "dynamic", "version": "v1-dyn", "ltf_min": 60, "floor": "h",     "symbols": None},
    "pulse":        {"mode": "pulse",   "version": "v1-15m", "ltf_min": 15, "floor": "15min", "symbols": STATIC_SYMBOLS},
}

# Streams processed by `--stream all`. radar_legacy (the retired dynamic stream,
# formerly keyed "radar") and pulse stopped emitting 2026-06-10 — pass their key
# explicitly to re-resolve historical rows. The ½TP streams ride the nightly cron
# so v3/v4 stay current without manual backfills (dag/halftp_monitor.py covers the
# intraday cards; this is the end-of-day authoritative resolution).
# "karma" is the per-symbol best-cell blend (sync/karma_map.py): it consumes the
# SAME live signals as main/impulse — per symbol it picks the source set and the
# exit model from the 2026 selection run — and tags rows version='karma'.
ACTIVE_STREAMS = ["main", "impulse", "main_half", "impulse_half", "karma", "karma_half", "opus"]


def fetch_live_window(conn, mode, symbols, w_start, w_end) -> list[dict]:
    """live signals for `mode` with signal_time in [w_start, w_end). symbols=None => all."""
    cur = conn.cursor()
    base = """
        SELECT symbol, signal_time, direction, entry, sl, tp, strategy, quality, confluence_score
        FROM ict_trade.signals
        WHERE mode = %s AND signal_time >= %s AND signal_time < %s
    """
    params = [mode, w_start.to_pydatetime(), w_end.to_pydatetime()]
    if symbols:
        base += " AND symbol = ANY(%s)"
        params.append(symbols)
    base += " ORDER BY symbol, signal_time"
    cur.execute(base, tuple(params))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return rows


def fetch_active_rows(conn, version) -> list[dict]:
    """trading_signals rows still 'active' (entered, unresolved) for `version` — re-check."""
    cur = conn.cursor()
    cur.execute(f"""
        SELECT symbol, signal_time, direction, entry_price AS entry, sl_price AS sl,
               tp_price AS tp, strategy, quality, confluence_score
        FROM {tsc.TABLE}
        WHERE version = %s AND lower(coalesce(status,'')) = 'active'
    """, (version,))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return rows


def resolve_stream(name, stream, live, bt, w_start, w_end, now, *,
                   rescan: bool, symbols_override=None, keep=None) -> tuple[list, dict]:
    """Pull a stream's live signals + active rows, resolve on 1m, return tagged rows.

    `keep(symbol, bar_open_utc) -> bool` is an optional per-signal gate (OPUS uses it
    for its per-symbol NY-session allowlist); None = keep every signal."""
    symbols = symbols_override if symbols_override is not None else stream["symbols"]
    work = fetch_live_window(live, stream["mode"], symbols, w_start, w_end)
    print(f"  [{name}] live mode='{stream['mode']}' in window: {len(work)}")
    if rescan:
        active = fetch_active_rows(bt, stream["version"])
        print(f"  [{name}] active rows to re-check: {len(active)}")
        work += active

    # dedup by (symbol, floored time, direction); keep first (live window before active)
    seen, deduped = set(), []
    sym_filter = set(symbols) if symbols else None
    for w in work:
        if sym_filter and w["symbol"] not in sym_filter:
            continue
        st = pd.Timestamp(w["signal_time"]).tz_convert("UTC").floor(stream["floor"])
        if keep is not None and not keep(w["symbol"], st):
            continue
        key = (w["symbol"], st, (w["direction"] or "").upper())
        if key in seen:
            continue
        seen.add(key)
        w["_st"] = st
        deduped.append(w)

    by_sym = defaultdict(list)
    for w in deduped:
        by_sym[w["symbol"]].append(w)

    # ½TP streams resolve under the partial-TP + breakeven exit model. The flag is
    # process-global (read by backtester.simulate_signal), so set it for this stream's
    # resolution only and ALWAYS restore — a v3/v4 pass must never leak into v1/v2.
    prev_partial = C.PARTIAL_TP_ENABLED
    C.PARTIAL_TP_ENABLED = bool(stream.get("partial", False))
    rows, status_counts, skipped = [], {}, 0
    try:
        for sym, items in by_sym.items():
            earliest = min(w["_st"] for w in items)
            df1m = tsc.fetch_1m(sym, earliest - pd.Timedelta(minutes=2), now)
            if df1m.empty:
                print(f"    [{name}] {sym}: no klines, skipping {len(items)}")
                skipped += len(items)
                continue
            for w in items:
                st = w["_st"]
                outcome = tsc.simulate(sym, st, w["direction"], float(w["entry"]),
                                       float(w["sl"]), float(w["tp"]), df1m=df1m,
                                       ltf_minutes=stream["ltf_min"],
                                       expiry_minutes=stream.get("expiry_min", tsc.EXPIRY_MINUTES))
                status_counts[outcome["status"]] = status_counts.get(outcome["status"], 0) + 1
                row = tsc.build_row(sym, st, w["direction"], w["entry"], w["sl"], w["tp"],
                                    outcome, strategy=w.get("strategy"), quality=w.get("quality"),
                                    confluence_score=w.get("confluence_score"))
                row["version"] = stream["version"]
                rows.append(row)
    finally:
        C.PARTIAL_TP_ENABLED = prev_partial
    print(f"  [{name}] resolved {len(rows)} rows, status={status_counts}, skipped={skipped}")
    return rows, status_counts


def resolve_karma(live, bt, w_start, w_end, now, *, rescan, symbols_override=None,
                  force_half=False, version="karma") -> list:
    """KARMA stream: per symbol, resolve its live parent signals under the cell the
    2026 selection chose (set in {main,impulse} x exit in {tam,yarim}). Symbols are
    grouped into (set, exit) buckets and each bucket rides resolve_stream with the
    matching mode + partial flag; every row is tagged `version`.

    force_half=True forces the ½TP+BE exit on every symbol (keeping each symbol's
    chosen SOURCE set) — the KARMA ½TP stream (version='karma_half')."""
    try:
        from karma_map import KARMA_MAP
    except ImportError:
        print("  [karma] sync/karma_map.py yok — stream atlandı")
        return []
    buckets = defaultdict(list)
    for sym, cfg in KARMA_MAP.items():
        if symbols_override is not None and sym not in symbols_override:
            continue
        eff_half = True if force_half else cfg["half"]
        buckets[(cfg["set"], eff_half)].append(sym)
    rows = []
    for (set_name, half), syms in sorted(buckets.items()):
        cfg = {"mode": "live" if set_name == "main" else "impulse", "version": version,
               "ltf_min": 60, "floor": "h", "symbols": sorted(syms), "partial": half}
        r, _ = resolve_stream(f"{version}[{set_name}/{'yarim' if half else 'tam'}]",
                              cfg, live, bt, w_start, w_end, now, rescan=rescan)
        rows += r
    return rows


def resolve_opus(live, bt, w_start, w_end, now, *, rescan, symbols_override=None) -> list:
    """OPUS stream: MAIN ('live') signals, kept only for symbols+sessions in the
    per-symbol NY-session allowlist (sync/opus_map.py). version='opus', full-TP."""
    try:
        from opus_map import OPUS_MAP, opus_allows
    except ImportError:
        print("  [opus] sync/opus_map.py yok — stream atlandı")
        return []
    syms = sorted(OPUS_MAP) if symbols_override is None else [s for s in symbols_override if s in OPUS_MAP]
    cfg = {"mode": "live", "version": "opus", "ltf_min": 60, "floor": "h", "symbols": syms}
    rows, _ = resolve_stream("opus", cfg, live, bt, w_start, w_end, now, rescan=rescan,
                             keep=lambda sym, st: opus_allows(sym, st))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3, help="trailing full days to (re)process")
    # Default is MAIN ONLY. radar_legacy (retired dynamic stream) & pulse were
    # disabled 2026-06-10 — pass their key explicitly to resolve legacy rows.
    ap.add_argument("--stream", choices=list(STREAMS) + ["karma", "karma_half", "opus", "all"], default="main")
    ap.add_argument("--no-active-rescan", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--symbols", nargs="*", default=None, help="override symbol scope (all streams)")
    args = ap.parse_args()

    now = pd.Timestamp.now(tz="UTC")
    today0 = now.normalize()                       # today 00:00 UTC
    w_end = today0                                 # exclude today => "1 day behind"
    w_start = today0 - pd.Timedelta(days=args.days)
    names = ACTIVE_STREAMS if args.stream == "all" else [args.stream]
    print(f"=== daily sync | window [{w_start.date()} .. {w_end.date()}) "
          f"| streams={names} | dry_run={args.dry_run} ===")

    live = tsc.live_conn()
    bt = tsc.backtest_conn()

    all_rows = []
    for name in names:
        if name in ("karma", "karma_half"):
            all_rows += resolve_karma(live, bt, w_start, w_end, now,
                                      rescan=not args.no_active_rescan,
                                      symbols_override=args.symbols,
                                      force_half=(name == "karma_half"), version=name)
            continue
        if name == "opus":
            all_rows += resolve_opus(live, bt, w_start, w_end, now,
                                     rescan=not args.no_active_rescan,
                                     symbols_override=args.symbols)
            continue
        rows, _ = resolve_stream(name, STREAMS[name], live, bt, w_start, w_end, now,
                                 rescan=not args.no_active_rescan,
                                 symbols_override=args.symbols)
        all_rows += rows
    live.close()

    if args.dry_run:
        for r in all_rows[:12]:
            print(f"    {r['version']:<7} {r['symbol']} {r['signal_time']} {r['trade_type']} "
                  f"{r['status']} pnl_r={r['pnl_r']}")
        print(f"  [dry-run] no DB writes ({len(all_rows)} rows would upsert).")
        bt.close()
        return

    n = tsc.upsert_rows(bt, all_rows)
    bt.close()
    print(f"  upserted {n} rows into {tsc.TABLE}")


if __name__ == "__main__":
    main()
