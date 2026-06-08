"""Signal engine: scan a multi-timeframe dataset and emit signals from all 5 strategies."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from ict import config as C
from ict.data import aggregate
from ict.indicators import atr
from ict.detectors import (
    detect_swings, detect_structure,
    detect_persistent_liquidity, detect_equal_levels, mark_sweeps,
    detect_order_blocks, detect_fvgs, htf_bias,
)
from ict.strategies import Signal, STRATEGIES
from ict.confluence import merge_same_bar


@dataclass
class DetectorBundle:
    df: pd.DataFrame
    atr: pd.Series
    swings: list = field(default_factory=list)
    structure: list = field(default_factory=list)
    liquidity: list = field(default_factory=list)
    order_blocks: list = field(default_factory=list)
    fvgs: list = field(default_factory=list)
    htf_bias_series: Optional[pd.Series] = None
    expiry_bars: int = C.ENTRY_EXPIRY_BARS
    bar_minutes: float = 5.0


def _bar_minutes(df: pd.DataFrame) -> float:
    if len(df) < 2:
        return 5.0
    return float((df.index[1] - df.index[0]).total_seconds()) / 60.0


def _compute_htf_bias_series(df: pd.DataFrame, htf_rule: str = C.HTF_RULE) -> pd.Series:
    """Build a per-bar HTF bias series aligned to the primary df's timestamps.

    Aggregation is done from the primary df itself; no extra data fetch needed.
    """
    df_htf = aggregate(df, htf_rule)
    if df_htf.empty:
        return pd.Series(["range"] * len(df), index=df.index)

    htf_swings = detect_swings(df_htf, n=C.SWING_N_HTF)
    htf_structure = detect_structure(df_htf, htf_swings)
    bias_per_htf_bar = [htf_bias(htf_structure, i) for i in range(len(df_htf))]
    htf_bias_at_htf = pd.Series(bias_per_htf_bar, index=df_htf.index)
    # Forward-fill onto primary timeline so each primary bar inherits the most-recent
    # confirmed HTF bias.
    return htf_bias_at_htf.reindex(df.index, method="ffill").fillna("range")


def build_detectors(df: pd.DataFrame, swing_n: int = C.SWING_N_ITF,
                    htf_rule: str = C.HTF_RULE) -> DetectorBundle:
    a = atr(df, C.ATR_PERIOD)
    sw = detect_swings(df, n=swing_n)
    st = detect_structure(df, sw)
    pl = detect_persistent_liquidity(df)
    eq = detect_equal_levels(sw, a)
    levels = pl + eq
    mark_sweeps(df, levels)
    obs = detect_order_blocks(df, a)
    fv = detect_fvgs(df)

    htf_series = _compute_htf_bias_series(df, htf_rule)
    bm = _bar_minutes(df)
    expiry = max(2, int(C.EXPIRY_MINUTES / bm)) if bm > 0 else C.ENTRY_EXPIRY_BARS

    return DetectorBundle(df=df, atr=a, swings=sw, structure=st,
                          liquidity=levels, order_blocks=obs, fvgs=fv,
                          htf_bias_series=htf_series, expiry_bars=expiry,
                          bar_minutes=bm)


def build_geometry(df, bar_index, direction, entry,
                   structure_events, liquidity_levels, obs, fvgs, lookback=80):
    """Reconstruct the ICT decision geometry active at the signal bar so the UI
    can draw the FVG / Order-Block / swept-liquidity / BOS that framed the entry.

    READ-ONLY: never affects signal generation. Returns a JSON-serializable dict;
    bar indices resolved to unix seconds. Identical to dag.build_geometry."""
    idx = bar_index
    want_bull = direction == "long"

    def _ts(i):
        if i is None or i < 0 or i >= len(df.index):
            return None
        try:
            return int(df.index[i].timestamp())
        except Exception:
            return None

    geo = {}

    cand = []
    for o in obs:
        if o.created_at_index > idx:
            continue
        if o.mitigated and o.mitigation_index is not None and o.mitigation_index <= idx:
            continue
        if (o.type == "bullish_ob") != want_bull:
            continue
        cand.append(("OB", float(o.top), float(o.bottom), o.created_at_index))
    for f in fvgs:
        if f.created_at_index > idx:
            continue
        if f.filled_at_index is not None and f.filled_at_index <= idx:
            continue
        if (f.type == "bullish_fvg") != want_bull:
            continue
        cand.append(("FVG", float(f.top), float(f.bottom), f.created_at_index))
    if cand:
        def _score(z):
            _, top, bot, _i = z
            contains = 0 if (bot <= entry <= top) else 1
            return (contains, abs((top + bot) / 2 - entry))
        kind, top, bot, cidx = min(cand, key=_score)
        geo["entry_zone"] = {"kind": kind, "top": top, "bottom": bot, "from": _ts(cidx)}

    swept = [l for l in liquidity_levels
             if l.swept and l.swept_at_index is not None
             and idx - lookback <= l.swept_at_index <= idx]
    if swept:
        s = max(swept, key=lambda l: l.swept_at_index)
        geo["swept"] = {"type": s.type, "price": float(s.level),
                        "created": _ts(s.created_at_index), "swept": _ts(s.swept_at_index)}

    sev = [e for e in structure_events
           if e.broken_at_index <= idx and idx - e.broken_at_index <= lookback]
    if sev:
        e = max(sev, key=lambda ev: ev.broken_at_index)
        geo["structure"] = {"type": e.type, "direction": e.direction,
                            "level": float(e.broken_level), "at": _ts(e.broken_at_index)}

    tgt = None
    for l in liquidity_levels:
        if l.created_at_index > idx:
            continue
        if l.swept and l.swept_at_index is not None and l.swept_at_index <= idx:
            continue
        if direction == "long" and l.level > entry:
            tgt = l.level if tgt is None else min(tgt, l.level)
        elif direction == "short" and l.level < entry:
            tgt = l.level if tgt is None else max(tgt, l.level)
    if tgt is not None:
        geo["target_liquidity"] = float(tgt)

    return geo


def run_engine(symbol: str, df: pd.DataFrame, *, start_index: Optional[int] = None,
               end_index: Optional[int] = None,
               strategies: Optional[list] = None,
               htf_rule: Optional[str] = None) -> list[Signal]:
    """Walk bars [start..end] and run the given strategies (default: all 5).

    Pass `strategies=[strategy_b, strategy_c, ...]` to filter — the live runner
    uses this to exclude underperformers (e.g. strategy_a) without touching
    backtest behaviour.

    Pass `htf_rule` to override the HTF-bias aggregation timeframe (default
    C.HTF_RULE = "4h"). The 15m Pulse pipeline passes "1h" so the HTF stays a
    proportionate 4:1 step above the primary TF."""
    bundle = build_detectors(df, htf_rule=htf_rule or C.HTF_RULE)
    n = len(df)
    if start_index is None:
        start_index = max(C.ATR_PERIOD + 5, C.SWING_N_ITF + 5)
    if end_index is None:
        end_index = n - 1

    strats = strategies if strategies is not None else STRATEGIES

    raw: list[Signal] = []
    for i in range(start_index, end_index + 1):
        for strat_fn in strats:
            try:
                sig = strat_fn(symbol, df, i, bundle.atr, bundle.structure,
                               bundle.liquidity, bundle.order_blocks, bundle.fvgs,
                               htf_bias_series=bundle.htf_bias_series,
                               expiry_bars=bundle.expiry_bars)
            except Exception:
                continue
            if sig is not None:
                # Pending-limit validity: at fire (bar CLOSE) price must be on the
                # retrace side of the entry limit (LONG: close>entry, SHORT: close<entry).
                # Drop "already-passed" setups where price is already through the entry.
                try:
                    _c = float(df["close"].iloc[sig.bar_index])
                    if (_c <= sig.entry) if sig.direction == "long" else (_c >= sig.entry):
                        continue
                except Exception:
                    pass
                try:
                    sig.context["geometry"] = build_geometry(
                        df, sig.bar_index, sig.direction, sig.entry,
                        bundle.structure, bundle.liquidity, bundle.order_blocks, bundle.fvgs)
                except Exception:
                    pass
                raw.append(sig)

    return merge_same_bar(raw)
