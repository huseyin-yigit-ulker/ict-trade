"""TALOS real-money-capable Binance executor (gold XAUUSDT Keltner-trend). Testnet/dry-run first.

Clones the OPUS/Donchian executor pattern (sync/live_exec) but implements TALOS's own mechanics:
a post-only maker LIMIT entry, a 1.5*ATR initial stop, and a 3.5*ATR chandelier trailing stop to an
8h/session exit — driven by the SAME sync/talos/strategy.track_open the paper feed uses.
"""
