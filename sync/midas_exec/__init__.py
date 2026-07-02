"""MIDAS real-money-capable Binance executor (gold XAUUSDT VWAP-trend). Testnet/dry-run first.

Clones the OPUS/Donchian executor pattern (sync/live_exec) but implements MIDAS's own mechanics:
a post-only maker LIMIT entry, a 1.5*ATR initial stop, and a 3.5*ATR chandelier trailing stop to an
8h/session exit — driven by the SAME sync/midas/strategy.track_open the paper feed uses.
"""
