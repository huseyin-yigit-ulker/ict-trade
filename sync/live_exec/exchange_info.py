"""exchangeInfo cache + symbol-filter helpers (tick/step rounding, min-notional, tradability).

Binance rejects orders whose price isn't a multiple of PRICE_FILTER.tickSize or whose qty isn't
a multiple of LOT_SIZE.stepSize, and whose notional is below the symbol's MIN_NOTIONAL. This
quantizes our deterministic levels to the exchange grid and screens symbols at boot.

Tradability is contract-type aware: `is_tradable_perp()` (the OPUS/Donchian gate) still passes ONLY
status=TRADING + contractType=PERPETUAL, but the raw contractType is now retained so a caller can opt
into other live contract classes. Gold on Binance USDⓈ-M is a `TRADIFI_PERPETUAL` (NOT `PERPETUAL`),
so MIDAS calls `is_tradable("XAUUSDT", allow=("PERPETUAL","TRADIFI_PERPETUAL"))` to trade it while the
plain-perp streams keep rejecting it automatically.
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
    tradable: bool          # status==TRADING and contractType==PERPETUAL (the plain-perp gate)
    contract_type: str = "" # raw contractType, e.g. 'PERPETUAL' | 'TRADIFI_PERPETUAL' | 'CURRENT_QUARTER'
    status: str = ""        # raw status, e.g. 'TRADING'


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
            ctype = str(s.get("contractType") or "")
            status = str(s.get("status") or "")
            self._by_symbol[sym] = SymbolFilters(
                symbol=sym,
                tick_size=tick,
                step_size=step,
                min_qty=min_qty,
                min_notional=min_notional,
                price_precision=int(s.get("pricePrecision", 8)),
                qty_precision=int(s.get("quantityPrecision", 8)),
                tradable=(status == "TRADING" and ctype == "PERPETUAL"),
                contract_type=ctype,
                status=status,
            )

    def get(self, symbol: str) -> SymbolFilters | None:
        return self._by_symbol.get(symbol)

    def is_tradable(self, symbol: str, *, allow: tuple[str, ...] = ("PERPETUAL",)) -> bool:
        """status=TRADING and contractType in `allow`. Default = plain perps only (OPUS behaviour).
        MIDAS passes allow=('PERPETUAL','TRADIFI_PERPETUAL') to trade the Binance gold contract."""
        f = self._by_symbol.get(symbol)
        return bool(f and f.status == "TRADING" and f.contract_type in allow)

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
