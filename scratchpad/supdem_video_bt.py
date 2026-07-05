"""Backtest the YouTube "supply & demand" gold strategy (video AY7fWmE1CBk) under our LIVE
portfolio rules, on BTC/ETH/XAU/XAG for 2026.

VIDEO STRATEGY (mechanized):
  * Zone = ORIGIN of an aggressive impulse: >=IMPULSE_N consecutive same-color 1h candles whose
    net displacement >= IMP_ATR * ATR(14). Demand = base of an up-impulse, Supply = base of a
    down-impulse. Zone box = [low,high] of the last candle BEFORE the run (its origin).
  * Wait for price to RETEST the zone (15m candle trades back into the box). Zone is invalidated
    if a 1h close breaks beyond its distal edge before a retest ("price broke through -> cancel").
  * Entry confluence on 15m: (a) 8-EMA crossover to the trade side AND (b) a strong engulfing
    candle in the trade direction.
  * SL beyond the zone distal (- buffer). TP at the next key level to the left = prior swing
    extreme (RR clipped to [RR_MIN, RR_MAX]; default RR_DEF when no clean level).

LIVE RULES applied (new-strategy-demo-protocol):
  * +0.5R confirm entry (ENTRY_CONFIRM_BUF=0.5, confirm-fill on 1m).
  * one position per symbol; an OPPOSITE confirmed signal REVERSES (close+flip); SAME ignored.
  * MAX_CONCURRENT = len(symbols).  Resolution intrabar-accurate on 1m, net of fees.
"""
import os, sys, argparse
from pathlib import Path
os.environ.setdefault("ENTRY_AT_CONFIRM", "1")
os.environ.setdefault("ENTRY_CONFIRM_BUF", "0.5")
sys.path.insert(0, "sync"); sys.path.insert(0, "sync/donchian"); sys.path.insert(0, "sync/live_exec")
import numpy as np, pandas as pd
import trade_sync_common as tsc

SYMBOLS = ["BTCUSDT", "ETHUSDT", "XAUUSDT", "XAGUSDT"]
CONFIRM_BUF = 0.5
EXPIRY_MIN = 180            # confirm-fill window (minutes) after the 15m entry close
MAX_HOLD_MIN = 14 * 24 * 60  # 14-day time-stop on each position (swing strategy)

# --- detector knobs (defaults; sweepable) ---
IMPULSE_N = 3              # consecutive same-color candles = "aggressive"
IMP_ATR = 1.0             # min net displacement of the impulse, in ATR(14)
EMA_LEN = 8
RR_MIN, RR_MAX, RR_DEF = 1.5, 6.0, 2.5
ZONE_MAXAGE_BARS = 24 * 21  # zone valid up to ~21 days (1h bars) waiting for a retest
SL_BUF_ATR = 0.1          # SL buffer beyond zone distal, in ATR
SWING_LOOKBACK = 60       # 1h bars back to find the "next key level" swing
MIN_RISK_PCT = 0.0        # skip trades whose stop distance < this fraction of price (fee-floor).
                          # fee~=0.001*price/risk in R; 0.0030 caps fee drag at ~0.33R. 0=off.


def atr(df, n=14):
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def detect_zones(h1):
    """Find supply/demand zones from impulses on 1h. Returns list of dicts:
    {dir, idx_origin (iloc), ts_origin, proximal, distal, formed_ts (impulse end), key_level}."""
    o, h, l, c = h1["open"].values, h1["high"].values, h1["low"].values, h1["close"].values
    a = atr(h1).values
    n = len(h1)
    green = c > o
    zones = []
    i = 1
    while i < n - IMPULSE_N:
        if np.isnan(a[i]):
            i += 1; continue
        # up-impulse: IMPULSE_N consecutive greens starting at i
        run = 0
        while i + run < n and green[i + run]:
            run += 1
        if run >= IMPULSE_N:
            disp = c[i + run - 1] - o[i]
            if disp >= IMP_ATR * a[i] and a[i] > 0:
                org = i - 1                       # origin candle = last one before the run
                # next key level UP = max high in the lookback window before the impulse
                lo = max(0, org - SWING_LOOKBACK)
                key = float(np.max(h[lo:org + 1])) if org > lo else float(h[org])
                zones.append({"dir": "long", "iorg": org, "ts": h1.index[org],
                              "proximal": float(h[org]), "distal": float(l[org]),
                              "formed_i": i + run - 1, "atr": float(a[i]), "key": key})
            i += run; continue
        # down-impulse
        run = 0
        while i + run < n and (not green[i + run]):
            run += 1
        if run >= IMPULSE_N:
            disp = o[i] - c[i + run - 1]
            if disp >= IMP_ATR * a[i] and a[i] > 0:
                org = i - 1
                lo = max(0, org - SWING_LOOKBACK)
                key = float(np.min(l[lo:org + 1])) if org > lo else float(l[org])
                zones.append({"dir": "short", "iorg": org, "ts": h1.index[org],
                              "proximal": float(l[org]), "distal": float(h[org]),
                              "formed_i": i + run - 1, "atr": float(a[i]), "key": key})
            i += run; continue
        i += 1
    return zones


