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


def build_detectors(df: pd.DataFrame, swing_n: int = C.SWING_N_ITF) -> DetectorBundle:
    a = atr(df, C.ATR_PERIOD)
    sw = detect_swings(df, n=swing_n)
    st = detect_structure(df, sw)
    pl = detect_persistent_liquidity(df)
    eq = detect_equal_levels(sw, a)
    levels = pl + eq
    mark_sweeps(df, levels)
    obs = detect_order_blocks(df, a)
    fv = detect_fvgs(df)

    htf_series = _compute_htf_bias_series(df)
    bm = _bar_minutes(df)
    expiry = max(2, int(C.EXPIRY_MINUTES / bm)) if bm > 0 else C.ENTRY_EXPIRY_BARS

    return DetectorBundle(df=df, atr=a, swings=sw, structure=st,
                          liquidity=levels, order_blocks=obs, fvgs=fv,
                          htf_bias_series=htf_series, expiry_bars=expiry,
                          bar_minutes=bm)


def run_engine(symbol: str, df: pd.DataFrame, *, start_index: Optional[int] = None,
               end_index: Optional[int] = None) -> list[Signal]:
    """Walk bars [start..end] and run all strategies. Returns merged/scored signals."""
    bundle = build_detectors(df)
    n = len(df)
    if start_index is None:
        start_index = max(C.ATR_PERIOD + 5, C.SWING_N_ITF + 5)
    if end_index is None:
        end_index = n - 1

    raw: list[Signal] = []
    for i in range(start_index, end_index + 1):
        for strat_fn in STRATEGIES:
            try:
                sig = strat_fn(symbol, df, i, bundle.atr, bundle.structure,
                               bundle.liquidity, bundle.order_blocks, bundle.fvgs,
                               htf_bias_series=bundle.htf_bias_series,
                               expiry_bars=bundle.expiry_bars)
            except Exception:
                continue
            if sig is not None:
                raw.append(sig)

    return merge_same_bar(raw)
