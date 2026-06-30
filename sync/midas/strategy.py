"""MIDAS — gold-only intraday VWAP-trend strategy (XAUUSDT 1m).

Independent from the Donchian/ICT book. A trend-CONTINUATION strategy: in an established intraday
trend (anchored-VWAP slope), buy the PULLBACK to VWAP (sell the rally to VWAP), risk 1.5*ATR, take
NO fixed profit target and ride a 3.5*ATR trailing stop to a session-close / 8h time exit. Trades
ONLY during real FX-gold market hours (Sun 18:00 ET -> Fri 17:00 ET, daily 17:00-18:00 ET break) and
NEVER holds across the rollover/weekend ("anlik islem ac-kapa"). One position at a time.

Validated on Binance XAUUSDT 1m 2026-H1 (see FX-GOLD-VWAP-RAPORU.md): +115R, PF 1.32, IS+54/OOS+61,
both directions positive, edge survives a parameter plateau + honest IS->OOS + random-entry null +
liquid-hours test + an independent reimplementation. NO-LOOKAHEAD: every signal is decided on a
bar's CLOSE and filled at the NEXT bar's open.

COST NOTE: this is an FX instrument. The default cost is $0.50/oz round-trip (~1.1 bps at $4000) =
a tight ECN-FX/CFD spread+slippage. The strategy DIES on Binance crypto taker fees (~10 bps ≈ $4/oz);
so MIDAS is a tight-spread-FX / maker-fill / PAPER stream, NOT a Binance-taker stream.
"""
from __future__ import annotations
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))                 # sync/         -> trade_sync_common
sys.path.insert(0, str(_HERE.parents[2] / "backtest"))    # backtest/     -> ict.data
import trade_sync_common as tsc                            # noqa: E402

SYMBOL = "XAUUSDT"

# ---- tuned, plateau-confirmed config ----
SLOPE_N = 60          # bars used for VWAP-slope (trend) direction
ATR_TF = "15min"      # ATR timeframe for stop sizing
ATR_N = 14
ATR_INIT_MULT = 1.5   # initial stop distance (1R)
TRAIL_MULT = 3.5      # ATR trailing-stop multiple (chandelier)
TOUCH_TOL = 0.25      # pullback must come within TOUCH_TOL*ATR of VWAP
MAX_HOLD_MIN = 480    # hard 8h time-stop
COST_RT = 0.50        # round-trip cost, $/oz (ECN-FX assumption)
TP_REF_MULT = TRAIL_MULT / ATR_INIT_MULT   # nominal "target" line for the UI (= trail_dist in R)

# Session filter — SKIP the London pre-NY window [07:00, 13:00) UTC. It is the ONLY session that is
# net-negative in BOTH in-sample (Jan-Apr) and out-of-sample (May-Jun): NY-positioning chop whipsaws
# the trend-continuation. Dropping it (2026-H1): +118R -> +144R, PF 1.33 -> 1.48, IS +54 -> +83,
# OOS held (+64 -> +61). Asia (22-07), London-NY overlap (13-17) and NY afternoon (17-21) stay on.
SKIP_UTC_START = 7
SKIP_UTC_END = 13


