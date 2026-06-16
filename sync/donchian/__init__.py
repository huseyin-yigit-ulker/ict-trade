"""Donchian strategies — the TREND/momentum complement to the RANGE/main book.

A Donchian(55) breakout system gated to the strong-trend regime (Kaufman ER >= 0.35),
where the mean-reversion 'main' set is weak — a low-overlap diversifier.

Submodules:
    strategy  — shared signal generator (generate_signals) + parameters
    backtest  — historical R backfill   -> trading_signals.version = 'donchian'
    canli     — live signal emission     -> ict_trade.signals.mode  = 'donchian'
"""
from . import strategy  # noqa: F401
