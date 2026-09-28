"""d30so8c live executor — the fast reconciler (cron #1) and the Faz-0 dry-run intent logger.

DRY (no recompute): reads the SAME dch30_4h live signals the dashboard/backtest use
(ict_trade.signals, mode='dch30_4h') and drives real Binance USDⓈ-M Futures orders that
reproduce sync/donchian/scaleout.resolve_scaleout — entry @ +0.5R confirm (Mode B), full SL,
TP1 +1R booking 60%, runner to breakeven / +8R structural cap / 3-day mark-to-market.

Stateless: every tick reduces (DB intent in ict_trade.live_positions, exchange reality from
positionRisk/openOrders) idempotently via deterministic clientOrderIds, so it is crash-safe and
can be killed/restarted any time without double-placing.

    EXEC_DRY_RUN=true  python sync/live_exec/executor.py        # log intents, send NOTHING
    EXEC_DRY_RUN=false LIVE_TRADING_ENABLED=true python sync/live_exec/executor.py   # armed

Master no-op when LIVE_TRADING_ENABLED=false.
"""
from __future__ import annotations

import re
import sys
import json
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent))               # sync/live_exec
sys.path.insert(0, str(_HERE.parents[1]))           # sync/
sys.path.insert(0, str(_HERE.parents[1] / "users")) # sync/users -> store (multi-user fan-out)
import _bootenv                                      # noqa: E402,F401  -- MUST precede tsc/scaleout/ict.config
import trade_sync_common as tsc                      # noqa: E402
import config as cfgmod                              # noqa: E402
import state as st                                   # noqa: E402
import levels as lvl                                 # noqa: E402
import sizing                                        # noqa: E402
import notify                                        # noqa: E402
import trade_report                                  # noqa: E402  (kapanış grafiği + net ROI; best-effort)
import store as ustore                               # noqa: E402  (sync/users/store.py)
import killswitch as ks                              # noqa: E402  (flatten_positions)
from binance_futures import BinanceFutures, BinanceError   # noqa: E402
from exchange_info import ExchangeInfo               # noqa: E402

LTF_MIN = 30                                         # dch30_4h base timeframe
MODE = "dch30_4h"
NEW_SIGNAL_LOOKBACK_MIN = tsc.EXPIRY_MINUTES + 60    # window to scan for not-yet-managed signals
MAX_MARGIN_RETRIES = 5

# Display name (EXEC_NAME, e.g. 'OPUS') prepended to the version tag in every Telegram alert, so the
# receiver knows which strategy fired. Falls back to the bare version tag when unset.
_NAME = (tsc._read_env().get("EXEC_NAME") or "").strip()
_TAG = f"{_NAME} · {st.VERSION}" if _NAME else st.VERSION

_HTML_RE = re.compile(r"<[^>]+>")


def _alert(cfg, conn, text: str, *, title: str = "", kind: str = "") -> None:
    """Per-user event routing: Telegram stays the owner/admin channel (canonical account only,
    exactly today's behavior); the account's own user additionally gets a personal Web Push
    (push_outbox -> sync/push_notify.py). Best-effort on both legs.
    kind ('entry'|'exit'|'milestone'|'system') sadece push ayağını süzer (user_prefs
    bildirim tercihleri); Telegram/owner kanalı her zaman tam akışı alır."""
    if cfg.is_canonical:
        notify.alert(text, chat_id=cfg.telegram_chat_id)
    if cfg.user_id:
        body = _HTML_RE.sub("", text)
        ustore.push_user(conn, cfg.user_id, title or body.split("\n", 1)[0][:60], body,
                         tag="", kind=kind)  # boş tag: sabit "exec" ardışık olayları tek bildirimde eziyordu (2026-07-14)


def _net(cfg) -> str:
    return "testnet" if cfg.testnet else "mainnet"


# ------------------------------------------------------------------ wiring
def _client(cfg) -> BinanceFutures:
    c = BinanceFutures(api_key=cfg.api_key, api_secret=cfg.api_secret,
                       base_url=cfg.base_url, proxy=cfg.proxy)
    return c


def _ensure_account(cfg, client, symbol: str) -> None:
    """Idempotent per-symbol account setup (armed only): leverage + isolated margin."""
    if not cfg.armed:
        return
    client.set_margin_type(symbol, cfg.margin_type)
    client.set_leverage(symbol, cfg.leverage)


# ------------------------------------------------------------------ shared per-tick caches
class SharedTick:
    """Everything user-INDEPENDENT in one cron tick, computed once and memoized so N users
    never multiply the market-data footprint (Binance REQUEST_WEIGHT is per IP — the shared
    VM egress is the scarce resource, account calls are per-key):
      * the recent-signal window (one query, per-user symbol filter applied in Python)
      * confirm gates per signal (pure market data — user-independent)
      * exchangeInfo + clock offset per network base URL
      * 1m klines per symbol (widest-range cache; narrower asks are slices)."""

    def __init__(self, now: pd.Timestamp):
        self.now = now
        self._signals: list[dict] | None = None
        self._gates: dict = {}
        self._xi: dict[str, ExchangeInfo] = {}
        self._off: dict[str, int] = {}
        self._k1m: dict[str, tuple[pd.Timestamp, object]] = {}

    def signals(self, live_conn) -> list[dict]:
        if self._signals is None:
            w_start = self.now - pd.Timedelta(minutes=NEW_SIGNAL_LOOKBACK_MIN + LTF_MIN)
            cur = live_conn.cursor()
            cur.execute("""
                SELECT symbol, signal_time, direction, entry, sl, tp, strategy
                FROM ict_trade.signals
                WHERE mode = %s AND signal_time >= %s
                ORDER BY symbol, signal_time
            """, (MODE, w_start.to_pydatetime()))
            cols = [d[0] for d in cur.description]
            self._signals = [dict(zip(cols, r)) for r in cur.fetchall()]
            cur.close()
        return self._signals

    def gate_for(self, cfg, sig: dict) -> tuple[str, object]:
        key = (sig["symbol"], str(sig["signal_time"]), str(sig["direction"]).upper())
        if key not in self._gates:
            self._gates[key] = _confirm_status(cfg, sig, self.now, shared=self)
        return self._gates[key]

    def sync_client(self, client) -> int:
        """One /fapi/v1/time per network per tick; later clients reuse the measured offset."""
        if client.base not in self._off:
            self._off[client.base] = client.sync_time()
        else:
            client._time_offset_ms = self._off[client.base]
        return self._off[client.base]

    def xi_for(self, client) -> ExchangeInfo:
        if client.base not in self._xi:
            self._xi[client.base] = ExchangeInfo(client.exchange_info())
        return self._xi[client.base]

    def fetch_1m(self, symbol: str, start, end):
        """Memoized tsc.fetch_1m. All executor asks end ≈ now; cache the widest [start, now]
        per symbol and answer narrower asks with a slice."""
        start = pd.Timestamp(start)
        start = start.tz_localize("UTC") if start.tz is None else start.tz_convert("UTC")
        cached = self._k1m.get(symbol)
        if cached is None or start < cached[0]:
            df = tsc.fetch_1m(symbol, start, end)
            self._k1m[symbol] = (start, df)
            return df
        df = cached[1]
        if df is None or getattr(df, "empty", True):
            return df
        return df[df.index >= start]


