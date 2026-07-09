"""Daily ETL: transfer resolved LIVE signals -> backtest trading_signals.

Runs end-of-day on the Oracle VM (needs Binance, which US GitHub runners can't reach).
"One day behind": today's signals are skipped (not yet resolved). Each run (re)processes
the last N=3 full days and upserts — so a signal still 'active' yesterday gets re-evaluated
and updated to its terminal status on a later run. A safety-net pass also re-resolves any
row still 'active' in trading_signals regardless of age.

Live streams, each -> its own backtest version tag (2026-06-13 prune: the standalone
½TP streams v3/v4/karma_half/opus_half, the 8 Chop twins and the redundant Light cells
were removed UI+DB; kept set below):
  - main          : mode='live'    -> version='v1'     (1h, static set, ltf 60m, dedup floor 1h)
  - impulse       : mode='impulse' -> version='v2'     (1h, static set, ltf 60m, dedup floor 1h)
  - karma         : per-symbol blend -> version='karma' (source mode AND exit model
                                                        chosen per symbol by sync/karma_map.py)
  - opus          : MAIN signals -> version='opus' (kept only for the per-symbol weekday
                                                    NY session(s) in sync/opus_map.py)
  - impulse_light : impulse, kept only in the 4h-ER light band [0.20,0.35) -> version='v2_light'
  - karma_light   : karma, kept only in the 4h-ER light band [0.20,0.35)   -> version='kma_light'
  - radar_legacy  : mode='dynamic' -> version='v1-dyn' (RETIRED dynamic-symbol stream)
  - pulse         : mode='pulse'   -> version='v1-15m' (RETIRED 15m stream)

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
    # 2026-06-13: crypto re-add by user decision (XRP/LINK/DOGE were cut for weak
    # 2025-26 backtests; AVAX is new) — re-validate in the next audit.
    "XRPUSDT", "DOGEUSDT", "LINKUSDT", "AVAXUSDT",
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
    "main":         {"mode": "live",     "version": "v1",       "ltf_min": 60, "floor": "h",     "symbols": STATIC_SYMBOLS},
    "impulse":      {"mode": "impulse",  "version": "v2",       "ltf_min": 60, "floor": "h",     "symbols": STATIC_SYMBOLS},
    "radar_legacy": {"mode": "dynamic",  "version": "v1-dyn",   "ltf_min": 60, "floor": "h",     "symbols": None},
    "pulse":        {"mode": "pulse",    "version": "v1-15m",   "ltf_min": 15, "floor": "15min", "symbols": STATIC_SYMBOLS},
    # Donchian(55) breakout trend stream (sync/donchian/) — the momentum complement to
    # the RANGE/main book. Live signals are emitted hourly by sync/donchian/canli.py
    # (mode='donchian'); this resolves them -> version='donchian'. symbols=None keeps the
    # resolver universe-agnostic (only the donchian emitter writes mode='donchian').
    "donchian":     {"mode": "donchian", "version": "donchian", "ltf_min": 60, "floor": "h",     "symbols": None},
    # HYBRID: 30m breakout CONFIRMED by 4h trend direction (canli.py --tf 30m --confirm-htf
    # 4h, mode='dch30_4h'). The 4h-dir filter is applied at EMIT time, so the resolver just
    # resolves the confirmed 30m signals like any 30m stream -> version='dch30_4h'. Best
    # stream overall: +1106R across 2024-26 (every OOS year positive, fewest trades of the
    # 30m family). 2026-06-17: the base donch_30m (dominated by this) and the ½TP twin
    # dch30_4hh (2024-negative OOS) were removed.
    "dch30_4h":     {"mode": "dch30_4h", "version": "dch30_4h", "ltf_min": 30, "floor": "30min", "symbols": None},
    # 6R-target twin of the hybrid (canli.py --tf 30m --confirm-htf 4h --rr 6, mode='dch30_4h6').
    # MFE study: winners run to ~8R median, losers go straight to stop -> a wider 6R target
    # ~doubles R/trade vs 4R in ALL THREE years (2024/2025/2026) — the one OOS-robust lever.
    # Lower WR (~15% vs 23%), but resolves fast (TP median ~1.4d, SL ~6h).
    "dch30_4h6":    {"mode": "dch30_4h6", "version": "dch30_4h6", "ltf_min": 30, "floor": "30min", "symbols": None},
}

# Streams processed by `--stream all`. radar_legacy (retired dynamic stream) and pulse
# stopped emitting 2026-06-10 — pass their key explicitly to re-resolve historical rows.
# 2026-06-13 prune: the standalone ½TP streams (v3/v4, karma_half, opus_half), the 8 Chop
# twins and the redundant Light cells were removed (UI + DB). Kept set = main, impulse,
# karma, opus + the two Light twins (impulse_light, karma_light).
# "karma" is the per-symbol best-cell blend (sync/karma_map.py): it consumes the
# SAME live signals as main/impulse — per symbol it picks the source set and the
# exit model from the 2026 selection run — and tags rows version='karma'.
# 2026-06-14: live streams RETIRED. v1/v2/karma/opus + the two Light twins were all
# OOS-negative in 2025 (period-fit) and removed from UI + DB. ACTIVE_STREAMS is now empty
# so the nightly `--stream all` cron is a NO-OP and does NOT re-create the deleted rows.
# (The OOS-positive range book — range/range_q/v2_light_r — is backtest-only, refreshed by
# its own scripts: backfill_range.py / promote_range_q.py / promote_light_range.py.) To
# re-resolve a retired stream's historical rows ad hoc, still pass its key (e.g. --stream main).
# 2026-06-16: 'donchian' (trend complement) wired live. Its hourly emitter
# (sync/donchian/canli.py) writes mode='donchian' live signals; the nightly
# `--stream all` now resolves them into backtest version='donchian'.
# 2026-06-19: 'd30_4h_so' (high-WR scale-out twin) wired live. It does NOT have its own
# emitter — it consumes the SAME dch30_4h live signals and resolves them under the scale-out
# + breakeven-ride model (sync/donchian/scaleout.py), tagged version='d30_4h_so'. Handled by
# resolve_scaleout_stream (not resolve_stream, whose tsc.simulate is single-target).
ACTIVE_STREAMS = ["donchian", "dch30_4h", "dch30_4h6", "d30_4h_so"]
LIGHT_PARENTS = ("impulse", "karma")


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
            # Confirm-fill model (ict.config.ENTRY_AT_CONFIRM): realistic entry = the +buf*risk
            # confirmation level (full-TP streams only; ½TP uses its own partial resolver).
            use_confirm = (getattr(C, "ENTRY_AT_CONFIRM", False)
                           and getattr(C, "ENTRY_CONFIRM_BUF", 0.0) > 0
                           and not bool(stream.get("partial", False)))
            for w in items:
                st = w["_st"]
                exp = stream.get("expiry_min", tsc.EXPIRY_MINUTES)
                cts = st + pd.Timedelta(minutes=stream["ltf_min"])
                if use_confirm:
                    cf = tsc.confirm_fill(df1m, cts, w["direction"], float(w["entry"]),
                                          float(w["sl"]), expiry_minutes=exp)
                    if cf is None:
                        continue              # failed directional confirmation -> no row
                    fill_ts, entry_eff, risk_eff = cf
                    outcome = tsc.resolve_market(df1m, fill_ts, w["direction"], entry_eff,
                                                 float(w["sl"]), float(w["tp"]), risk_eff,
                                                 max_hold_minutes=3 * 24 * 60)
                    erow = entry_eff
                else:
                    if not tsc.entry_confirmed(df1m, cts, w["direction"], float(w["entry"]),
                                               float(w["sl"]), expiry_minutes=exp):
                        continue              # failed directional confirmation -> no row
                    outcome = tsc.simulate(sym, st, w["direction"], float(w["entry"]),
                                           float(w["sl"]), float(w["tp"]), df1m=df1m,
                                           ltf_minutes=stream["ltf_min"], expiry_minutes=exp,
                                           max_hold_minutes=3 * 24 * 60)   # uniform 3-day time limit
                    erow = w["entry"]
                status_counts[outcome["status"]] = status_counts.get(outcome["status"], 0) + 1
                row = tsc.build_row(sym, st, w["direction"], erow, w["sl"], w["tp"],
                                    outcome, strategy=w.get("strategy"), quality=w.get("quality"),
                                    confluence_score=w.get("confluence_score"))
                # realistic-entry resolution -> the 'c' twin tag, never the entry@close original
                row["version"] = stream["version"] + ("c" if use_confirm else "")
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


# light version tags per base stream (<=10 chars; mirror backfill_light.LIGHT_TAG)
LIGHT_TAG = {"v2": "v2_light", "karma": "kma_light"}


def _light_keep():
    """Returns keep(symbol, bar_open_utc) gating on the 4h-ER LIGHT band-pass
    (ER in [0.20,0.35)), or a pass-through if regime.py is unavailable. INCLUSION
    gate — missing ER drops the signal (light not confirmed)."""
    try:
        import regime
    except ImportError:
        print("  [light] sync/regime.py yok — band kapısı atlandı (hepsi geçer)")
        return lambda sym, st: True
    cache, now = {}, pd.Timestamp.now(tz="UTC")
    def keep(sym, st):
        if sym not in cache:
            cache[sym] = regime.build_er(sym, now - pd.Timedelta(days=60), now)
        return regime.light_ok(cache[sym], st)
    return keep


def resolve_light(name, live, bt, w_start, w_end, now, *, rescan, symbols_override=None) -> list:
    """LIGHT variant of a base stream: resolve the parent's live signals, but keep
    only the ones fired in the 4h-ER light band [0.20,0.35). name is 'impulse_light'
    or 'karma_light'. Re-tags rows with the short light version."""
    base = name[:-6]                                   # strip '_light'
    keep = _light_keep()
    if base == "karma":
        rows = resolve_karma(live, bt, w_start, w_end, now, rescan=rescan,
                             symbols_override=symbols_override, version="karma")
        rows = [r for r in rows if keep(r["symbol"], pd.Timestamp(r["signal_time"]).tz_convert("UTC"))]
    else:                                              # impulse
        rows, _ = resolve_stream(name, STREAMS[base], live, bt, w_start, w_end, now,
                                 rescan=rescan, symbols_override=symbols_override, keep=keep)
    base_ver = STREAMS[base]["version"] if base in STREAMS else base
    tag = LIGHT_TAG[base_ver]
    for r in rows:
        r["version"] = tag
    return rows


def resolve_scaleout_stream(live, bt, w_start, w_end, now, *, rescan, symbols_override=None) -> list:
    """DONCHIAN high-WR scale-out (version='d30_4h_so'): consume the dch30_4h live signals
    and resolve them under the scale-out + breakeven-ride model (sync/donchian/scaleout.py)
    rather than the standard single-target tsc.simulate. Same entry/-1R stop as dch30_4h;
    book 60% at +1R, runner rides to breakeven / a 20-day time exit. A still-riding runner
    whose 20-day window is not yet covered is left ACTIVE (active_if_incomplete=True) so it
    is re-resolved on a later run instead of being booked early."""
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(tsc.__file__).resolve().parent / "donchian"))
    import scaleout as so

    mode, version, ltf_min, floor = "dch30_4h", so.VERSION, 30, "30min"
    symbols = symbols_override if symbols_override is not None else so.SO_SYMBOLS
    work = fetch_live_window(live, mode, symbols, w_start, w_end)
    print(f"  [{version}] live mode='{mode}' in window: {len(work)}")
    if rescan:
        active = fetch_active_rows(bt, version)
        print(f"  [{version}] active rows to re-check: {len(active)}")
        work += active

    seen, deduped = set(), []
    sym_filter = set(symbols) if symbols else None
    for w in work:
        if sym_filter and w["symbol"] not in sym_filter:
            continue
        st = pd.Timestamp(w["signal_time"]).tz_convert("UTC").floor(floor)
        key = (w["symbol"], st, (w["direction"] or "").upper())
        if key in seen:
            continue
        seen.add(key)
        w["_st"] = st
        deduped.append(w)

    by_sym = defaultdict(list)
    for w in deduped:
        by_sym[w["symbol"]].append(w)

    rows, status_counts, skipped = [], {}, 0
    for sym, items in by_sym.items():
        earliest = min(w["_st"] for w in items)
        df1m = tsc.fetch_1m(sym, earliest - pd.Timedelta(minutes=2), now)
        if df1m.empty:
            print(f"    [{version}] {sym}: no klines, skipping {len(items)}")
            skipped += len(items)
            continue
        for w in items:
            st = w["_st"]
            outcome = so.resolve_scaleout(sym, st, w["direction"], float(w["entry"]),
                                          float(w["sl"]), float(w["tp"]), df1m=df1m,
                                          ltf_minutes=ltf_min, expiry_minutes=tsc.EXPIRY_MINUTES,
                                          active_if_incomplete=True)
            if outcome is None:               # failed directional confirmation -> no row
                continue
            status_counts[outcome["status"]] = status_counts.get(outcome["status"], 0) + 1
            row = tsc.build_row(sym, st, w["direction"], outcome.get("entry_eff", w["entry"]),
                                w["sl"], outcome.get("cap_price", w["tp"]), outcome, strategy=w.get("strategy"),
                                quality=w.get("quality"), confluence_score=w.get("confluence_score"))
            row["version"] = version
            rows.append(row)
    print(f"  [{version}] resolved {len(rows)} rows, status={status_counts}, skipped={skipped}")
    return rows


def resolve_opus(live, bt, w_start, w_end, now, *, rescan, symbols_override=None,
                 half=False, version="opus") -> list:
    """OPUS stream: MAIN ('live') signals, kept only for symbols+sessions in the
    per-symbol weekday NY-session allowlist (sync/opus_map.py). version='opus' (full
    TP); half=True -> ½TP+BE exit on the same gated signals (version='opus_half')."""
    try:
        from opus_map import OPUS_MAP, opus_allows
    except ImportError:
        print("  [opus] sync/opus_map.py yok — stream atlandı")
        return []
    syms = sorted(OPUS_MAP) if symbols_override is None else [s for s in symbols_override if s in OPUS_MAP]
    cfg = {"mode": "live", "version": version, "ltf_min": 60, "floor": "h",
           "symbols": syms, "partial": half}
    rows, _ = resolve_stream(version, cfg, live, bt, w_start, w_end, now, rescan=rescan,
                             keep=lambda sym, st: opus_allows(sym, st))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3, help="trailing full days to (re)process")
    # Default is MAIN ONLY. radar_legacy (retired dynamic stream) & pulse were
    # disabled 2026-06-10 — pass their key explicitly to resolve legacy rows.
    # Default is now "all" (a no-op with ACTIVE_STREAMS empty) so a bare run does NOT
    # re-create retired rows. Pass an explicit key to re-resolve a retired stream ad hoc.
    ap.add_argument("--stream", choices=list(STREAMS) + ["karma", "opus", "all", "d30_4h_so"]
                    + [f"{b}_light" for b in LIGHT_PARENTS], default="all")
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
        if name == "karma":
            all_rows += resolve_karma(live, bt, w_start, w_end, now,
                                      rescan=not args.no_active_rescan,
                                      symbols_override=args.symbols, version="karma")
            continue
        if name == "opus":
            all_rows += resolve_opus(live, bt, w_start, w_end, now,
                                     rescan=not args.no_active_rescan,
                                     symbols_override=args.symbols, version="opus")
            continue
        if name == "d30_4h_so":
            all_rows += resolve_scaleout_stream(live, bt, w_start, w_end, now,
                                                rescan=not args.no_active_rescan,
                                                symbols_override=args.symbols)
            continue
        if name.endswith("_light"):
            all_rows += resolve_light(name, live, bt, w_start, w_end, now,
                                      rescan=not args.no_active_rescan,
                                      symbols_override=args.symbols)
            continue
        rows, _ = resolve_stream(name, STREAMS[name], live, bt, w_start, w_end, now,
                                 rescan=not args.no_active_rescan,
                                 symbols_override=args.symbols)
        all_rows += rows

    # Safety net: drop any US-stock-perp rows before they reach the backtest book. Donchian is
    # crypto + metals only (2026-07-09 owner decision); the generators are already restricted, but
    # this guards against a stray stock signal lingering in the live feed being resolved back in.
    from donchian import strategy as _dstrat
    _before = len(all_rows)
    all_rows = [r for r in all_rows if r["symbol"] not in _dstrat.STOCK_SYMBOLS]
    if len(all_rows) != _before:
        print(f"  stock-filter: dropped {_before - len(all_rows)} US-stock rows (crypto+metals only)")

    # Self-heal the LIVE signals table: physically delete Donchian breakouts that
    # CONCLUSIVELY failed directional entry confirmation (adverse buf*risk before
    # favourable, or fill window elapsed without confirming). The emit-time pre-filter
    # already blocks new unconfirmed signals and the dashboard re-checks at display time;
    # this is the third leg so a reversed breakout never lingers as a live row. Pending
    # (still-open-window) signals are kept. Best-effort: never let it break the sync.
    try:
        from donchian import prune_live
        pr = prune_live.prune(live, now=now, apply=not args.dry_run, verbose=False)
        verb = "would delete" if args.dry_run else "deleted"
        print(f"  live prune: {verb} {pr['invalid']} invalid "
              f"(confirmed={pr['confirmed']} pending={pr['pending']} scanned={pr['scanned']})")
    except Exception as e:  # noqa: BLE001
        print(f"  live prune skipped: {e}")
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

    # TOTAL/2/3 market-cap ground-truth snapshot — accrues forward, never blocks the
    # sync (it's a research/regime-map feed, not part of the trade pipeline).
    try:
        import marketcap
        s = marketcap.snapshot_live()
        print(f"  marketcap snapshot: TOTAL3={marketcap._human(s['total3'])} "
              f"BTC.D={s['btc_d']*100:.1f}%")
    except Exception as e:  # noqa: BLE001 — never let the regime feed break the sync
        print(f"  marketcap snapshot skipped: {e}")


if __name__ == "__main__":
    main()
