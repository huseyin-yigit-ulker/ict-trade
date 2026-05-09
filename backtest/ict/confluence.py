"""Confluence scoring & multi-strategy signal merging."""

from __future__ import annotations
from typing import Iterable

from . import config as C
from .strategies import Signal


def score(signal: Signal) -> int:
    return sum(C.CONFLUENCE_WEIGHTS.get(f, 0) for f in signal.confluence_factors)


def merge_same_bar(signals: list[Signal]) -> list[Signal]:
    """Group signals at the same (symbol, bar_index, direction) into a composite.

    Opposite-direction signals at the same bar cancel each other (per spec §6.2).
    """
    if not signals:
        return []

    by_key: dict[tuple, list[Signal]] = {}
    for s in signals:
        by_key.setdefault((s.symbol, s.bar_index), []).append(s)

    out: list[Signal] = []
    for (symbol, bar_idx), group in by_key.items():
        longs = [s for s in group if s.direction == "long"]
        shorts = [s for s in group if s.direction == "short"]

        # Same-direction: composite. Cross-direction: highest score wins; tie cancels.
        for direction_group in (longs, shorts):
            if not direction_group:
                continue
            scored = [(score(s) + (C.CONFLUENCE_WEIGHTS["multi_strategy"] if len(direction_group) > 1 else 0), s)
                      for s in direction_group]
            scored.sort(key=lambda x: x[0], reverse=True)

            top_score = scored[0][0]
            top_signal = scored[0][1]
            top_signal.confluence_score = min(top_score, C.CONFLUENCE_MAX)

            if len(direction_group) > 1:
                top_signal.strategy = "composite"
                top_signal.context["composing_strategies"] = [s.strategy for s in direction_group]
                if "multi_strategy" not in top_signal.confluence_factors:
                    top_signal.confluence_factors.append("multi_strategy")

            if top_signal.confluence_score >= C.CONFLUENCE_HIGH:
                top_signal.quality = "high"
            elif top_signal.confluence_score >= C.CONFLUENCE_MIN_PUBLISH:
                top_signal.quality = "medium"
            else:
                continue  # below publish threshold

            out.append(top_signal)

        # cross-direction conflict: drop both if scores tie
        if longs and shorts:
            l_top = max((score(s) for s in longs), default=0)
            s_top = max((score(s) for s in shorts), default=0)
            if l_top == s_top:
                # remove both directions for this bar
                out = [o for o in out if not (o.symbol == symbol and o.bar_index == bar_idx)]

    return out