def _levels_for(cfg, sig: dict) -> lvl.Levels:
    return lvl.compute_levels(
        sig["direction"], float(sig["entry"]), float(sig["sl"]),
        entry_mode=cfg.entry_mode, confirm_buf=cfg.confirm_buf, first_r=cfg.first_r,
        close_frac=cfg.close_frac, runner_cap_r=cfg.runner_cap_r)


def _confirm_status(cfg, sig: dict, now: pd.Timestamp, shared: "SharedTick | None" = None
                    ) -> tuple[str, pd.DataFrame | None]:
    """'confirmed' | 'pending' | 'reversed' for one signal, from 1m since the bar close.
    confirmed = favourable +buf*risk printed before adverse −buf*risk within the window."""
    fire = pd.Timestamp(sig["signal_time"]).tz_convert("UTC") + pd.Timedelta(minutes=LTF_MIN)
    fetch = shared.fetch_1m if shared is not None else tsc.fetch_1m
    df1m = fetch(sig["symbol"], fire - pd.Timedelta(minutes=2), now)
    if df1m is None or df1m.empty:
        return "pending", None
    cf = tsc.confirm_fill(df1m, fire, sig["direction"], float(sig["entry"]), float(sig["sl"]),
                          expiry_minutes=cfg.expiry_min)
    if cf is not None:
        return "confirmed", df1m
    # distinguish reversed (adverse hit) vs still-pending (window open, neither hit)
    if now >= fire + pd.Timedelta(minutes=cfg.expiry_min):
        return "reversed", df1m
    return "pending", df1m


# ------------------------------------------------------------------ sizing / screen
def _size_and_screen(cfg, xi: ExchangeInfo, sig: dict, lv: lvl.Levels) -> tuple[float, float, str]:
    """Return (qty, tp1_qty, skip_reason). skip_reason='' means OK."""
    if not xi.is_tradable_perp(sig["symbol"]):
        return 0.0, 0.0, "not a tradable PERPETUAL (status/contractType)"
    total = xi.floor_qty(sig["symbol"], sizing.qty_for_risk(lv.eff_entry, lv.sl, cfg.risk_usd))
    if total <= 0:
        return 0.0, 0.0, "qty rounds to 0"
    if not xi.passes_min_notional(sig["symbol"], total, lv.eff_entry):
        return 0.0, 0.0, f"below MIN_NOTIONAL (qty={total} px={lv.eff_entry:g})"
    tp1q = sizing.split_tp1(sig["symbol"], total, cfg.close_frac, xi)
    return total, tp1q, ""


def _intent_dict(cfg, sig: dict, lv: lvl.Levels, qty: float, tp1q: float,
                 gate: str, xi: ExchangeInfo) -> dict:
    sym = sig["symbol"]
    rp = lambda p, m="nearest": xi.round_price(sym, p, mode=m)
    return {
        "symbol": sym, "direction": sig["direction"], "entry_mode": cfg.entry_mode, "gate": gate,
        "signal_time": str(pd.Timestamp(sig["signal_time"])),
        "risk0": round(lv.risk0, 10), "risk_usd": cfg.risk_usd,
        "entry": {"type": "STOP_MARKET" if cfg.entry_mode == "B" else "LIMIT",
                  "stopPrice": rp(lv.entry_stop), "qty": qty},
        "full_sl": {"type": "STOP_MARKET", "closePosition": True, "stopPrice": rp(lv.sl, "nearest")},
        "tp1": {"type": "TAKE_PROFIT_MARKET", "reduceOnly": True, "qty": tp1q,
                "stopPrice": rp(lv.tp1), "books_frac": cfg.close_frac},
        "runner_after_tp1": {
            "be_stop": {"type": "STOP_MARKET", "reduceOnly": True, "stopPrice": rp(lv.be)},
            "cap": {"type": "TAKE_PROFIT_MARKET", "reduceOnly": True,
                    "stopPrice": rp(lv.cap), "cap_r0": cfg.runner_cap_r},
        },
    }


# ------------------------------------------------------------------ order legs (armed)
def _side(direction: str) -> str:
    return "BUY" if str(direction).lower() == "long" else "SELL"


def _exit_side(direction: str) -> str:
    return "SELL" if str(direction).lower() == "long" else "BUY"


# NOTE on execution model: Binance Futures TESTNET rejects every conditional order type
# (STOP_MARKET / TAKE_PROFIT_MARKET / STOP / TRAILING) with -4120 ("use the Algo Order API"),
# so resting exchange-side brackets are impossible there. We therefore run a SYNTHETIC bracket:
# the reconciler walks 1m bars each tick (the SAME path scaleout.resolve_scaleout uses) and fires
# plain MARKET orders at the detected entry/SL/TP1/BE/cap/time-stop events. Portable to mainnet.
# Trade-off vs resting stops: protection depends on the cron running (mitigated by safety_sweep)
# and exits lag up to one reconcile interval + MARKET slippage — acceptable for testnet validation;
# revisit resting conditional orders for mainnet (where they ARE supported) if tighter stops matter.

def _market(client, conn, pos, qty, *, leg, reduce_only=True) -> dict | None:
    """Fire a MARKET order on `qty` (exit side for reduce-only closes; entry side otherwise).
    qty<=0 is a no-op (the position is already flat) — never send a -4003."""
    qty = float(qty or 0)
    if qty <= 0:
        return None
    sym = pos["symbol"]
    side = _exit_side(pos["direction"]) if reduce_only else _side(pos["direction"])
    coid = st.coid(pos["id"], leg)
    params = dict(symbol=sym, side=side, type="MARKET", quantity=qty, newClientOrderId=coid)
    if reduce_only:
        params["reduceOnly"] = "true"
    resp = client.new_order(**params)
    st.log_order(conn, position_id=pos["id"], symbol=sym, leg=leg, action="fill",
                 client_order_id=coid, order_id=resp.get("orderId"), payload=resp,
                 user_id=pos.get("user_id"))
    return resp


# ---- exchange-side protective stop (MAINNET only) -----------------------------------------------
# Testnet rejects every conditional order (-4120), so resting brackets are MAINNET-only; testnet keeps
# the synthetic reconciler exactly as before. On mainnet we lay a REAL STOP_MARKET(closePosition) at
# the SL (and, after TP1, at breakeven) so the −1R / breakeven cap is enforced by Binance the instant
# price hits it — no 2-min reconcile lag, and it survives the cron/VM dying (the whole reason this
# matters at high leverage). It runs ALONGSIDE the synthetic exit: whichever fires first wins; the
# loser is a no-op (closePosition on a flat position) and gets cancelled at finalize. Best-effort —
# a placement failure never breaks the reconcile (safety_sweep is the backstop for a missing stop).
def _place_protective_stop(cfg, client, conn, xi: ExchangeInfo, pos: dict, stop_px: float, *, leg: str) -> None:
    if cfg.testnet:
        return
    sym = pos["symbol"]
    try:
        # Conditional orders go to the Algo Service (POST /fapi/v1/algoOrder, triggerPrice) — the
        # legacy /fapi/v1/order rejects STOP_MARKET with -4120 since the 2025-12-09 migration.
        resp = client.new_algo_order(
            symbol=sym, side=_exit_side(pos["direction"]), type="STOP_MARKET",
            triggerPrice=xi.round_price(sym, stop_px, mode="nearest"),
            closePosition="true", workingType="MARK_PRICE")
        st.log_order(conn, position_id=pos["id"], symbol=sym, leg=leg, action="place",
                     client_order_id=resp.get("clientAlgoId"), order_id=resp.get("algoId"), payload=resp)
    except BinanceError as e:
        print(f"  ! {sym} protective {leg} algo place failed: {e} (safety_sweep will backstop)")


