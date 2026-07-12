"""Backtest backfill for the ATRX-GATED d30so8f3h7 twins (2026-07-12 symbol-state study).

Same signals + same scale-out exit model as d30so8f3h7 / OPUS (30m+4h, close_frac 0.3, cap 8R,
7-day limit, +0.5R confirm, CRYPTO-only universe), but a signal is only TAKEN if the symbol's
DAILY volatility state passes the ATRX gate at signal time. ATRX = ATR(5d)/ATR(20d) computed on
daily bars STRICTLY BEFORE the signal's day (previous-day close — no lookahead). Two versions:

  d30so8f3sq  "OPUS·SQZ"    atrx < 0.8   — squeeze-only. The WR play: the symbol's daily vol is
                                           compressed; the breakout rides the expansion that follows.
  d30so8f3q5  "OPUS·Q5"     atrx <= 1.25 — no-expansion. The totR play: only skip entries where
                                           daily vol has ALREADY expanded (the worst state bucket).

Rationale (scratchpad/opus_scn_*.py + opus_dyn_*.py, 2026-07-12): across 39 symbol-state
scenarios on 101 Binance crypto perps, the ATRX family was the ONLY condition that held in
2024 AND 2025 AND 2026 as a true dynamic-universe re-walk. Everything else (volume bands,
weekly losers/winners, 30d-low proximity...) flipped sign out-of-sample.

Universe = DYNAMIC, not OPUS's fixed 18: the CORE 18 (book from 2024-01) + 83 more Binance
crypto perps (book from 2026-01, where the shared 1m cache starts) — any symbol passing the
ATRX gate generates signals ("filtreyi geçen her sembol sinyal üretsin", 2026-07-12).

Backtest-only (no live emit; live OPUS is untouched). Nightly cron refresh, like volgate.

    python sync/donchian/atrx_backfill.py --dry-run
    python sync/donchian/atrx_backfill.py --apply
"""
from __future__ import annotations
import sys, os, argparse
from pathlib import Path
_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent)); sys.path.insert(0, str(_HERE.parents[1]))
sys.path.insert(0, str(_HERE.parents[1] / "live_exec"))
os.environ.setdefault("DCH_ENTRY_AT_CONFIRM", "1")
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import _bootenv  # noqa: E402,F401
import portfolio_backfill as pb  # noqa: E402
import trade_sync_common as tsc  # noqa: E402

ST = pb.STREAMS["d30so8f3h7"]
ATR_FAST, ATR_SLOW = 5, 20
VERSIONS = [
    ("d30so8f3sq", lambda x: x < 0.8),    # squeeze-only (WR play)
    ("d30so8f3q5", lambda x: x <= 1.25),  # no-expansion / skip the worst vol bucket (totR play)
]

# ── Universe (2026-07-12 owner decision: "filtreyi geçen HER sembol sinyal üretsin") ──
# CORE = OPUS'un 18 kripto perp'i, kitap 2024-01-01'den (çok-yıllık 1m cache mevcut).
# BROAD = çalışmanın kalan 83 Binance kripto perp'i (hisse-perp + metal HARİÇ), kitap
# 2026-01-01'den — 1m cache kapsamı burada başlar; daha erken başlatmak her sembol için
# ~2 yıl 1m fetch'i gerektirirdi. Delisted/veri-yok semboller per-symbol try/except ile atlanır.
CORE_START = pd.Timestamp("2024-01-01", tz="UTC")
BROAD_START = pd.Timestamp("2026-01-01", tz="UTC")
BROAD_SYMBOLS = [
    "1000BONKUSDT", "1000FLOKIUSDT", "1000LUNCUSDT", "1000SHIBUSDT", "2ZUSDT", "AAVEUSDT",
    "AEROUSDT", "ALGOUSDT", "APTUSDT", "ASTERUSDT", "ATOMUSDT", "BCHUSDT", "BEATUSDT", "BSVUSDT",
    "BUSDT", "CAKEUSDT", "CCUSDT", "CFXUSDT", "CRVUSDT", "DASHUSDT", "DEXEUSDT", "DOTUSDT",
    "ENAUSDT", "ETCUSDT", "ETHFIUSDT", "FFUSDT", "FILUSDT", "GRASSUSDT", "GRTUSDT", "GWEIUSDT",
    "HBARUSDT", "HYPEUSDT", "ICPUSDT", "INJUSDT", "JASMYUSDT", "JSTUSDT", "JTOUSDT", "JUPUSDT",
    "KAIAUSDT", "KASUSDT", "KITEUSDT", "LABUSDT", "LDOUSDT", "LITUSDT", "LTCUSDT", "MONUSDT",
    "MORPHOUSDT", "MUSDT", "NIGHTUSDT", "OPUSDT", "PENDLEUSDT", "PENGUUSDT", "PIEVERSEUSDT",
    "POLUSDT", "PUMPUSDT", "PYTHUSDT", "QNTUSDT", "RENDERUSDT", "SEIUSDT", "SKYUSDT", "SPXUSDT",
    "STABLEUSDT", "STRKUSDT", "STXUSDT", "SUNUSDT", "TAOUSDT", "TIAUSDT", "TRUMPUSDT", "TRXUSDT",
    "UBUSDT", "UNIUSDT", "VELVETUSDT", "VETUSDT", "VIRTUALUSDT", "VVVUSDT", "WLDUSDT", "WLFIUSDT",
    "XLMUSDT", "XMRUSDT", "XPLUSDT", "XTZUSDT", "ZECUSDT", "ZROUSDT",
]

