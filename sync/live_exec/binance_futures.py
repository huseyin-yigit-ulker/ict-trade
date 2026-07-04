"""Signed Binance USDⓈ-M Futures REST client — raw `requests` + stdlib HMAC (no ccxt).

Mirrors the retry/backoff shape of backtest/ict/data.fetch_klines and the BINANCE_PROXY egress
hook from dag/dag.py. Only the ~9 endpoints the executor / safety sweep / killswitch need:

  public : time, exchangeInfo
  signed : account, positionRisk, openOrders, order (new), cancelOrder, cancelAllOpenOrders,
           userTrades, leverage, marginType

Every signed call appends `timestamp` + `recvWindow`, then a SHA256 HMAC `signature` over the
exact query string. Binance error bodies look like {"code": -2011, "msg": "..."} — we surface
those as BinanceError(code, msg) so callers can treat "already done" codes as success
(idempotency: -4015 dup order, -2011/-2013 unknown cancel, -4046 no margin-type change).
"""
from __future__ import annotations

import hmac
import time
import hashlib
import urllib.parse
from typing import Any

import requests


class BinanceError(RuntimeError):
    def __init__(self, code: int, msg: str, status: int = 0):
        super().__init__(f"[{code}] {msg}")
        self.code = code
        self.msg = msg
        self.status = status