def _cancel_resting(cfg, client, sym: str) -> None:
    """Drop any resting protective order on the symbol (MAINNET) — called on every exit/transition so
    a filled/MARKET-closed leg never leaves a dangling closePosition order on the book."""
    if cfg.testnet:
        return
    try:
        client.cancel_all_open_orders(sym)      # regular LIMIT legs (e.g. exch_tp TP1/cap)
    except BinanceError:
        pass
    try:
        client.cancel_all_algo_orders(sym)      # conditional STOP/TP algo orders (SL / BE)
    except BinanceError:
        pass


def _place_tp_algos(cfg, client, conn, xi: ExchangeInfo, pos: dict, rl) -> None:
    """Exchange-side scale-out TPs as CONDITIONAL TAKE_PROFIT_MARKET algo orders (MAINNET) so they show
    as proper TP orders in the UI (separate from the SL): TP1 = tp1_qty @ +1R, cap = the runner
    remainder @ +capR. reduceOnly + quantity (partial). Triggers a MARKET book when price reaches the
    level. Best-effort — a failure never breaks the entry (the SL still protects)."""
    if cfg.testnet:
        return
    sym = pos["symbol"]
    tp1_q = xi.floor_qty(sym, float(pos["tp1_qty"]))
    cap_q = xi.floor_qty(sym, float(pos["qty"]) - tp1_q)
    for leg, q, px in (("tp1_tp", tp1_q, rl.tp1), ("cap_tp", cap_q, rl.cap)):
        if q <= 0:
            continue
        try:
            r = client.new_algo_order(
                symbol=sym, side=_exit_side(pos["direction"]), type="TAKE_PROFIT_MARKET",
                triggerPrice=xi.round_price(sym, px, mode="nearest"), quantity=q,
                reduceOnly="true", workingType="MARK_PRICE")
            st.log_order(conn, position_id=pos["id"], symbol=sym, leg=leg, action="place",
                         client_order_id=r.get("clientAlgoId"), order_id=r.get("algoId"), payload=r)
        except BinanceError as e:
            print(f"  ! {sym} {leg} TP algo place failed: {e}")


def _avg_fill(client, sym, resp) -> float:
    """avgPrice from the order response, else look it up (MARKET resp can omit it pre-fill)."""
    a = float(resp.get("avgPrice") or 0)
    if a:
        return a
    try:
        o = client.get_order(sym, order_id=resp.get("orderId"))
        return float(o.get("avgPrice") or o.get("price") or 0)
    except BinanceError:
        return 0.0


def _scan(df1m, since, direction: str, protect: float, target: float):
    """First-touch on 1m bars from `since`: returns ('protect'|'target'|None, ts, price).
    LONG: protect = a LOW breach (low<=protect), target = a HIGH breach (high>=target).
    SHORT mirrors. Same-bar tie -> protect (pessimistic), matching resolve_scaleout."""
    if df1m is None or df1m.empty:
        return None, None, None
    idx = df1m.index
    s = pd.Timestamp(since)
    s = s.tz_localize("UTC") if s.tz is None else s.tz_convert("UTC")
    lng = str(direction).lower() == "long"
    H = df1m["high"].values; L = df1m["low"].values
    p0 = int(idx.searchsorted(s))
    for i in range(p0, len(idx)):
        prot = (L[i] <= protect) if lng else (H[i] >= protect)
        tgt = (H[i] >= target) if lng else (L[i] <= target)
        if prot:
            return "protect", idx[i], protect
        if tgt:
            return "target", idx[i], target
    return None, None, None


def _realized_since(client, sym, since) -> float:
    """Sum realizedPnl (USDT) from userTrades since `since` — the true $ result of a position."""
    if not since:
        return 0.0
    try:
        start_ms = int(pd.Timestamp(since).timestamp() * 1000)
        return sum(float(t.get("realizedPnl", 0) or 0)
                   for t in client.user_trades(sym, limit=200, start_ms=start_ms))
    except BinanceError:
        return 0.0


def _funding_since(client, sym, since) -> float:
    """Sum FUNDING_FEE income (USDT) for `sym` since `since` — the funding paid (<0) / received (>0)
    over the current open position. Binance settles funding every 8h on a perp; userTrades.realizedPnl
    does NOT include it, so it is tracked separately here as the position's live funding cost."""
    if not since:
        return 0.0
    try:
        start_ms = int(pd.Timestamp(since).timestamp() * 1000)
        return sum(float(r.get("income", 0) or 0)
                   for r in client.income(symbol=sym, income_type="FUNDING_FEE", start_ms=start_ms))
    except BinanceError:
        return 0.0


def _open_entry_times(conn, symbols, user_id=None, network=None) -> dict:
    """symbol -> entry_fill_time of the currently-open managed position (anchors funding-since-entry)."""
    cur = conn.cursor()
    q = """
        SELECT symbol, min(entry_fill_time)
        FROM ict_trade.live_positions
        WHERE state in ('OPEN_FULL','RUNNER','CLOSING')
          AND entry_fill_time is not null AND symbol = ANY(%s)
    """
    params: list = [list(symbols)]
    if user_id is not None:
        q += " AND user_id = %s AND network = %s"
        params += [user_id, network]
    q += " GROUP BY symbol"
    cur.execute(q, tuple(params))
    out = {r[0]: r[1] for r in cur.fetchall()}
    cur.close()
    return out


