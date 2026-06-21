"""exchangeInfo cache + symbol-filter helpers (tick/step rounding, min-notional, tradability).

Binance rejects orders whose price isn't a multiple of PRICE_FILTER.tickSize or whose qty isn't
a multiple of LOT_SIZE.stepSize, and whose notional is below the symbol's MIN_NOTIONAL. This
quantizes our deterministic levels to the exchange grid and screens symbols at boot:
only status=TRADING + contractType=PERPETUAL pass (so XAUUSDT and any delisted/settling perp
are rejected automatically — they never become a managed position).
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class SymbolFilters:
    symbol: str
    tick_size: float
    step_size: float
    min_qty: float
    min_notional: float
    price_precision: int
    qty_precision: int
    tradable: bool          # status==TRADING and contractType==PERPETUAL


def _round_to(value: float, step: float, *, mode: str) -> float:
    if step <= 0:
        return float(value)
    n = value / step
    if mode == "floor":
        n = math.floor(n + 1e-9)
    elif mode == "ceil":
        n = math.ceil(n - 1e-9)
    else:
        n = round(n)
    return n * step


class ExchangeInfo:
    """Parsed exchangeInfo, queried per symbol. Build once per process from client.exchange_info()."""

    def __init__(self, raw: dict):
        self._by_symbol: dict[str, SymbolFilters] = {}
        for s in raw.get("symbols", []):
            sym = s.get("symbol")
            if not sym:
                continue
            tick = step = min_qty = min_notional = 0.0
            for f in s.get("filters", []):
                ft = f.get("filterType")
                if ft == "PRICE_FILTER":
                    tick = float(f.get("tickSize", 0) or 0)
                elif ft == "LOT_SIZE":
                    step = float(f.get("stepSize", 0) or 0)
                    min_qty = float(f.get("minQty", 0) or 0)
                elif ft in ("MIN_NOTIONAL", "NOTIONAL"):
                    min_notional = float(f.get("notional", f.get("minNotional", 0)) or 0)
            self._by_symbol[sym] = SymbolFilters(
                symbol=sym,
                tick_size=tick,
                step_size=step,
                min_qty=min_qty,
                min_notional=min_notional,
                price_precision=int(s.get("pricePrecision", 8)),
                qty_precision=int(s.get("quantityPrecision", 8)),
                tradable=(s.get("status") == "TRADING" and s.get("contractType") == "PERPETUAL"),
            )

    def get(self, symbol: str) -> SymbolFilters | None:
        return self._by_symbol.get(symbol)

    def is_tradable_perp(self, symbol: str) -> bool:
        f = self._by_symbol.get(symbol)
        return bool(f and f.tradable)

    def round_price(self, symbol: str, price: float, *, mode: str = "nearest") -> float:
        f = self._by_symbol.get(symbol)
        if not f:
            return float(price)
        return round(_round_to(price, f.tick_size, mode=mode), f.price_precision)

    def floor_qty(self, symbol: str, qty: float) -> float:
        f = self._by_symbol.get(symbol)
        if not f:
            return float(qty)
        return round(_round_to(qty, f.step_size, mode="floor"), f.qty_precision)

    def passes_min_notional(self, symbol: str, qty: float, price: float) -> bool:
        f = self._by_symbol.get(symbol)
        if not f:
            return False
        if f.min_qty and qty < f.min_qty:
            return False
        return (qty * price) >= f.min_notional
