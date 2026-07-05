"""Audited single-position intraday backtest engine for XAUUSDT 1m.

Correctness priorities (lessons from this repo's history of measurement bugs):
  * NO lookahead: a signal is decided on bar i's CLOSE; the fill is bar i+1's OPEN.
  * Conservative intrabar fills: if a bar's range hits BOTH stop and target, STOP wins.
    Stops gap-fill at the worse of {stop, bar-open}; targets gap-fill at the better.
  * Intraday only ("anlik islem ac kapa"): never hold across the daily rollover break or the
    weekend. A position is force-closed at the close of the last open bar of its session run.
  * Realistic cost: one round-trip cost in PRICE units ($/oz) deducted per trade (spread+slippage
    +commission). Reported in R (=stop distance) and in net %, plus a cost sweep.

Strategy contract: a function(df, **params) -> (side, stop, target) numpy arrays aligned to df,
where decision is valid as of df.index[i] close. side: +1 long / -1 short / 0 none.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass
class Cfg:
    cost_rt: float = 0.50       # round-trip cost in $/oz (spread+slippage+commission)
    max_hold_min: int = 240     # hard time-stop in minutes (0 = none, only session-close exits)
    risk_pct: float = 0.01      # fixed-fractional risk per trade for the % equity curve
    trail_mult: float = 0.0     # ATR-trailing-stop multiple (0 = off); requires `atr` arg to backtest


def backtest(df: pd.DataFrame, side, stop, target, cfg: Cfg, atr=None) -> pd.DataFrame:
    """Walk bars; one position at a time; enter next-open, manage intrabar, force-flat each session.
    Optional ATR trailing stop (cfg.trail_mult>0): the stop ratchets toward price; the trail level
    at bar j is derived from data through j-1 (no intrabar lookahead)."""
    o = df["open"].to_numpy(float); h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float);  c = df["close"].to_numpy(float)
    openmkt = df["open_mkt"].to_numpy(bool)
    ts = df.index
    side = np.asarray(side, float); stop = np.asarray(stop, float); target = np.asarray(target, float)
    atr = np.asarray(atr, float) if atr is not None else None
    n = len(df)
    trades = []
    i = 0
    while i < n - 1:
        s = side[i]
        if s == 0 or not openmkt[i] or not openmkt[i + 1] or not np.isfinite(stop[i]):
            i += 1; continue
        # ENTER at next bar open
        k = i + 1
        entry = o[k]
        sd = abs(entry - stop[i])
        if sd <= 0 or not np.isfinite(sd):
            i += 1; continue
        st = stop[i]; tg = target[i]
        best = entry  # best favorable price for trailing
        exit_px = np.nan; exit_idx = None; reason = ""
        j = k
        while j < n:
            # session boundary: if this bar isn't open, or it's the last open bar of the run -> exit at prev close
            if not openmkt[j]:
                exit_px = c[j - 1]; exit_idx = j - 1; reason = "session"; break
            hit_stop = (l[j] <= st) if s > 0 else (h[j] >= st)
            hit_tgt = np.isfinite(tg) and ((h[j] >= tg) if s > 0 else (l[j] <= tg))
            if hit_stop:  # stop wins ties (conservative)
                exit_px = min(st, o[j]) if s > 0 else max(st, o[j])
                exit_idx = j; reason = "stop"; break
            if hit_tgt:
                exit_px = max(tg, o[j]) if s > 0 else min(tg, o[j])
                exit_idx = j; reason = "target"; break
            if cfg.max_hold_min and (j - k) >= cfg.max_hold_min:
                exit_px = c[j]; exit_idx = j; reason = "time"; break
            if (j + 1 >= n) or (not openmkt[j + 1]):  # last open bar before break/weekend/EOD
                exit_px = c[j]; exit_idx = j; reason = "session"; break
            # ratchet trailing stop using THIS bar's extreme -> effective from next bar (no lookahead)
            if cfg.trail_mult > 0 and atr is not None and np.isfinite(atr[j]):
                if s > 0:
                    best = max(best, h[j]); st = max(st, best - cfg.trail_mult * atr[j])
                else:
                    best = min(best, l[j]); st = min(st, best + cfg.trail_mult * atr[j])
            j += 1
        gross = (exit_px - entry) * s
        net = gross - cfg.cost_rt
        r = net / sd
        trades.append({
            "entry_time": ts[k], "exit_time": ts[exit_idx], "side": int(s),
            "entry": entry, "stop": st, "target": tg, "exit": exit_px,
            "stop_dist": sd, "gross": gross, "net": net, "r": r, "reason": reason,
            "hold_min": int((ts[exit_idx] - ts[k]).total_seconds() // 60),
        })
        i = exit_idx + 1  # flat again; look for next signal after we exit (no overlap)
    return pd.DataFrame(trades)


def stats(tr: pd.DataFrame, cfg: Cfg, label: str = "") -> dict:
    if tr.empty:
        return {"label": label, "n": 0, "totR": 0.0, "wr": 0.0, "avgR": 0.0, "pf": 0.0,
                "maxddR": 0.0, "ret_pct": 0.0, "maxdd_pct": 0.0, "sharpe": 0.0}
    r = tr["r"].to_numpy()
    eq = r.cumsum(); peak = np.maximum.accumulate(eq); ddR = (eq - peak).min()
    wins = r[r > 0].sum(); losses = -r[r < 0].sum()
    pf = wins / losses if losses > 0 else float("inf")
    # fixed-fractional % equity (compounding, risk_pct of equity per trade)
    eqp = 1.0; curve = [1.0]
    for rr in r:
        eqp *= (1 + cfg.risk_pct * rr); curve.append(eqp)
    curve = np.array(curve); cpeak = np.maximum.accumulate(curve)
    maxdd_pct = ((curve - cpeak) / cpeak).min()
    # daily Sharpe on R
    daily = tr.set_index("exit_time")["r"].resample("D").sum()
    daily = daily[daily != 0] if (daily != 0).any() else daily
    sharpe = (daily.mean() / daily.std() * np.sqrt(252)) if daily.std() > 0 else 0.0
    return {"label": label, "n": int(len(tr)), "totR": round(float(r.sum()), 1),
            "wr": round(float((r > 0).mean()), 3), "avgR": round(float(r.mean()), 3),
            "pf": round(float(pf), 2), "maxddR": round(float(ddR), 1),
            "ret_pct": round(float((eqp - 1) * 100), 1), "maxdd_pct": round(float(maxdd_pct * 100), 1),
            "sharpe": round(float(sharpe), 2)}


def split_stats(tr: pd.DataFrame, cfg: Cfg, oos_start="2026-05-01") -> dict:
    """In-sample (Jan-Apr) vs out-of-sample (May-Jun) + monthly + long/short breakdown."""
    if tr.empty:
        return {"all": stats(tr, cfg, "ALL")}
    oos = pd.Timestamp(oos_start, tz="UTC")
    out = {
        "all": stats(tr, cfg, "ALL"),
        "is": stats(tr[tr.entry_time < oos], cfg, "IS(Jan-Apr)"),
        "oos": stats(tr[tr.entry_time >= oos], cfg, "OOS(May-Jun)"),
        "long": stats(tr[tr.side > 0], cfg, "LONG"),
        "short": stats(tr[tr.side < 0], cfg, "SHORT"),
    }
    mon = {}
    for m, g in tr.groupby(tr.entry_time.dt.to_period("M")):
        mon[str(m)] = stats(g, cfg)["totR"]
    out["monthly"] = mon
    return out


def cost_sweep(df, side, stop, target, base: Cfg, costs=(0.2, 0.5, 1.0, 2.0)) -> pd.DataFrame:
    rows = []
    for cst in costs:
        cfg = Cfg(cost_rt=cst, max_hold_min=base.max_hold_min, risk_pct=base.risk_pct)
        tr = backtest(df, side, stop, target, cfg)
        rows.append({"cost_rt": cst, **stats(tr, cfg)})
    return pd.DataFrame(rows)