def _reconcile_to_closed(cfg, client, conn, bt_conn, pos, now) -> None:
    """Binance is flat but DB still shows the position open — finalize from exchange truth
    (realizedPnl since entry), so the reconciler stops looping and the record is accurate."""
    sym = pos["symbol"]
    _cancel_resting(cfg, client, sym)               # drop any dangling protective stop on the book
    realized_usd = _realized_since(client, sym, pos.get("entry_fill_time"))
    risk_eff = abs(float(pos.get("eff_entry") or pos["signal_entry"]) - float(pos["signal_sl"]))
    denom = risk_eff * float(pos.get("qty") or 0)
    realized_r = (realized_usd / denom) if denom else None
    st.patch(conn, pos["id"], state=st.CLOSED, exit_reason="closed_externally",
             exit_time=now, realized_r=realized_r, realized_usd=realized_usd)
    exit_px = _last_price(sym, now)     # yalnız rapor için — DB semantiği değişmesin
    full = _reload(conn, pos["id"])
    if bt_conn is not None:
        st.writeback_trading_signals(bt_conn, full)
    if exit_px is not None:
        trade_report.report_close(client, cfg, full, reason="closed_externally", exit_px=exit_px,
                                  realized_r=realized_r, tag=_TAG)
    dirn = str(pos["direction"]).upper()
    if realized_r is None:
        head, tail = "🏁 KAPANDI", "borsada kapandı (R bilinmiyor)"
    else:
        head = ("🛑 STOP −1R" if realized_r <= -0.5 else
                "🏁 KÂR (runner/cap)" if realized_r >= 1.0 else
                "🏁 TP1+BE")
        tail = f"realized {realized_usd:+.2f}$ ({realized_r:+.2f}R)"
    _alert(cfg, conn, f"{head} · <b>{sym}</b> {dirn} #{pos['id']}\n"
                      f"borsa-emri kapanışı (SL/TP/cap tetiklendi) · {tail} — {_TAG}", kind="exit")


def _reverse_close(cfg, client, conn, bt_conn, pos, now) -> None:
    """An OPPOSITE-direction signal arrived for a held symbol — MARKET-close the position so the
    caller can open the flip (Binance one-way nets per symbol, so we must close before reversing).
    A not-yet-entered position is just cancelled. reason='reversed'."""
    sym = pos["symbol"]
    if not pos.get("entry_fill_time"):                      # never entered -> nothing on the exchange
        st.patch(conn, pos["id"], state=st.CANCELLED, exit_reason="reversed", exit_time=now)
        return
    amt = _position_amt(client, sym)
    if amt:
        _market(client, conn, pos, abs(amt), leg="reverse")
    _cancel_resting(cfg, client, sym)
    realized_usd = _realized_since(client, sym, pos.get("entry_fill_time"))
    risk_eff = abs(float(pos.get("eff_entry") or pos["signal_entry"]) - float(pos["signal_sl"]))
    denom = risk_eff * float(pos.get("qty") or 0)
    realized_r = (realized_usd / denom) if denom else None
    rev_exit_px = _last_price(sym, now)
    st.patch(conn, pos["id"], state=st.CLOSED, exit_reason="reversed", exit_time=now,
             exit_px=rev_exit_px, realized_r=realized_r, realized_usd=realized_usd)
    full = _reload(conn, pos["id"])
    if bt_conn is not None:
        st.writeback_trading_signals(bt_conn, full)
    if rev_exit_px is not None:
        trade_report.report_close(client, cfg, full, reason="reversed", exit_px=rev_exit_px,
                                  realized_r=realized_r, tag=_TAG)
    _alert(cfg, conn, f"🔄 <b>TERS SİNYAL</b> · <b>{sym}</b> #{pos['id']}\n"
                      f"{str(pos['direction']).upper()} kapatıldı ({realized_usd:+.2f}$"
                      + (f", {realized_r:+.2f}R" if realized_r is not None else "")
                      + ") → ters yön açılıyor" + f" — {_TAG}", kind="exit")


def _close(conn, bt_conn, pos, *, reason, exit_px, realized_r, client=None, cfg=None):
    """Finalize a position in the DB (the MARKET close was already fired by the caller) and
    upsert the result to trading_signals. realized_usd = R × the position's $ risk (risk_eff×qty).

    client/cfg verilirse Telegram'a kapanış raporu (grafik + Binance'ten net ROI) gönderilir —
    tamamen best-effort, hatası yutulur ve emir yönetimini ETKİLEMEZ."""
    risk_eff = abs(float(pos.get("eff_entry") or pos["signal_entry"]) - float(pos["signal_sl"]))
    realized_usd = (realized_r * risk_eff * float(pos.get("qty") or 0)) if realized_r is not None else None
    st.patch(conn, pos["id"], state=st.CLOSED, exit_reason=reason, exit_px=exit_px,
             exit_time=pd.Timestamp.now(tz="UTC"), realized_r=realized_r, realized_usd=realized_usd)
    full = _reload(conn, pos["id"])
    if bt_conn is not None:
        st.writeback_trading_signals(bt_conn, full)
    if client is not None and cfg is not None:
        trade_report.report_close(client, cfg, full, reason=reason, exit_px=exit_px,
                                  realized_r=realized_r, tag=_TAG)


# ------------------------------------------------------------------ reconcile
def _order_filled(client, sym, coid) -> dict | None:
    if not coid:
        return None
    try:
        o = client.get_order(sym, client_order_id=coid)
    except BinanceError:
        return None
    return o if o.get("status") == "FILLED" else None


def _position_amt(client, sym) -> float:
    for p in client.position_risk(sym):
        if p.get("symbol") == sym:
            return float(p.get("positionAmt", 0) or 0)
    return 0.0