class BinanceFutures:
    def __init__(self, *, api_key: str, api_secret: str, base_url: str,
                 proxy: str = "", recv_window: int = 5000, timeout: int = 20):
        self.key = api_key
        self.secret = (api_secret or "").encode()
        self.base = base_url.rstrip("/")
        self.recv_window = recv_window
        self.timeout = timeout
        self._proxies = {"http": proxy, "https": proxy} if proxy else None
        self._time_offset_ms = 0          # serverTime - localTime, refreshed by sync_time()

    # ---------------------------------------------------------------- low level
    def _headers(self) -> dict:
        return {"X-MBX-APIKEY": self.key} if self.key else {}

    def _now_ms(self) -> int:
        return int(time.time() * 1000) + self._time_offset_ms

    def _request(self, method: str, path: str, params: dict | None = None,
                 *, signed: bool = False) -> Any:
        params = dict(params or {})
        if signed:
            params["timestamp"] = self._now_ms()
            params["recvWindow"] = self.recv_window
            query = urllib.parse.urlencode(params, doseq=True)
            sig = hmac.new(self.secret, query.encode(), hashlib.sha256).hexdigest()
            query = f"{query}&signature={sig}"
        else:
            query = urllib.parse.urlencode(params, doseq=True)
        url = f"{self.base}{path}" + (f"?{query}" if query else "")

        last_exc: Exception | None = None
        for attempt in range(5):
            try:
                r = requests.request(method, url, headers=self._headers(),
                                     timeout=self.timeout, proxies=self._proxies)
                # transient: rate limit / ban / 5xx -> back off & retry (same policy as data.py)
                if r.status_code in (418, 429) or r.status_code >= 500:
                    raise requests.exceptions.RequestException(f"HTTP {r.status_code}")
                if r.status_code >= 400:
                    try:
                        body = r.json()
                        raise BinanceError(int(body.get("code", 0)), str(body.get("msg", r.text)), r.status_code)
                    except ValueError:
                        raise BinanceError(0, r.text[:200], r.status_code)
                return r.json() if r.text else {}
            except requests.exceptions.RequestException as e:
                last_exc = e
                if attempt == 4:
                    break
                time.sleep(1.5 * (2 ** attempt))      # 1.5, 3, 6, 12s
        raise BinanceError(0, f"network: {last_exc}")

    # ---------------------------------------------------------------- public
    def server_time(self) -> int:
        return int(self._request("GET", "/fapi/v1/time")["serverTime"])

    def sync_time(self) -> int:
        """Align the local clock to Binance's; returns the offset (ms). Signed calls fail with
        -1021 if |drift| > recvWindow, so callers run this once at boot."""
        srv = self.server_time()
        self._time_offset_ms = srv - int(time.time() * 1000)
        return self._time_offset_ms

    def exchange_info(self) -> dict:
        return self._request("GET", "/fapi/v1/exchangeInfo")

    # ---------------------------------------------------------------- account / positions
    def account(self) -> dict:
        return self._request("GET", "/fapi/v2/account", signed=True)

    def position_risk(self, symbol: str | None = None) -> list[dict]:
        p = {"symbol": symbol} if symbol else {}
        out = self._request("GET", "/fapi/v2/positionRisk", p, signed=True)
        return out if isinstance(out, list) else [out]

    def open_orders(self, symbol: str | None = None) -> list[dict]:
        p = {"symbol": symbol} if symbol else {}
        out = self._request("GET", "/fapi/v1/openOrders", p, signed=True)
        return out if isinstance(out, list) else [out]

    def user_trades(self, symbol: str, *, limit: int = 100, start_ms: int | None = None) -> list[dict]:
        p: dict = {"symbol": symbol, "limit": limit}
        if start_ms is not None:
            p["startTime"] = start_ms
        return self._request("GET", "/fapi/v1/userTrades", p, signed=True)

    def income(self, *, symbol: str | None = None, income_type: str | None = None,
               start_ms: int | None = None, limit: int = 1000) -> list[dict]:
        """Income history (/fapi/v1/income). incomeType='FUNDING_FEE' isolates the 8-hourly funding
        cashflows on a perp: each row's `income` is <0 when WE paid funding, >0 when we received it.
        Summed since a position's entry, it is the funding cost accrued while that trade is open."""
        p: dict = {"limit": limit}
        if symbol is not None:
            p["symbol"] = symbol
        if income_type is not None:
            p["incomeType"] = income_type
        if start_ms is not None:
            p["startTime"] = start_ms
        out = self._request("GET", "/fapi/v1/income", p, signed=True)
        return out if isinstance(out, list) else []

    def get_order(self, symbol: str, *, client_order_id: str | None = None,
                  order_id: int | None = None) -> dict:
        p: dict = {"symbol": symbol}
        if client_order_id is not None:
            p["origClientOrderId"] = client_order_id
        if order_id is not None:
            p["orderId"] = order_id
        return self._request("GET", "/fapi/v1/order", p, signed=True)

    # ---------------------------------------------------------------- account setup
    def set_leverage(self, symbol: str, leverage: int) -> dict:
        return self._request("POST", "/fapi/v1/leverage",
                             {"symbol": symbol, "leverage": leverage}, signed=True)

    def set_margin_type(self, symbol: str, margin_type: str) -> dict:
        """ISOLATED|CROSSED. -4046 ('No need to change margin type') == already set == success."""
        try:
            return self._request("POST", "/fapi/v1/marginType",
                                 {"symbol": symbol, "marginType": margin_type}, signed=True)
        except BinanceError as e:
            if e.code == -4046:
                return {"code": -4046, "msg": "already set"}
            raise

    # ---------------------------------------------------------------- orders
    def new_order(self, **params) -> dict:
        """Place an order. -4015 (duplicate clientOrderId) == already placed == success: the
        caller re-fetches by clientOrderId. Pass newClientOrderId for idempotency."""
        try:
            return self._request("POST", "/fapi/v1/order", params, signed=True)
        except BinanceError as e:
            if e.code == -4015 and params.get("newClientOrderId"):
                return self.get_order(params["symbol"], client_order_id=params["newClientOrderId"])
            raise

    def cancel_order(self, symbol: str, *, client_order_id: str | None = None,
                     order_id: int | None = None) -> dict:
        """Cancel one order. -2011 (unknown) / -2013 (does not exist) == already gone == success."""
        p: dict = {"symbol": symbol}
        if client_order_id is not None:
            p["origClientOrderId"] = client_order_id
        if order_id is not None:
            p["orderId"] = order_id
        try:
            return self._request("DELETE", "/fapi/v1/order", p, signed=True)
        except BinanceError as e:
            if e.code in (-2011, -2013):
                return {"code": e.code, "msg": "already gone"}
            raise

    def cancel_all_open_orders(self, symbol: str) -> dict:
        try:
            return self._request("DELETE", "/fapi/v1/allOpenOrders", {"symbol": symbol}, signed=True)
        except BinanceError as e:
            if e.code in (-2011, -2013):
                return {"code": e.code, "msg": "none"}
            raise

    # ---- Algo (CONDITIONAL) orders ----------------------------------------------------------------
    # Binance migrated conditional orders (STOP_MARKET/TAKE_PROFIT_MARKET/STOP/TAKE_PROFIT/TRAILING)
    # to the Algo Service on 2025-12-09: the legacy /fapi/v1/order rejects them with -4120, they must
    # go to /fapi/v1/algoOrder (algoType=CONDITIONAL, triggerPrice instead of stopPrice).
    def new_algo_order(self, **params) -> dict:
        params.setdefault("algoType", "CONDITIONAL")
        return self._request("POST", "/fapi/v1/algoOrder", params, signed=True)

    def open_algo_orders(self, symbol: str | None = None) -> list[dict]:
        r = self._request("GET", "/fapi/v1/openAlgoOrders", {"symbol": symbol} if symbol else {}, signed=True)
        orders = r.get("orders", r) if isinstance(r, dict) else r
        return [o for o in orders if not symbol or o.get("symbol") == symbol] if isinstance(orders, list) else []

    def cancel_algo_order(self, *, algo_id=None, client_algo_id=None) -> dict:
        p: dict = {}
        if algo_id is not None:
            p["algoId"] = algo_id
        if client_algo_id is not None:
            p["clientAlgoId"] = client_algo_id
        try:
            return self._request("DELETE", "/fapi/v1/algoOrder", p, signed=True)
        except BinanceError as e:
            if e.code in (-2011, -2013):
                return {"code": e.code, "msg": "already gone"}
            raise

    def cancel_all_algo_orders(self, symbol: str) -> None:
        """No bulk endpoint — cancel each open CONDITIONAL order on the symbol (best-effort)."""
        for o in self.open_algo_orders(symbol):
            aid = o.get("algoId")
            if aid is not None:
                try:
                    self.cancel_algo_order(algo_id=aid)
                except BinanceError:
                    pass