def engulf(o, c, i, long):
    """Strong directional candle: bullish/bearish engulfing of prior body."""
    body = abs(c[i] - o[i]); pbody = abs(c[i - 1] - o[i - 1])
    if long:
        return c[i] > o[i] and c[i] >= max(o[i - 1], c[i - 1]) and body > pbody
    return c[i] < o[i] and c[i] <= min(o[i - 1], c[i - 1]) and body > pbody


def signals_for_symbol(sym, start, end):
    """Generate raw signals (entry/sl/tp + 15m close ts) honoring zone retest + 15m confluence."""
    warm = pd.Timedelta(days=30)
    h1 = tsc.fetch_klines(sym, "1h", int((start - warm).timestamp() * 1000), int(end.timestamp() * 1000))
    m15 = tsc.fetch_klines(sym, "15m", int((start - warm).timestamp() * 1000), int(end.timestamp() * 1000))
    if h1 is None or m15 is None or h1.empty or m15.empty:
        return []
    zones = detect_zones(h1)
    o15, c15 = m15["open"].values, m15["close"].values
    h15, l15 = m15["high"].values, m15["low"].values
    e15 = ema(m15["close"], EMA_LEN).values
    ts15 = m15.index
    h1c = h1["close"].values
    sigs = []
    for z in zones:
        formed_ts = h1.index[z["formed_i"]]
        # zone invalidation: a 1h close beyond distal AFTER formation, before retest
        max_ts = formed_ts + pd.Timedelta(hours=ZONE_MAXAGE_BARS)
        long = z["dir"] == "long"
        prox, dist = z["proximal"], z["distal"]
        # 1h bars after formation -> first break of distal kills the zone
        kill_ts = None
        post = h1.index > formed_ts
        idxs = np.where(post)[0]
        for k in idxs:
            if h1.index[k] > max_ts:
                kill_ts = max_ts; break
            if (long and h1c[k] < dist) or (not long and h1c[k] > dist):
                kill_ts = h1.index[k]; break
        deadline = kill_ts if kill_ts is not None else max_ts
        # scan 15m after formation, within [formed, deadline], for retest + confluence
        lo = int(ts15.searchsorted(formed_ts))
        hi = int(ts15.searchsorted(deadline))
        entered = False
        for j in range(max(lo, 1), hi):
            inzone = (l15[j] <= prox) if long else (h15[j] >= prox)
            if not inzone:
                continue
            # confluence: close on trade side of EMA8 + engulfing candle
            cross = (c15[j] > e15[j]) if long else (c15[j] < e15[j])
            if cross and engulf(o15, c15, j, long):
                entry = float(c15[j])
                risk = abs(entry - dist) + SL_BUF_ATR * z["atr"]
                if MIN_RISK_PCT > 0 and risk < MIN_RISK_PCT * entry:
                    continue                                   # fee-floor: stop too tight
                sl = entry - risk if long else entry + risk
                # TP at the key level, RR-clipped
                rr_key = (z["key"] - entry) / risk if long else (entry - z["key"]) / risk
                rr = min(max(rr_key, RR_MIN), RR_MAX) if rr_key > 0 else RR_DEF
                tp = entry + rr * risk if long else entry - rr * risk
                cts = ts15[j] + pd.Timedelta(minutes=15)   # candle close ts
                if start <= cts < end:
                    sigs.append({"symbol": sym, "direction": z["dir"], "ts": cts,
                                 "entry": entry, "sl": sl, "tp": tp, "risk": risk})
                entered = True
                break
        _ = entered
    sigs.sort(key=lambda s: s["ts"])
    return sigs


def build_events(sym, sigs, df1m, end):
    """Confirm-fill each signal (+0.5R) and resolve its NATURAL outcome on 1m."""
    evs = []
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
        evs.append({"symbol": sym, "direction": s["direction"], "ts": s["ts"],
                    "entry": s["entry"], "sl": s["sl"], "tp": s["tp"],
                    "entry_eff": entry_eff, "risk_eff": risk_eff,
                    "fill": pd.Timestamp(res["real_entry_time"]).tz_convert("UTC"),
                    "nat_exit": pd.Timestamp(res["exit_time"]).tz_convert("UTC") if res.get("exit_time") else None,
                    "nat_r": res.get("pnl_r"), "nat_status": res.get("status"),
                    "df1m": df1m})
    return evs