def _reconcile(cfg, client, conn, bt_conn, xi, pos: dict, now: pd.Timestamp,
               shared: SharedTick | None = None) -> None:
    fetch_1m = shared.fetch_1m if shared is not None else tsc.fetch_1m
    sym = pos["symbol"]
    state = pos["state"]
    lv = lvl.compute_levels(pos["direction"], float(pos["signal_entry"]), float(pos["signal_sl"]),
                            entry_mode=pos["entry_mode"], confirm_buf=cfg.confirm_buf,
                            first_r=cfg.first_r, close_frac=cfg.close_frac,
                            runner_cap_r=cfg.runner_cap_r)
    _ctx = pos.get("context")
    if isinstance(_ctx, str):
        try:
            _ctx = json.loads(_ctx)
        except (ValueError, TypeError):
            _ctx = {}
    exch_tp = bool((_ctx or {}).get("exch_tp"))   # hybrid: TP1+cap rest as exchange LIMIT orders

    # Exchange truth wins: if we believe we're holding but Binance is flat, the position was closed
    # outside our path (manual, liquidation, or a stale flatten) — finalize from userTrades instead
    # of looping on -4003 trying to close 0 qty.
    if state in (st.OPEN_FULL, st.RUNNER) and _position_amt(client, sym) == 0:
        _reconcile_to_closed(cfg, client, conn, bt_conn, pos, now)
        return

    if state in (st.PENDING_ENTRY, st.ENTRY_WORKING):
        # Position is created ONLY after the breakout confirmed (favourable +0.5R before adverse),
        # so the entry trigger is already satisfied -> MARKET in now. Guard against chasing: if price
        # has already run to/over the +1R TP1 level, skip (a 2-min-late confirm shouldn't buy the top).
        last = _last_price(sym, now, shared)
        if last is not None:
            lngd = lv.sign
            if (last - lv.eff_entry) * lngd >= lv.risk_eff:      # already at/over +1R from entry
                st.patch(conn, pos["id"], state=st.CANCELLED, exit_reason="slipped")
                _alert(cfg, conn, f"⏭️ <b>ATLANDI</b> · <b>{sym}</b> {str(pos['direction']).upper()} #{pos['id']}\n"
                                  f"fiyat +1R'yi geçti (geç onay) — giriş yapılmadı — {_TAG}", kind="entry")
                return
        # Auto-leverage (risk-safe): set the per-trade leverage from the SL distance so the
        # liquidation sits ~2x the SL distance beyond entry (1/L ≈ 2*SL%) — liquidation can NEVER
        # precede the −1R stop, so the loss stays $risk_usd. Capped at leverage_max. Risk is fixed
        # by the qty (risk_usd/|entry−sl|); leverage only sets the margin + liquidation distance.
        lev = cfg.leverage
        if cfg.armed and cfg.auto_leverage:
            slpct = (abs(lv.eff_entry - lv.sl) / lv.eff_entry) if lv.eff_entry else 0.0
            if slpct > 0:
                lev = max(1, min(cfg.leverage_max, int(0.5 / slpct)))
            try:
                client.set_leverage(sym, lev)
            except Exception as e:  # noqa: BLE001
                _alert(cfg, conn, f"⚠️ <b>{sym}</b> set_leverage({lev}) hata: {e} — {cfg.leverage}x'e düşüldü",
                       kind="system")
                lev = cfg.leverage
        resp = _market(client, conn, pos, pos["qty"], leg="entry", reduce_only=False)
        avg = _avg_fill(client, sym, resp) or float(lv.eff_entry)
        rl = lvl.reanchor(lv, avg, first_r=cfg.first_r)
        st.patch(conn, pos["id"], state=st.OPEN_FULL, entry_fill_time=now, entry_fill_px=avg, leverage=lev,
                 eff_entry=avg, eff_tp1=rl.tp1, eff_be=rl.be, entry_coid=st.coid(pos["id"], "entry"),
                 entry_order_id=resp.get("orderId"), time_stop_at=now + pd.Timedelta(days=cfg.horizon_days))
        # Full exchange-side bracket at entry (mainnet): algo SL (real conditional) + resting LIMIT
        # TP1/cap. Marking exch_tp makes the reconciler run the SL-backstop branch (no synthetic TP
        # double-book — the LIMITs book the profit). All no-ops on testnet (keeps the synthetic model).
        _place_protective_stop(cfg, client, conn, xi, pos, rl.sl, leg="sl_rest")   # algo STOP_MARKET @ −1R
        _place_tp_algos(cfg, client, conn, xi, pos, rl)                             # algo TAKE_PROFIT_MARKET TP1 60% + cap 40%
        if not cfg.testnet:
            _ctx = pos.get("context") or {}
            if isinstance(_ctx, str):
                try:
                    _ctx = json.loads(_ctx)
                except (ValueError, TypeError):
                    _ctx = {}
            st.patch(conn, pos["id"], context={**_ctx, "exch_tp": True})
        _alert(cfg, conn, f"✅ <b>GİRİŞ</b> · <b>{sym}</b> {str(pos['direction']).upper()} #{pos['id']}\n"
                          f"giriş {avg:g} · {float(pos['qty']):g} adet (${float(pos['qty'])*avg:.0f}) · risk ${cfg.risk_usd:g} · {lev}x{' (oto)' if cfg.auto_leverage else ''}\n"
                          f"SL {rl.sl:g} (−1R) · TP1 {rl.tp1:g} (%{int(cfg.close_frac*100)}) · cap {rl.cap:g} (+{cfg.runner_cap_r:g}R %{int((1-cfg.close_frac)*100)}) — borsa bracket — {_TAG}",
               kind="entry")
        return

    if state in (st.OPEN_FULL, st.RUNNER) and exch_tp:
        # Exchange-side bracket: SL + TP1 + cap rest as algo orders on the book. The reconciler:
        #   (1) when TP1 books (position drops toward the runner) -> trail the SL to BREAKEVEN once
        #       (cancel the −1R algo SL, leave the TPs, place a BE algo SL), so the runner can't lose;
        #   (2) runs a SYNTHETIC SL as a pure backstop (the algo SL is primary). A full close (both
        #       TPs, or the SL) is caught by the flat guard above -> _reconcile_to_closed (real R).
        rl = lvl.reanchor(lv, float(pos["eff_entry"]), first_r=cfg.first_r)
        short = str(pos["direction"]).lower() == "short"
        e = float(pos["eff_entry"])
        be_done = bool((_ctx or {}).get("be_done"))
        cur = abs(_position_amt(client, sym))
        if cur > 0 and not be_done and cur < float(pos["qty"]) * 0.9:    # TP1 filled -> SL -> breakeven
            for o in client.open_algo_orders(sym):              # cancel the −1R SL (adverse side); keep the TPs
                trig = float(o.get("triggerPrice") or 0)
                if ((trig > e) if short else (trig < e)) and o.get("algoId") is not None:
                    try:
                        client.cancel_algo_order(algo_id=o["algoId"])
                    except BinanceError:
                        pass
            _place_protective_stop(cfg, client, conn, xi, pos, e, leg="be_rest")   # algo BE stop @ entry
            # -> RUNNER so the dashboard badge reads "TP1 sonrası" (the exch_tp branch now also matches
            # RUNNER); tp1_fill_time anchors the post-BE backstop scan so the entry bar can't false-trigger.
            st.patch(conn, pos["id"], state=st.RUNNER, tp1_fill_time=now,
                     context={**(_ctx or {}), "be_done": True})
            _alert(cfg, conn, f"🎯 <b>TP1 DOLDU</b> · <b>{sym}</b> {str(pos['direction']).upper()} #{pos['id']}\n"
                              f"%{int(cfg.close_frac*100)} alındı @ {rl.tp1:g} (+1R · +{cfg.close_frac*cfg.first_r:.1f}R kilitli)\n"
                              f"SL → breakeven {e:g} · runner %{int((1-cfg.close_frac)*100)} → +{cfg.runner_cap_r:g}R / BE / {cfg.horizon_days}g — {_TAG}",
                   kind="milestone")
            return
        sl_level = e if be_done else rl.sl                       # backstop fires at BE once trailed
        since = (pd.Timestamp(pos["tp1_fill_time"]) if be_done and pos.get("tp1_fill_time")
                 else pd.Timestamp(pos["entry_fill_time"]))
        df1m = fetch_1m(sym, since - pd.Timedelta(minutes=2), now)
        sl_hit = (df1m is not None and not df1m.empty
                  and bool((df1m["high"] >= sl_level).any() if short else (df1m["low"] <= sl_level).any()))
        if sl_hit:                                               # backstop close (algo SL should have fired first)
            _cancel_resting(cfg, client, sym)
            _market(client, conn, pos, abs(_position_amt(client, sym)), leg="sl")
            _reconcile_to_closed(cfg, client, conn, bt_conn, pos, now)
            _alert(cfg, conn, f"🛑 <b>{'BREAKEVEN STOP' if be_done else 'STOP −1R'}</b> · <b>{sym}</b> "
                              f"{str(pos['direction']).upper()} #{pos['id']}\n"
                              f"sentetik backstop kapanışı @ {sl_level:g} — {_TAG}", kind="exit")
            return
        _maybe_time_stop(cfg, client, conn, bt_conn, sym, pos, now, shared)
        return

    if state == st.OPEN_FULL:
        rl = lvl.reanchor(lv, float(pos["eff_entry"]), first_r=cfg.first_r)
        df1m = fetch_1m(sym, pd.Timestamp(pos["entry_fill_time"]) - pd.Timedelta(minutes=2), now)
        hit, _ts, _px = _scan(df1m, pos["entry_fill_time"], pos["direction"], rl.sl, rl.tp1)
        if hit == "protect":                                    # −1R full stop
            _market(client, conn, pos, abs(_position_amt(client, sym)), leg="sl")
            _cancel_resting(cfg, client, sym)
            _close(conn, bt_conn, pos, reason="sl", exit_px=rl.sl, realized_r=-1.0 - _fee_r(cfg, pos),
                   client=client, cfg=cfg)
            _alert(cfg, conn, f"🛑 <b>{sym}</b> stopped −1R — {_TAG}", kind="exit")
            return
        if hit == "target":                                     # +1R -> book 60%, ride runner
            _market(client, conn, pos, pos["tp1_qty"], leg="tp1")
            _cancel_resting(cfg, client, sym)                   # full-position −1R stop no longer valid (40% left)
            runner_qty = xi.floor_qty(sym, abs(_position_amt(client, sym)))
            if runner_qty <= 0:
                _close(conn, bt_conn, pos, reason="tp1_be", exit_px=rl.tp1,
                       realized_r=cfg.close_frac * cfg.first_r - _fee_r(cfg, pos),
                       client=client, cfg=cfg)
                return
            st.patch(conn, pos["id"], state=st.RUNNER, runner_qty=runner_qty,
                     tp1_fill_time=now, tp1_fill_px=rl.tp1)
            _place_protective_stop(cfg, client, conn, xi, pos, rl.be, leg="be_rest")   # runner protected at breakeven
            _alert(cfg, conn, f"🎯 <b>{sym}</b> TP1 +1R, booked {int(cfg.close_frac*100)}% "
                              f"({pos['tp1_qty']}) — runner {runner_qty} to +{cfg.runner_cap_r:g}R/BE",
                   kind="milestone")
            return
        _maybe_time_stop(cfg, client, conn, bt_conn, sym, pos, now, shared)
        return

    if state == st.RUNNER:
        be, cap = float(pos["eff_be"]), float(pos["eff_cap"])
        df1m = fetch_1m(sym, pd.Timestamp(pos["tp1_fill_time"]) - pd.Timedelta(minutes=2), now)
        hit, _ts, _px = _scan(df1m, pos["tp1_fill_time"], pos["direction"], be, cap)
        if hit == "protect":                                    # back to breakeven -> runner 0R
            _market(client, conn, pos, abs(_position_amt(client, sym)), leg="be")
            _cancel_resting(cfg, client, sym)
            _close(conn, bt_conn, pos, reason="breakeven", exit_px=be,
                   realized_r=cfg.close_frac * cfg.first_r - _fee_r(cfg, pos),
                   client=client, cfg=cfg)
            _alert(cfg, conn, f"🏁 <b>{sym}</b> runner breakeven (+{cfg.close_frac*cfg.first_r:.1f}R) — {_TAG}",
                   kind="exit")
            return
        if hit == "target":                                     # runner ran to +cap
            _market(client, conn, pos, abs(_position_amt(client, sym)), leg="cap")
            _cancel_resting(cfg, client, sym)
            r = cfg.close_frac * cfg.first_r + (1 - cfg.close_frac) * cfg.runner_cap_r - _fee_r(cfg, pos)
            _close(conn, bt_conn, pos, reason="cap", exit_px=cap, realized_r=r, client=client, cfg=cfg)
            _alert(cfg, conn, f"🏁 <b>{sym}</b> runner CAP +{cfg.runner_cap_r:g}R ({r:+.2f}R) — {_TAG}",
                   kind="exit")
            return
        _maybe_time_stop(cfg, client, conn, bt_conn, sym, pos, now, shared)
        return


