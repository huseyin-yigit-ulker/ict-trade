"""LIVE-faithful PORTFOLIO backfill for the SUPPLY/DEMAND video strategy (version='sdv').

Mechanizes the YouTube supply/demand strategy (zone = origin of a >=3-candle, >=1-ATR impulse;
retest + 8-EMA crossover + engulfing confluence on 15m; SL beyond zone distal; TP at the prior
swing key-level, RR-clipped). Run under the SAME live portfolio rules the donchian book uses
(sync/donchian/portfolio_backfill.py): ONE position per symbol, a SAME-direction signal while
open is IGNORED, an OPPOSITE confirmed one REVERSES (mark-to-market + flip), no cross-symbol
cap, +0.5R confirm-entry. One continuous walk 2024-01-01..now over the full 40-sym universe.

Refined config = the 2026 sweep winner: MIN_RISK_PCT=0.0020 fee-floor (kills the tiny-stop
fee-blowup tail) on top of the baseline detector. Backtest-only stream (no live scanner / cron),
mirroring how 'range' shipped.

    python sync/supdem_backfill.py --dry-run            # resolve + walk, NO DB write
    python sync/supdem_backfill.py --apply              # DELETE old 'sdv' rows + upsert
    python sync/supdem_backfill.py --apply --symbols BTCUSDT ETHUSDT   # restrict (testing)
"""
from __future__ import annotations
import os, sys, argparse
from pathlib import Path

os.environ.setdefault("ENTRY_AT_CONFIRM", "1")
os.environ.setdefault("ENTRY_CONFIRM_BUF", "0.5")

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent))                       # sync/
sys.path.insert(0, str(_HERE.parent / "donchian"))          # sync/donchian
sys.path.insert(0, str(_HERE.parent / "live_exec"))         # sync/live_exec

import numpy as np                                          # noqa: E402
import pandas as pd                                         # noqa: E402
import _bootenv                                             # noqa: E402,F401  forces DCH_ENTRY_AT_CONFIRM=1
import trade_sync_common as tsc                             # noqa: E402
import strategy as strat                                    # noqa: E402
import scaleout as so                                       # noqa: E402  (so._load_1m warm cache + M1_TAIL)

VERSION = "sdv"
DEFAULT_START = pd.Timestamp("2024-01-01", tz="UTC")
SYMBOLS = list(strat.SYMBOLS)                               # full universe (40); no-data symbols skip

# ---- detector config (2026 sweep winner) ----
IMPULSE_N = 3              # consecutive same-color candles = "aggressive" impulse
IMP_ATR = 1.0             # min impulse net displacement, in ATR(14)
EMA_LEN = 8               # confluence EMA (video uses 8)
RR_MIN, RR_MAX, RR_DEF = 1.5, 6.0, 2.5
ZONE_MAXAGE_BARS = 24 * 21  # zone valid up to ~21 days (1h bars) waiting for a retest
SL_BUF_ATR = 0.1          # SL buffer beyond zone distal, in ATR
SWING_LOOKBACK = 60       # 1h bars back to find the "next key level" swing
MIN_RISK_PCT = 0.0020     # fee-floor: skip trades whose stop < this fraction of price
CONFIRM_BUF = 0.5         # +0.5R confirm-entry
EXPIRY_MIN = 180          # confirm-fill window (minutes) after the 15m entry close
MAX_HOLD_MIN = 14 * 24 * 60  # 14-day time-stop per position

# Bounded LRU of 1m frames (full-span 1m for 40 symbols won't fit in RAM at once).
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


# ---------------------------------------------------------------- detector
def _atr(df, n=14):
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def _ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def _detect_zones(h1):
    o, h, l, c = h1["open"].values, h1["high"].values, h1["low"].values, h1["close"].values
    a = _atr(h1).values
    n = len(h1)
    green = c > o
    zones = []
    i = 1
    while i < n - IMPULSE_N:
        if np.isnan(a[i]):
            i += 1; continue
        run = 0
        while i + run < n and green[i + run]:
            run += 1
        if run >= IMPULSE_N:
            if (c[i + run - 1] - o[i]) >= IMP_ATR * a[i] and a[i] > 0:
                org = i - 1
                lo = max(0, org - SWING_LOOKBACK)
                key = float(np.max(h[lo:org + 1])) if org > lo else float(h[org])
                zones.append({"dir": "long", "ts": h1.index[org], "proximal": float(h[org]),
                              "distal": float(l[org]), "formed_i": i + run - 1, "atr": float(a[i]),
                              "key": key})
            i += run; continue
        run = 0
        while i + run < n and (not green[i + run]):
            run += 1
        if run >= IMPULSE_N:
            if (o[i] - c[i + run - 1]) >= IMP_ATR * a[i] and a[i] > 0:
                org = i - 1
                lo = max(0, org - SWING_LOOKBACK)
                key = float(np.min(l[lo:org + 1])) if org > lo else float(l[org])
                zones.append({"dir": "short", "ts": h1.index[org], "proximal": float(l[org]),
                              "distal": float(h[org]), "formed_i": i + run - 1, "atr": float(a[i]),
                              "key": key})
            i += run; continue
        i += 1
    return zones