def truncated_r(e, t):
    """R if position e is force-closed (reverse) at time t — mark-to-market re-resolve."""
    hold = int((t - e["fill"]).total_seconds() // 60)
    if hold <= 0:
        return 0.0, t
    res = tsc.resolve_market(e["df1m"], e["fill"], e["direction"], e["entry_eff"], e["sl"], e["tp"],
                             e["risk_eff"], max_hold_minutes=hold)
    r = res.get("pnl_r")
    xt = pd.Timestamp(res["exit_time"]).tz_convert("UTC") if res.get("exit_time") else t
    return (float(r) if r is not None else 0.0), xt


def walk(events, max_concurrent):
    """One-position-per-symbol + reverse portfolio walk. Returns realized R list."""
    evs = sorted(events, key=lambda e: e["fill"])
    open_pos, realized = {}, []

    def close_before(t):
        for sym, p in list(open_pos.items()):
            if p["nat_exit"] is not None and p["nat_exit"] <= t:
                realized.append({"symbol": sym, "direction": p["direction"], "ts": p["ts"],
                                 "exit": p["nat_exit"], "r": p["nat_r"], "status": p["nat_status"]})
                del open_pos[sym]

    for e in evs:
        t = e["fill"]
        close_before(t)
        sym = e["symbol"]
        if sym in open_pos:
            p = open_pos[sym]
            if p["direction"] == e["direction"]:
                continue                                   # same -> ignore
            r, xt = truncated_r(p, t)                       # opposite -> reverse-close
            realized.append({"symbol": sym, "direction": p["direction"], "ts": p["ts"],
                             "exit": xt, "r": r, "status": "reverse"})
            del open_pos[sym]
        if len(open_pos) >= max_concurrent:
            continue
        open_pos[sym] = e
    for sym, p in open_pos.items():
        if p["nat_exit"] is not None:
            realized.append({"symbol": sym, "direction": p["direction"], "ts": p["ts"],
                             "exit": p["nat_exit"], "r": p["nat_r"], "status": p["nat_status"]})
        else:
            realized.append({"symbol": sym, "direction": p["direction"], "ts": p["ts"],
                             "exit": None, "r": None, "status": "active"})
    return realized


def run(start, end, label):
    print(f"\n===== {label}  ({start.date()}..{end.date()}) =====", flush=True)
    all_ev = []
    per_sym_sig = {}
    for sym in SYMBOLS:
        sigs = signals_for_symbol(sym, start, end)
        per_sym_sig[sym] = len(sigs)
        if not sigs:
            continue
        m1end = min(pd.Timestamp.now(tz="UTC"), end + pd.Timedelta(days=15))
        df1m = tsc.fetch_klines(sym, "1m", int((start - pd.Timedelta(days=2)).timestamp() * 1000),
                                int(m1end.timestamp() * 1000))
        if df1m is None or df1m.empty:
            print(f"  ! {sym}: no 1m"); continue
        all_ev += build_events(sym, sigs, df1m, end)
    realized = walk(all_ev, max_concurrent=len(SYMBOLS))
    closed = [r for r in realized if r["r"] is not None]
    tot = sum(r["r"] for r in closed)
    wins = sum(1 for r in closed if r["r"] > 0)
    wr = 100 * wins / len(closed) if closed else 0
    gp = sum(r["r"] for r in closed if r["r"] > 0); gl = -sum(r["r"] for r in closed if r["r"] < 0)
    pf = gp / gl if gl > 0 else float("inf")
    avg = tot / len(closed) if closed else 0
    print(f"  signals/sym: " + "  ".join(f"{s}={per_sym_sig[s]}" for s in SYMBOLS))
    print(f"  TRADES={len(closed)}  R={tot:+.1f}  WR={wr:.1f}%  avgR={avg:+.2f}  PF={pf:.2f}  "
          f"active={len(realized)-len(closed)}", flush=True)
    # per symbol
    for sym in SYMBOLS:
        cs = [r for r in closed if r["symbol"] == sym]
        if cs:
            tr = sum(r["r"] for r in cs); w = sum(1 for r in cs if r["r"] > 0)
            print(f"    {sym:9} n={len(cs):3} R={tr:+6.1f} WR={100*w/len(cs):4.0f}%")
    # per month
    bym = {}
    for r in closed:
        m = pd.Timestamp(r["exit"]).strftime("%Y-%m")
        bym.setdefault(m, []).append(r["r"])
    print("    months: " + "  ".join(f"{m}:{sum(v):+.1f}" for m, v in sorted(bym.items())))
    return tot, wr, len(closed)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--oos", action="store_true", help="also run 2025 OOS")
    args = ap.parse_args()
    run(pd.Timestamp("2026-01-01", tz="UTC"), pd.Timestamp("2026-06-22", tz="UTC"), "2026 IN-SAMPLE")
    if args.oos:
        run(pd.Timestamp("2025-01-01", tz="UTC"), pd.Timestamp("2026-01-01", tz="UTC"), "2025 OOS")