def _last_price(sym, now, shared: SharedTick | None = None) -> float | None:
    try:
        fetch = shared.fetch_1m if shared is not None else tsc.fetch_1m
        d = fetch(sym, now - pd.Timedelta(minutes=5), now)
        return float(d["close"].iloc[-1]) if d is not None and not d.empty else None
    except Exception:  # noqa: BLE001
        return None


def _maybe_time_stop(cfg, client, conn, bt_conn, sym, pos, now: pd.Timestamp,
                     shared: SharedTick | None = None) -> None:
    ts_at = pos.get("time_stop_at")
    if not ts_at:
        return
    if now < pd.Timestamp(ts_at).tz_convert("UTC"):
        return
    # 3-day limit: MARKET-close the residual (mark-to-market), same R math as resolve_scaleout.
    amt = _position_amt(client, sym)
    if amt:
        _market(client, conn, pos, abs(amt), leg="time")
    _cancel_resting(cfg, client, sym)
    last = _last_price(sym, now, shared)
    risk = abs(float(pos["eff_entry"] or pos["signal_entry"]) - float(pos["signal_sl"]))
    sign = 1 if str(pos["direction"]).lower() == "long" else -1
    booked = cfg.close_frac * cfg.first_r if pos["state"] == st.RUNNER else 0.0
    runner_r = ((last - float(pos["eff_entry"])) * sign / risk) if (last and risk) else 0.0
    frac = (1 - cfg.close_frac) if pos["state"] == st.RUNNER else 1.0
    r = booked + frac * max(runner_r, 0.0) - _fee_r(cfg, pos)
    _close(conn, bt_conn, pos, reason="time_stop", exit_px=last, realized_r=r, client=client, cfg=cfg)
    _alert(cfg, conn, f"⏱️ <b>3 GÜN DOLDU</b> · <b>{sym}</b> {str(pos['direction']).upper()} #{pos['id']}\n"
                      f"süre limiti — market kapandı @ {last:g} · realized {r:+.2f}R — {_TAG}", kind="exit")


def _fee_r(cfg, pos: dict) -> float:
    from ict import config as C
    risk = abs(float(pos.get("eff_entry") or pos["signal_entry"]) - float(pos["signal_sl"]))
    entry = float(pos.get("eff_entry") or pos["signal_entry"])
    return C.FEE_PCT_PER_SIDE * (2 * entry) / risk if risk else 0.0


def _reload(conn, pos_id: int) -> dict:
    cur = conn.cursor()
    cur.execute("SELECT * FROM ict_trade.live_positions WHERE id = %s", (pos_id,))
    cols = [d[0] for d in cur.description]
    row = dict(zip(cols, cur.fetchone()))
    cur.close()
    return row