_D: dict = {}


def _atrx_series(sym):
    """Daily ATR(5)/ATR(20) indexed by UTC day. Cached per symbol for the run."""
    if sym not in _D:
        d = tsc.fetch_klines(sym, "1d",
                             int(pd.Timestamp("2023-09-01", tz="UTC").timestamp() * 1000),
                             int(pd.Timestamp.now(tz="UTC").timestamp() * 1000))
        s = None
        if d is not None and not d.empty:
            h, l, c = d["high"].astype(float), d["low"].astype(float), d["close"].astype(float)
            tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
            s = tr.rolling(ATR_FAST).mean() / tr.rolling(ATR_SLOW).mean()
            s.index = pd.to_datetime(s.index, utc=True).normalize()
        _D[sym] = s
    return _D[sym]


def _atrx(sym, ts):
    """ATRX known at the signal's day: the value of the LAST day strictly before it (D-1 close)."""
    s = _atrx_series(sym)
    if s is None:
        return np.nan
    day = pd.Timestamp(ts)
    day = (day.tz_localize("UTC") if day.tz is None else day.tz_convert("UTC")).normalize()
    prior = s.loc[s.index < day].dropna()
    return float(prior.iloc[-1]) if len(prior) else np.nan


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true"); g.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    w_end = pd.Timestamp.now(tz="UTC")
    core = list(ST.symbols or pb.SYMBOLS)
    plan = [(s, CORE_START) for s in core] + [(s, BROAD_START) for s in BROAD_SYMBOLS]
    print(f"=== ATRX twins of d30so8f3h7 | core {len(core)} sym ({CORE_START.date()}..) + "
          f"broad {len(BROAD_SYMBOLS)} sym ({BROAD_START.date()}..) -> {w_end.date()} ===", flush=True)

    kept = {v: [] for v, _ in VERSIONS}
    for sym, w_start in plan:
        try:
            ev = pb.build_events(sym, ST, w_start, w_end)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {sym}: {type(e).__name__}: {e}", flush=True)
            continue
        if not ev:
            continue
        gates = {id(e): _atrx(sym, e["signal_ts"]) for e in ev}
        counts = []
        for ver, ok in VERSIONS:
            sel = [e for e in ev if not np.isnan(gates[id(e)]) and ok(gates[id(e)])]
            kept[ver] += sel
            counts.append(f"{ver[-2:]}:{len(sel)}")
        print(f"  {sym:<14} {len(ev):>4} events -> {' '.join(counts)}", flush=True)

    for ver, _ in VERSIONS:
        # CORE_START güvenli: _load_1m cache varken baş tarafı fetch etmez (yalnız kuyruk);
        # broad sembollerin frame'i cache'in başladığı yerden gelir ve tüm event'lerini kapsar.
        realized = pb.walk(kept[ver], ST, CORE_START, w_end)
        rows = pb.to_rows(realized, ST)
        for r in rows:
            r["version"] = ver                      # override d30so8f3h7 -> gated tag
        closed = [r for r in realized if r["r"] is not None]
        tot = sum(r["r"] for r in closed)
        wr = round(100 * sum(1 for r in closed if r["r"] > 0) / len(closed)) if closed else 0
        sl = round(100 * sum(1 for r in closed if r["status"] == "closed_sl") / len(closed)) if closed else 0
        print(f"\n[{ver}] {len(rows)} rows · closed={len(closed)} · R={tot:+.1f} · WR={wr}% · "
              f"SLrate={sl}% · active={len(realized) - len(closed)}", flush=True)
        if args.apply:
            conn = tsc.backtest_conn(); cur = conn.cursor()
            cur.execute(f"DELETE FROM {tsc.TABLE} WHERE version = %s", (ver,))
            deleted = cur.rowcount; conn.commit(); cur.close()
            n = tsc.upsert_rows(conn, rows); conn.close()
            print(f"  [DB] deleted {deleted} old, upserted {n} rows for version='{ver}'", flush=True)
        else:
            print(f"  [dry-run] {len(rows)} rows would upsert.", flush=True)


if __name__ == "__main__":
    main()