def _engulf(o, c, i, long):
    body = abs(c[i] - o[i]); pbody = abs(c[i - 1] - o[i - 1])
    if long:
        return c[i] > o[i] and c[i] >= max(o[i - 1], c[i - 1]) and body > pbody
    return c[i] < o[i] and c[i] <= min(o[i - 1], c[i - 1]) and body > pbody


def _signals_for_symbol(sym, start, end):
    warm = pd.Timedelta(days=30)
    h1 = tsc.fetch_klines(sym, "1h", int((start - warm).timestamp() * 1000), int(end.timestamp() * 1000))
    m15 = tsc.fetch_klines(sym, "15m", int((start - warm).timestamp() * 1000), int(end.timestamp() * 1000))
    if h1 is None or m15 is None or h1.empty or m15.empty:
        return []
    zones = _detect_zones(h1)
    o15, c15 = m15["open"].values, m15["close"].values
    h15, l15 = m15["high"].values, m15["low"].values
    e15 = _ema(m15["close"], EMA_LEN).values
    ts15 = m15.index
    h1c = h1["close"].values
    sigs = []
    for z in zones:
        formed_ts = h1.index[z["formed_i"]]
        max_ts = formed_ts + pd.Timedelta(hours=ZONE_MAXAGE_BARS)
        long = z["dir"] == "long"
        prox, dist = z["proximal"], z["distal"]
        kill_ts = None
        for k in np.where(h1.index > formed_ts)[0]:
            if h1.index[k] > max_ts:
                kill_ts = max_ts; break
            if (long and h1c[k] < dist) or (not long and h1c[k] > dist):
                kill_ts = h1.index[k]; break
        deadline = kill_ts if kill_ts is not None else max_ts
        lo = int(ts15.searchsorted(formed_ts))
        hi = int(ts15.searchsorted(deadline))
        for j in range(max(lo, 1), hi):
            inzone = (l15[j] <= prox) if long else (h15[j] >= prox)
            if not inzone:
                continue
            cross = (c15[j] > e15[j]) if long else (c15[j] < e15[j])
            if cross and _engulf(o15, c15, j, long):
                entry = float(c15[j])
                risk = abs(entry - dist) + SL_BUF_ATR * z["atr"]
                if MIN_RISK_PCT > 0 and risk < MIN_RISK_PCT * entry:
                    continue                                   # fee-floor: stop too tight
                sl = entry - risk if long else entry + risk
                rr_key = (z["key"] - entry) / risk if long else (entry - z["key"]) / risk
                rr = min(max(rr_key, RR_MIN), RR_MAX) if rr_key > 0 else RR_DEF
                tp = entry + rr * risk if long else entry - rr * risk
                cts = ts15[j] + pd.Timedelta(minutes=15)       # candle close ts
                if start <= cts < end:
                    sigs.append({"symbol": sym, "direction": z["dir"], "ts": cts,
                                 "entry": entry, "sl": sl, "tp": tp})
                break
    sigs.sort(key=lambda s: s["ts"])
    return sigs


# ---------------------------------------------------------------- portfolio walk
def build_events(sym, w_start, w_end):
    """Each taken signal -> a portfolio event (confirm-fill + natural 1m outcome). NO df1m stashed."""
    sigs = _signals_for_symbol(sym, w_start, w_end)
    if not sigs:
        return []
    df1m = _get_1m(sym, w_start, w_end)
    if df1m is None or df1m.empty:
        return []
    out = []
    for s in sigs:
        cf = tsc.confirm_fill(df1m, s["ts"], s["direction"], s["entry"], s["sl"], buf=CONFIRM_BUF,
                              expiry_minutes=EXPIRY_MIN)
        if cf is None:
            continue
        fill_ts, entry_eff, risk_eff = cf
        res = tsc.resolve_market(df1m, fill_ts, s["direction"], entry_eff, s["sl"], s["tp"],
                                 risk_eff, max_hold_minutes=MAX_HOLD_MIN)
        if res.get("real_entry_time") is None:
            continue
        out.append({"symbol": sym, "direction": s["direction"], "signal_ts": s["ts"],
                    "sl": s["sl"], "tp": s["tp"], "entry_eff": entry_eff, "risk_eff": risk_eff,
                    "fill": pd.Timestamp(res["real_entry_time"]).tz_convert("UTC"),
                    "nat_exit": pd.Timestamp(res["exit_time"]).tz_convert("UTC") if res.get("exit_time") else None,
                    "nat_exit_price": res.get("exit_price"), "nat_r": res.get("pnl_r"),
                    "nat_status": res.get("status")})
    return out