def _write_snapshot(cfg, client, conn) -> None:
    """Snapshot the REAL exchange state into ict_trade.live_account(_snapshot) so the dashboard
    can show live mark / unrealized PnL / wallet without the browser ever signing a request.
    Read-only on Binance; runs whenever credentials exist (even dry-run/halted). Non-fatal.
    DUAL-MODE like state.py: legacy (user_id None) keeps the original (network)/(symbol) keys;
    multi-user targets the 005b per-user composite PKs."""
    net = _net(cfg)
    uid = cfg.user_id
    cur = conn.cursor()
    try:
        acc = client.account()
        acc_vals = (float(acc.get("totalWalletBalance", 0) or 0),
                    float(acc.get("availableBalance", 0) or 0),
                    float(acc.get("totalUnrealizedProfit", 0) or 0), bool(acc.get("canTrade", False)))
        if uid is None:
            cur.execute("""
                INSERT INTO ict_trade.live_account
                  (network, wallet_balance, available_balance, total_unrealized, can_trade, updated_at)
                VALUES (%s,%s,%s,%s,%s, current_timestamp)
                ON CONFLICT (network) DO UPDATE SET
                  wallet_balance=EXCLUDED.wallet_balance, available_balance=EXCLUDED.available_balance,
                  total_unrealized=EXCLUDED.total_unrealized, can_trade=EXCLUDED.can_trade,
                  updated_at=current_timestamp
            """, (net,) + acc_vals)
        else:
            cur.execute("""
                INSERT INTO ict_trade.live_account
                  (user_id, network, wallet_balance, available_balance, total_unrealized, can_trade, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s, current_timestamp)
                ON CONFLICT (user_id, network) DO UPDATE SET
                  wallet_balance=EXCLUDED.wallet_balance, available_balance=EXCLUDED.available_balance,
                  total_unrealized=EXCLUDED.total_unrealized, can_trade=EXCLUDED.can_trade,
                  updated_at=current_timestamp
            """, (uid, net) + acc_vals)
        # per-symbol: every enabled symbol + anything currently holding a position
        want = set(cfg.symbols)
        entry_times = _open_entry_times(conn, want, uid, net if uid else None)
        for r in client.position_risk():
            sym = r.get("symbol")
            amt = float(r.get("positionAmt", 0) or 0)
            if sym not in want and amt == 0:
                continue
            # funding paid/received on the OPEN position (flat symbols carry none)
            funding = _funding_since(client, sym, entry_times.get(sym)) if amt != 0 else 0.0
            row_vals = (amt, float(r.get("entryPrice", 0) or 0),
                        float(r.get("markPrice", 0) or 0), float(r.get("unRealizedProfit", 0) or 0),
                        int(float(r.get("leverage", 0) or 0)), funding)
            if uid is None:
                cur.execute("""
                    INSERT INTO ict_trade.live_account_snapshot
                      (symbol, network, position_amt, entry_price, mark_price, unrealized_pnl, leverage, funding_fee, updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s, current_timestamp)
                    ON CONFLICT (symbol) DO UPDATE SET
                      network=EXCLUDED.network, position_amt=EXCLUDED.position_amt,
                      entry_price=EXCLUDED.entry_price, mark_price=EXCLUDED.mark_price,
                      unrealized_pnl=EXCLUDED.unrealized_pnl, leverage=EXCLUDED.leverage,
                      funding_fee=EXCLUDED.funding_fee, updated_at=current_timestamp
                """, (sym, net) + row_vals)
            else:
                cur.execute("""
                    INSERT INTO ict_trade.live_account_snapshot
                      (user_id, symbol, network, position_amt, entry_price, mark_price, unrealized_pnl, leverage, funding_fee, updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, current_timestamp)
                    ON CONFLICT (user_id, network, symbol) DO UPDATE SET
                      position_amt=EXCLUDED.position_amt,
                      entry_price=EXCLUDED.entry_price, mark_price=EXCLUDED.mark_price,
                      unrealized_pnl=EXCLUDED.unrealized_pnl, leverage=EXCLUDED.leverage,
                      funding_fee=EXCLUDED.funding_fee, updated_at=current_timestamp
                """, (uid, sym, net) + row_vals)
        conn.commit()
    except (BinanceError, Exception) as e:  # noqa: BLE001
        conn.rollback()
        print(f"  [snapshot] skipped: {e}")
    finally:
        cur.close()