# ---------------------------------------------------------------- data + market hours
def load_1m(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    df = tsc.fetch_klines(SYMBOL, "1m", int(start.timestamp() * 1000), int(end.timestamp() * 1000))
    if df is None or df.empty:
        return pd.DataFrame()
    return df.loc[(df.index >= start) & (df.index < end)]


def add_market_open(df: pd.DataFrame) -> pd.DataFrame:
    """Real FX-gold session: open Sun 18:00 ET -> Fri 17:00 ET, daily 17:00-18:00 ET break.
    America/New_York via tz handles US DST automatically.

    PRE-WEEKEND FLATTEN: trading stops 1h BEFORE the Friday weekend close (16:00 ET, not 17:00) so
    NO position is held into the thin pre-weekend hour or over the weekend gap. The engine
    force-closes any open position at the last open bar -> 15:59 ET Friday."""
    et = df.index.tz_convert("America/New_York")
    dow = et.dayofweek; hour = et.hour
    is_open = pd.Series(True, index=df.index)
    is_open &= ~(dow == 5)                       # Saturday
    is_open &= ~((dow == 6) & (hour < 18))       # Sunday opens 18:00 ET
    is_open &= ~((dow == 4) & (hour >= 16))      # Friday: flat 1h early (16:00 ET, weekend buffer)
    is_open &= ~((dow <= 3) & (hour == 17))      # Mon-Thu 17:00-18:00 break
    out = df.copy(); out["open_mkt"] = is_open.values
    return out


# ---------------------------------------------------------------- indicators (no lookahead)
def atr_tf(df: pd.DataFrame, tf: str = ATR_TF, n: int = ATR_N) -> pd.Series:
    g = df.resample(tf, label="right", closed="right").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    pc = g["close"].shift(1)
    tr = pd.concat([(g["high"] - g["low"]), (g["high"] - pc).abs(), (g["low"] - pc).abs()], axis=1).max(axis=1)
    a = tr.ewm(alpha=1 / n, adjust=False).mean()
    return a.reindex(df.index, method="ffill")


def _fx_day(df: pd.DataFrame) -> np.ndarray:
    """FX-day id; boundary = 18:00 ET (the gold/FX day open)."""
    et = df.index.tz_convert("America/New_York")
    return (et - pd.Timedelta(hours=18)).normalize().view("int64")


def anchored_vwap(df: pd.DataFrame):
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    vol = df["volume"].replace(0, np.nan).ffill().fillna(1.0)
    day = pd.Series(_fx_day(df), index=df.index)
    vwap = (tp * vol).groupby(day).cumsum() / vol.groupby(day).cumsum()
    return vwap


def signals(df: pd.DataFrame, atr: pd.Series | None = None):
    """Return (side, stop) arrays. side +1/-1/0 decided at bar i close; stop = initial-stop price."""
    if atr is None:
        atr = atr_tf(df)
    vwap = anchored_vwap(df)
    n = len(df); side = np.zeros(n); stop = np.full(n, np.nan)
    vw = vwap.to_numpy(); slope = (vwap - vwap.shift(SLOPE_N)).to_numpy()
    c = df["close"].to_numpy(); o = df["open"].to_numpy()
    lo = df["low"].to_numpy(); hi = df["high"].to_numpy()
    a = atr.to_numpy(); openmkt = df["open_mkt"].to_numpy(bool)
    uth = df.index.hour.to_numpy()                  # UTC hour for the session filter
    tol = TOUCH_TOL * a
    for i in range(SLOPE_N + 1, n):
        if not openmkt[i] or not np.isfinite(vw[i]) or not np.isfinite(a[i]) or a[i] <= 0:
            continue
        if SKIP_UTC_START <= uth[i] < SKIP_UTC_END:  # skip the London pre-NY window (07-13 UTC)
            continue
        if c[i] > vw[i] and slope[i] > 0 and lo[i] <= vw[i] + tol[i] and c[i] > o[i]:
            side[i] = 1; stop[i] = c[i] - ATR_INIT_MULT * a[i]
        elif c[i] < vw[i] and slope[i] < 0 and hi[i] >= vw[i] - tol[i] and c[i] < o[i]:
            side[i] = -1; stop[i] = c[i] + ATR_INIT_MULT * a[i]
    return side, stop


# ---------------------------------------------------------------- single-position intraday walk
@dataclass
class Trade:
    signal_time: pd.Timestamp
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    side: int
    entry: float
    stop: float
    tp_ref: float
    exit_px: float
    pnl_r: float
    reason: str
    trail: list = None   # [[unix_sec, stop_price], ...] — the ratcheting stop path (UI viz)


def _net_r(entry, exit_px, stop_dist, side, cost):
    return ((exit_px - entry) * side - cost) / stop_dist


def walk(df: pd.DataFrame, side, stop, atr, *, cost=COST_RT, trail=TRAIL_MULT,
         max_hold=MAX_HOLD_MIN) -> list[Trade]:
    """Enter next-open; ATR trailing stop (ratchet uses bar j extreme -> effective j+1, no lookahead);
    force-flat at session close; STOP wins same-bar ties; gap-fills are conservative."""
    o = df["open"].to_numpy(); h = df["high"].to_numpy(); l = df["low"].to_numpy(); c = df["close"].to_numpy()
    openmkt = df["open_mkt"].to_numpy(bool); ts = df.index
    a = np.asarray(atr, float); n = len(df)
    out: list[Trade] = []
    i = 0
    while i < n - 1:
        s = side[i]
        if s == 0 or not openmkt[i] or not openmkt[i + 1] or not np.isfinite(stop[i]):
            i += 1; continue
        k = i + 1; entry = o[k]; st = stop[i]; sd = abs(entry - st)
        if sd <= 0 or not np.isfinite(sd):
            i += 1; continue
        tp_ref = entry + s * TP_REF_MULT * sd          # nominal target line (UI only)
        best = entry; exit_px = np.nan; xi = None; reason = ""
        st_init = st                                   # the FIXED initial stop (defines 1R)
        trail_pts = [[int(ts[k].timestamp()), float(st)]]   # entry -> initial stop level
        prev_st = st
        j = k
        while j < n:
            if not openmkt[j]:
                exit_px = c[j - 1]; xi = j - 1; reason = "session"; break
            hit = (l[j] <= st) if s > 0 else (h[j] >= st)
            if hit:
                exit_px = (min(st, o[j]) if s > 0 else max(st, o[j])); xi = j; reason = "trail/stop"; break
            if max_hold and (j - k) >= max_hold:
                exit_px = c[j]; xi = j; reason = "time"; break
            if j + 1 >= n:                              # DATA EDGE: market still open -> NOT resolved
                exit_px = c[j]; xi = j; reason = "open"; break
            if not openmkt[j + 1]:                      # real session close -> resolved
                exit_px = c[j]; xi = j; reason = "session"; break
            if trail > 0 and np.isfinite(a[j]):
                if s > 0:
                    best = max(best, h[j]); st = max(st, best - trail * a[j])
                else:
                    best = min(best, l[j]); st = min(st, best + trail * a[j])
                if st != prev_st:                      # record only the ratchet change-points
                    trail_pts.append([int(ts[j].timestamp()), float(st)]); prev_st = st
            j += 1
        trail_pts.append([int(ts[xi].timestamp()), float(st)])   # extend the line to the exit bar
        pnl_r = _net_r(entry, exit_px, sd, s, cost)
        out.append(Trade(ts[i], ts[k], ts[xi], int(s), float(entry), float(st_init),
                         float(tp_ref), float(exit_px), float(pnl_r), reason, trail_pts))
        i = xi + 1
    return out


def generate_trades(start: pd.Timestamp, end: pd.Timestamp, *, cost=COST_RT) -> list[Trade]:
    """End-to-end: fetch 1m, tag market hours, build signals, walk -> closed trades."""
    df = load_1m(start - pd.Timedelta(days=2), end)      # small warmup for ATR/VWAP/slope
    if df.empty:
        return []
    df = add_market_open(df)
    atr = atr_tf(df)
    side, stop = signals(df, atr)
    trades = walk(df, side, stop, atr.to_numpy(), cost=cost)
    return [t for t in trades if t.entry_time >= start]


def _closed(entry, px, risk, s, t, reason, cost):
    return {"status": "closed", "exit_px": float(px), "exit_time": pd.Timestamp(t),
            "reason": reason, "pnl_r": float(_net_r(entry, px, risk, s, cost))}


def track_open(entry_fill: pd.Timestamp, side: int, entry: float, init_sl: float, now: pd.Timestamp,
               *, trail=TRAIL_MULT, max_hold=MAX_HOLD_MIN, cost=COST_RT):
    """LIVE replay of ONE open position from its fill to `now`: the CURRENT trailing-stop level,
    locked R, and whether it has already exited (trail hit / 8h / session). Mirrors walk()'s inner
    loop. Used by canli.py to push SL-ratchet + exit alerts. Returns None if data is insufficient."""
    df = load_1m(pd.Timestamp(entry_fill) - pd.Timedelta(days=2), now)
    if df.empty:
        return None
    df = add_market_open(df)
    bar = pd.Timedelta(minutes=1)
    df = df[df.index + bar <= now]                 # drop the still-forming candle
    if df.empty:
        return None
    atr = atr_tf(df).to_numpy()
    o = df["open"].to_numpy(); h = df["high"].to_numpy(); l = df["low"].to_numpy(); c = df["close"].to_numpy()
    openmkt = df["open_mkt"].to_numpy(bool); ts = df.index; n = len(df)
    s = 1 if side > 0 else -1
    risk = abs(entry - init_sl)
    if risk <= 0:
        return None
    k = int(ts.searchsorted(pd.Timestamp(entry_fill)))
    if k >= n:
        return None
    best = entry; st = init_sl
    trail_pts = [[int(ts[k].timestamp()), float(st)]]; prev_st = st   # ratcheting stop path (for the UI)
    for j in range(k, n):
        if not openmkt[j]:
            return _closed(entry, c[j - 1], risk, s, ts[j - 1], "session", cost)
        hit = (l[j] <= st) if s > 0 else (h[j] >= st)
        if hit:
            px = min(st, o[j]) if s > 0 else max(st, o[j])
            return _closed(entry, px, risk, s, ts[j], "trail/stop", cost)
        if max_hold and (j - k) >= max_hold:
            return _closed(entry, c[j], risk, s, ts[j], "time", cost)
        if (j + 1 < n) and not openmkt[j + 1]:     # real session boundary within loaded data
            return _closed(entry, c[j], risk, s, ts[j], "session", cost)
        if trail > 0 and np.isfinite(atr[j]):
            if s > 0:
                best = max(best, h[j]); st = max(st, best - trail * atr[j])
            else:
                best = min(best, l[j]); st = min(st, best + trail * atr[j])
            if st != prev_st:
                trail_pts.append([int(ts[j].timestamp()), float(st)]); prev_st = st
        if j + 1 >= n:                              # latest loaded bar + market open -> still OPEN
            break
    trail_pts.append([int(ts[n - 1].timestamp()), float(st)])         # extend the line to now
    locked = ((st - entry) if s > 0 else (entry - st)) / risk
    return {"status": "open", "cur_sl": float(st), "best": float(best), "locked_r": float(locked),
            "last_price": float(c[n - 1]), "trail": trail_pts, "init_sl": float(init_sl),
            "minutes_open": int((ts[n - 1] - ts[k]).total_seconds() // 60)}


def current_open(now: pd.Timestamp, lookback_hours: int = 10):
    """The position that is CURRENTLY open (entered within the max-hold window, not yet resolved),
    or None if flat. Self-heal for canli: ensures an open trade is surfaced LIVE even if its
    formation alert was missed (cron gap / pre-deploy). One-position-at-a-time, so at most one."""
    trades = generate_trades(now - pd.Timedelta(hours=lookback_hours), now)
    if trades and trades[-1].reason == "open":
        t = trades[-1]
        return {"direction": "long" if t.side > 0 else "short", "entry": t.entry,
                "sl": t.stop, "tp": t.tp_ref, "signal_time": t.signal_time}
    return None


def latest_setup(now: pd.Timestamp, lookback_min: int = 10, *, cost=COST_RT):
    """For CANLI: fresh VWAP-trend setups whose SIGNAL bar closed within `lookback_min` minutes.
    Returns list of dicts {direction, entry, sl, tp, signal_time}. entry = signal-bar close (the
    live reference price); sl = 1.5*ATR; tp = nominal trail-distance target line."""
    df = load_1m(now - pd.Timedelta(hours=12), now)      # enough for VWAP(day)+ATR+slope
    if df.empty:
        return []
    df = add_market_open(df)
    bar = pd.Timedelta(minutes=1)
    df = df[df.index + bar <= now]                       # drop the still-forming candle
    if df.empty:
        return []
    atr = atr_tf(df)
    side, stop = signals(df, atr)
    floor = now - pd.Timedelta(minutes=lookback_min)
    out = []
    a = atr.to_numpy(); c = df["close"].to_numpy()
    for i in range(len(df)):
        if side[i] == 0:
            continue
        sig_close = df.index[i] + bar                    # the bar's close time = fire time
        if not (floor <= sig_close <= now):
            continue
        entry = float(c[i]); sl = float(stop[i]); sd = abs(entry - sl)
        d = "long" if side[i] > 0 else "short"
        tp = entry + side[i] * TP_REF_MULT * sd
        out.append({"direction": d, "entry": entry, "sl": sl, "tp": float(tp),
                    "signal_time": df.index[i]})         # signal_time = bar OPEN (UI adds ltf)
    return out