def _reverse_r(p, t, w_start, w_end):
    """R if position p is force-closed (reverse) at time t — mark-to-market re-resolve on 1m."""
    hold = int((t - p["fill"]).total_seconds() // 60)
    if hold <= 0:
        return 0.0, t, None
    df1m = _get_1m(p["symbol"], w_start, w_end)
    res = tsc.resolve_market(df1m, p["fill"], p["direction"], p["entry_eff"], p["sl"], p["tp"],
                             p["risk_eff"], max_hold_minutes=hold)
    r = res.get("pnl_r")
    xt = pd.Timestamp(res["exit_time"]).tz_convert("UTC") if res.get("exit_time") else t
    return (float(r) if r is not None else 0.0), xt, res.get("exit_price")


def walk(events, w_start, w_end):
    """One-position-per-symbol + reverse portfolio walk (no cross-symbol cap). -> realized records."""
    evs = sorted(events, key=lambda e: e["fill"])
    open_pos, realized = {}, []

    def rec(p, exit_t, r, status, ep):
        realized.append({"symbol": p["symbol"], "direction": p["direction"], "signal_ts": p["signal_ts"],
                         "entry": p["entry_eff"], "sl": p["sl"], "tp": p["tp"], "fill": p["fill"],
                         "exit": exit_t, "exit_price": ep, "r": r, "status": status})

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
                continue                                       # same -> ignore
            r, xt, ep = _reverse_r(p, t, w_start, w_end)        # opposite -> reverse-close
            rec(p, xt, r, "closed_tp" if r >= 0 else "closed_sl", ep)
            del open_pos[sym]
        open_pos[sym] = e
    for sym, p in open_pos.items():
        if p["nat_exit"] is not None:
            rec(p, p["nat_exit"], p["nat_r"], p["nat_status"], p["nat_exit_price"])
        else:
            rec(p, None, None, "active", None)
    return realized


def _pf(x):
    return float(x) if x is not None else None


def to_rows(realized):
    rows = []
    for r in realized:
        outcome = {"status": r["status"],
                   "real_entry_time": r["fill"].to_pydatetime() if r["fill"] is not None else None,
                   "exit_time": r["exit"].to_pydatetime() if r["exit"] is not None else None,
                   "exit_price": _pf(r["exit_price"]), "pnl_r": _pf(r["r"])}
        row = tsc.build_row(r["symbol"], r["signal_ts"], "LONG" if r["direction"] == "long" else "SHORT",
                            _pf(r["entry"]), _pf(r["sl"]), _pf(r["tp"]), outcome, strategy="supdem")
        row["version"] = VERSION
        rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--symbols", nargs="*", default=None)
    args = ap.parse_args()
    global SYMBOLS
    if args.symbols:
        SYMBOLS = [s.upper() for s in args.symbols]
    w_start = pd.Timestamp(args.start, tz="UTC") if args.start else DEFAULT_START
    w_end = pd.Timestamp(args.end, tz="UTC") if args.end else pd.Timestamp.now(tz="UTC")
    print(f"=== [sdv] supply/demand portfolio backfill | [{w_start.date()}..{w_end.date()}) | "
          f"{len(SYMBOLS)} symbols | min_risk={MIN_RISK_PCT:.4f} ===", flush=True)
    events = []
    for sym in SYMBOLS:
        try:
            ev = build_events(sym, w_start, w_end)
            events += ev
            if ev:
                print(f"  {sym:<12} {len(ev):>4} taken", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {sym}: {type(e).__name__}: {e}", flush=True)
    realized = walk(events, w_start, w_end)
    rows = to_rows(realized)
    closed = [r for r in realized if r["r"] is not None]
    tot = sum(r["r"] for r in closed)
    wins = sum(1 for r in closed if r["r"] > 0)
    wr = round(100 * wins / len(closed)) if closed else 0
    gp = sum(r["r"] for r in closed if r["r"] > 0); gl = -sum(r["r"] for r in closed if r["r"] < 0)
    pf = gp / gl if gl > 0 else float("inf")
    print(f"\n  -> {len(rows)} rows · closed={len(closed)} · R={tot:+.1f} · WR={wr}% · PF={pf:.2f} "
          f"· active={len(realized) - len(closed)}", flush=True)
    # per-year recap
    for yr in ["2024", "2025", "2026"]:
        cs = [r for r in closed if str(pd.Timestamp(r["exit"]).year) == yr]
        if cs:
            print(f"     {yr}: R={sum(r['r'] for r in cs):+.1f}  n={len(cs)}  "
                  f"WR={round(100*sum(1 for r in cs if r['r']>0)/len(cs))}%", flush=True)
    if args.apply:
        conn = tsc.backtest_conn()
        cur = conn.cursor()
        cur.execute(f"DELETE FROM {tsc.TABLE} WHERE version = %s", (VERSION,))
        deleted = cur.rowcount
        conn.commit(); cur.close()
        n = tsc.upsert_rows(conn, rows)
        conn.close()
        print(f"\n  [DB] deleted {deleted} old rows, upserted {n} rows for version='{VERSION}'", flush=True)
    else:
        print(f"\n  [dry-run] {len(rows)} rows would upsert (no DB write).", flush=True)


if __name__ == "__main__":
    main()
