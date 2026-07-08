"""Labels + trade-sequence features for MIDAS meta-labeling.

Meta-label (López de Prado ch.3): the primary model (MIDAS signals()+walk()) decides side and
timing; the meta-label is simply whether that trade ended positive under the live exit engine
(1.5*ATR stop, 3.5*ATR chandelier trail, 8h cap, session flatten). Using the REAL walk() R keeps
the label faithful to live rules — no separate barrier approximation needed.

Trade-sequence features generalize the shipped AFTER-LOSS exec gate (enter only if the previous
same-fx-day trade lost): prev_r_day / had_prev / n_today / cum_r_today. The canonical book is
sequential (one position at a time), so every "previous" trade has exited before the next signal
bar closes — no leakage.

A plain triple-barrier labeler is included for the (future) standalone Candidate-B model; it is
NOT used by the meta-model.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def meta_frame(trades, df: pd.DataFrame, taker_frac: float = 1e-3) -> pd.DataFrame:
    """One row per canonical trade: label + sequence features + bookkeeping.

    taker_frac: round-trip cost as a fraction of entry price for the alternative Binance-taker
    view (10 bps ≈ $4/oz at $4000). r_taker re-derives R from the trade's own fill prices.
    """
    fx_day = pd.Series(df["fx_day"].to_numpy(), index=df.index)
    rows = []
    prev_by_day: dict = {}
    for t in trades:
        d = fx_day.loc[t.signal_time]
        hist = prev_by_day.get(d, [])
        sd = abs(t.entry - t.stop)
        gross = (t.exit_px - t.entry) * t.side
        rows.append({
            "signal_time": t.signal_time, "entry_time": t.entry_time, "exit_time": t.exit_time,
            "side": t.side, "r": t.pnl_r, "y": int(t.pnl_r > 0),
            "r_taker": (gross - taker_frac * t.entry) / sd,
            "reason": t.reason,
            "prev_r_day": hist[-1] if hist else np.nan,
            "had_prev": int(bool(hist)),
            "n_today": len(hist),
            "cum_r_today": float(np.sum(hist)) if hist else 0.0,
        })
        prev_by_day.setdefault(d, []).append(t.pnl_r)
    return pd.DataFrame(rows)


def triple_barrier(df: pd.DataFrame, atr: pd.Series, *, k_up: float = 3.5, k_dn: float = 1.5,
                   horizon_min: int = 480) -> pd.DataFrame:
    """Candidate-B labeler (unused by the meta-model): for each bar, the LONG outcome of a
    +k_up*ATR / -k_dn*ATR / horizon barrier race starting at next-bar open. Short = mirror."""
    o = df["open"].to_numpy(); h = df["high"].to_numpy(); lo = df["low"].to_numpy()
    a = atr.to_numpy(); n = len(df)
    lab = np.full(n, np.nan)
    for i in range(n - 1):
        if not np.isfinite(a[i]) or a[i] <= 0:
            continue
        e = o[i + 1]; up = e + k_up * a[i]; dn = e - k_dn * a[i]
        end = min(n, i + 1 + horizon_min)
        for j in range(i + 1, end):
            if lo[j] <= dn:
                lab[i] = -1.0; break
            if h[j] >= up:
                lab[i] = 1.0; break
        else:
            lab[i] = 0.0
    return pd.DataFrame({"tb_long": lab}, index=df.index)