# ------------------------------------------------------------------ per-user tick
def _run_tick(cfg, user, live, bt, shared: SharedTick, now: pd.Timestamp) -> None:
    """One full executor pass for ONE account (cfg carries the account's keys/knobs/identity).
    user is the ExecUser row (None = legacy env account). Everything market-data-shaped goes
    through `shared` so N accounts don't multiply the per-IP Binance weight."""
    armed = cfg.armed
    uid = cfg.user_id
    net = _net(cfg)
    label = cfg.user_email or "env"
    sym_filter = cfg.symbols if uid is None else None      # user mode reconciles ALL their rows
    bt_conn = bt if cfg.is_canonical else None             # writeback = canonical/owner only

    client = _client(cfg)
    try:
        off = shared.sync_client(client)
        xi = shared.xi_for(client)
    except BinanceError as e:
        print(f"  [{label}] fatal exchangeInfo/time: {e}")
        return
    print(f"  [{label}/{net}] offset {off:+d}ms | risk=${cfg.risk_usd:g} | "
          f"max {cfg.max_concurrent} pos / ${cfg.max_total_risk_usd:g} | {list(cfg.symbols)}", flush=True)

    # ---- kill switch: flatten everything, drop the flag, disable — nothing else this tick
    if user is not None and user.kill_requested:
        n = 0
        if armed:
            try:
                n = ks.flatten_positions(cfg, client, live, user_id=uid, network=net, reason="killswitch")
            except Exception as e:  # noqa: BLE001
                print(f"  [{label}] kill flatten error: {e}")
        ustore.clear_kill(live, user.settings_id)
        ustore.audit(live, uid, "kill_executed", {"stream": "opus", "network": net, "flattened": n})
        _alert(cfg, live, f"🟥 <b>ACİL DURDUR</b> · {n} pozisyon kapatıldı, OPUS/{net} devre dışı bırakıldı — {_TAG}",
               title="Acil durdurma tamamlandı", kind="system")
        return

    # ---- entry gates: activation + daily loss cap (reconcile ALWAYS continues below)
    entries_ok = armed and (user is None or user.entries_allowed)
    if entries_ok and user is not None and user.daily_loss_cap_usd:
        lost = ustore.realized_today_usd(live, uid, net, "opus")
        if lost <= -float(user.daily_loss_cap_usd):
            entries_ok = False
            if not ustore.daily_pause_notified(live, uid, "opus"):
                ustore.audit(live, uid, "daily_loss_pause",
                             {"stream": "opus", "network": net, "lost_usd": lost,
                              "cap_usd": user.daily_loss_cap_usd})
                _alert(cfg, live, f"⛔ Günlük zarar limiti aşıldı ({lost:+.2f}$ ≤ −{user.daily_loss_cap_usd:g}$) — "
                                  f"bugün yeni işlem açılmayacak. Açık pozisyonlar yönetilmeye devam ediyor.",
                       title="Günlük zarar limiti", kind="system")

    # 1) NEW signals -> intents (dry) / positions (armed)
    sigs = [s for s in shared.signals(live) if s["symbol"] in set(cfg.symbols)]
    # One position per symbol (Binance one-way mode NETS all orders for a symbol into ONE position,
    # so independent same-symbol pyramiding is impossible). open_by_sym = the currently-open row per
    # symbol; a SAME-direction new signal is ignored, an OPPOSITE one REVERSES (close + flip).
    open_by_sym = ({p["symbol"]: p for p in st.fetch_open(live, sym_filter, user_id=uid, network=net if uid else None)}
                   if armed else {})
    managed = set(open_by_sym)
    print(f"  [{label}] {len(sigs)} recent dch30_4h signal(s) in window")
    for sig in sigs:
        sym = sig["symbol"]
        lv = _levels_for(cfg, sig)
        qty, tp1q, skip = _size_and_screen(cfg, xi, sig, lv)
        gate, _ = shared.gate_for(cfg, sig)
        if skip:
            print(f"  · {sym:<9} SKIP: {skip}")
            continue
        if not armed:
            intent = _intent_dict(cfg, sig, lv, qty, tp1q, gate, xi)
            print(f"  · {sym:<9} {sig['direction'].upper():<5} gate={gate}  INTENT:")
            print("    " + json.dumps(intent, default=str))
            continue
        if not entries_ok:
            continue                                        # disabled/drain/loss-capped: manage only
        # armed: only act on a CONFIRMED breakout (matches the backtest's confirmed-only rows)
        if gate != "confirmed":
            continue
        existing = open_by_sym.get(sym)
        if existing is not None:
            if (existing["direction"] or "").upper() == sig["direction"].upper():
                continue                                    # same direction -> no pyramiding
            try:                                            # opposite -> reverse (close, then open new)
                _reverse_close(cfg, client, live, bt_conn, existing, now)
            except BinanceError as e:
                print(f"  ! {sym} reverse-close error: {e}")
                continue
            open_by_sym.pop(sym, None)
            managed.discard(sym)
            print(f"  ↺ {sym:<9} ters sinyal -> mevcut {existing['direction']} kapatıldı (reversed)")
        elif sym in managed:
            continue                                        # created earlier this run
        if len(managed) >= cfg.max_concurrent:
            print(f"  · {sig['symbol']:<9} SKIP: MAX_CONCURRENT {cfg.max_concurrent} reached")
            continue
        if (st.total_open_risk_usd(live, cfg.risk_usd, user_id=uid, network=net if uid else None)
                + cfg.risk_usd > cfg.max_total_risk_usd):
            print(f"  · {sig['symbol']:<9} SKIP: MAX_TOTAL_RISK_USD {cfg.max_total_risk_usd} reached")
            continue
        _ensure_account(cfg, client, sig["symbol"])
        fire = pd.Timestamp(sig["signal_time"]).tz_convert("UTC") + pd.Timedelta(minutes=LTF_MIN)
        pos_id = st.create_position(
            live, symbol=sig["symbol"], signal_time=pd.Timestamp(sig["signal_time"]),
            direction=sig["direction"], side=_side(sig["direction"]), entry_mode=cfg.entry_mode,
            lv=lv, qty=qty, tp1_qty=tp1q, leverage=cfg.leverage,
            entry_deadline=fire + pd.Timedelta(minutes=cfg.expiry_min),
            context={"strategy": sig.get("strategy")},
            user_id=uid, network=net if uid else None)
        if pos_id is None:
            continue
        managed.add(sig["symbol"])
        print(f"  + {sig['symbol']:<9} {sig['direction'].upper():<5} position {pos_id} created (gate=confirmed)")

    # 2) reconcile open positions
    if armed:
        for pos in st.fetch_open(live, sym_filter, user_id=uid, network=net if uid else None):
            try:
                _reconcile(cfg, client, live, bt_conn, xi, pos, now, shared)
            except BinanceError as e:
                print(f"  ! {pos['symbol']} reconcile error: {e}")
                if e.code == -2019 and pos["state"] in (st.PENDING_ENTRY, st.ENTRY_WORKING):
                    context = pos.get("context") or {}
                    if isinstance(context, str):
                        try:
                            context = json.loads(context)
                        except (ValueError, TypeError):
                            context = {}
                    attempts = int(context.get("margin_insufficient_attempts", 0)) + 1
                    context["margin_insufficient_attempts"] = attempts
                    exhausted = attempts >= MAX_MARGIN_RETRIES
                    fields = {"context": context}
                    if exhausted:
                        fields.update(state=st.CANCELLED, exit_reason="margin_insufficient")
                    st.patch(live, pos["id"], **fields)
                    suffix = (f" · deneme {attempts}/{MAX_MARGIN_RETRIES}; bakiye yetersizliği nedeniyle sinyal iptal edildi, "
                              "bu pozisyon için tekrar denenmeyecek." if exhausted else
                              f" · deneme {attempts}/{MAX_MARGIN_RETRIES}")
                    _alert(cfg, live, f"⚠️ <b>{pos['symbol']}</b> reconcile error: {e}{suffix}", kind="system")
                else:
                    _alert(cfg, live, f"⚠️ <b>{pos['symbol']}</b> reconcile error: {e}", kind="system")

    # 3) snapshot the real exchange state for the dashboard (read-only; needs only credentials)
    if cfg.api_key and cfg.api_secret:
        _write_snapshot(cfg, client, live)
        print(f"  [{label}] snapshot written ({net})")


# ------------------------------------------------------------------ main
def main():
    base = cfgmod.load_cfg()
    now = pd.Timestamp.now(tz="UTC")
    head = ("ARMED (LIVE ORDERS)" if base.armed else
            ("DRY-RUN (no orders)" if base.dry_run else "HALTED (LIVE_TRADING_ENABLED=false)"))
    print(f"=== {_TAG} executor @ {now:%Y-%m-%d %H:%M}Z | {head} | mode={base.entry_mode} "
          f"cap={base.runner_cap_r:g}R | {'MULTI-USER' if base.multi_user else 'single (env)'} ===", flush=True)

    if not base.trading_enabled and not base.dry_run:
        print("[halt] LIVE_TRADING_ENABLED=false and not a dry-run — no-op.")
        return

    live = tsc.live_conn()
    bt = tsc.backtest_conn() if base.armed else None
    shared = SharedTick(now)

    if base.multi_user:
        try:
            users = ustore.load_exec_users(live, "opus")
        except Exception as e:  # noqa: BLE001
            print(f"[fatal] load_exec_users: {e}")
            notify.alert(f"⚠️ {_TAG} executor: kullanıcılar yüklenemedi: {e}", chat_id=base.telegram_chat_id)
            live.close()
            return
        print(f"  {len(users)} exec user-network row(s) loaded")
        for u in users:
            try:
                _run_tick(cfgmod.cfg_for_user(base, u), u, live, bt, shared, now)
            except Exception as e:  # noqa: BLE001 — one user can NEVER break another's reconcile
                print(f"  ! user {u.email}/{u.network} tick error: {e}")
                notify.alert(f"⚠️ {_TAG} exec kullanıcı hatası · {u.email}/{u.network}: {e}",
                             chat_id=base.telegram_chat_id)
                try:
                    live.rollback()
                except Exception:  # noqa: BLE001
                    pass
    else:
        _run_tick(base, None, live, bt, shared, now)

    live.close()
    if bt:
        bt.close()
    print("  done.")


if __name__ == "__main__":
    main()
