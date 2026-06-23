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

import sys
import json
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent))               # sync/live_exec
sys.path.insert(0, str(_HERE.parents[1]))           # sync/
import _bootenv                                      # noqa: E402,F401  -- MUST precede tsc/scaleout/ict.config
import trade_sync_common as tsc                      # noqa: E402
import config as cfgmod                              # noqa: E402
import state as st                                   # noqa: E402
import levels as lvl                                 # noqa: E402
import sizing                                        # noqa: E402
import notify                                        # noqa: E402
from binance_futures import BinanceFutures, BinanceError   # noqa: E402
from exchange_info import ExchangeInfo               # noqa: E402

LTF_MIN = 30                                         # dch30_4h base timeframe
MODE = "dch30_4h"
NEW_SIGNAL_LOOKBACK_MIN = tsc.EXPIRY_MINUTES + 60    # window to scan for not-yet-managed signals


# ------------------------------------------------------------------ wiring
def _client(cfg) -> BinanceFutures:
    c = BinanceFutures(api_key=cfg.api_key, api_secret=cfg.api_secret,
                       base_url=cfg.base_url, proxy=cfg.proxy)
    return c


def _load_exchange_info(cfg, client) -> ExchangeInfo:
    """exchangeInfo is PUBLIC — works in dry-run without API keys."""
    return ExchangeInfo(client.exchange_info())


def _ensure_account(cfg, client, symbol: str) -> None:
    """Idempotent per-symbol account setup (armed only): leverage + isolated margin."""
    if not cfg.armed:
        return
    client.set_margin_type(symbol, cfg.margin_type)
    client.set_leverage(symbol, cfg.leverage)


# ------------------------------------------------------------------ signal read
def _read_recent_signals(cfg, live_conn, now: pd.Timestamp) -> list[dict]:
    """dch30_4h live signals whose bar opened within the new-signal lookback, for our symbols."""
    w_start = now - pd.Timedelta(minutes=NEW_SIGNAL_LOOKBACK_MIN + LTF_MIN)
    cur = live_conn.cursor()
    cur.execute("""
        SELECT symbol, signal_time, direction, entry, sl, tp, strategy
        FROM ict_trade.signals
        WHERE mode = %s AND signal_time >= %s AND symbol = ANY(%s)
        ORDER BY symbol, signal_time
    """, (MODE, w_start.to_pydatetime(), list(cfg.symbols)))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return rows


def _levels_for(cfg, sig: dict) -> lvl.Levels:
    return lvl.compute_levels(
        sig["direction"], float(sig["entry"]), float(sig["sl"]),
        entry_mode=cfg.entry_mode, confirm_buf=cfg.confirm_buf, first_r=cfg.first_r,
        close_frac=cfg.close_frac, runner_cap_r=cfg.runner_cap_r)


def _confirm_status(cfg, sig: dict, now: pd.Timestamp) -> tuple[str, pd.DataFrame | None]:
    """'confirmed' | 'pending' | 'reversed' for one signal, from 1m since the bar close.
    confirmed = favourable +buf*risk printed before adverse −buf*risk within the window."""
    fire = pd.Timestamp(sig["signal_time"]).tz_convert("UTC") + pd.Timedelta(minutes=LTF_MIN)
    df1m = tsc.fetch_1m(sig["symbol"], fire - pd.Timedelta(minutes=2), now)
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
                 client_order_id=coid, order_id=resp.get("orderId"), payload=resp)
    return resp


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


def _reconcile_to_closed(cfg, client, conn, bt_conn, pos, now) -> None:
    """Binance is flat but DB still shows the position open — finalize from exchange truth
    (realizedPnl since entry), so the reconciler stops looping and the record is accurate."""
    sym = pos["symbol"]
    realized_usd = _realized_since(client, sym, pos.get("entry_fill_time"))
    risk_eff = abs(float(pos.get("eff_entry") or pos["signal_entry"]) - float(pos["signal_sl"]))
    denom = risk_eff * float(pos.get("qty") or 0)
    realized_r = (realized_usd / denom) if denom else None
    st.patch(conn, pos["id"], state=st.CLOSED, exit_reason="closed_externally",
             exit_time=now, realized_r=realized_r, realized_usd=realized_usd)
    if bt_conn is not None:
        st.writeback_trading_signals(bt_conn, _reload(conn, pos["id"]))
    notify.alert(f"⚠️ <b>{sym}</b> borsada kapanmış (DB senkronlandı) — "
                 f"realized {realized_usd:+.2f}$ ({realized_r:+.2f}R) — {st.VERSION}" if realized_r is not None
                 else f"⚠️ <b>{sym}</b> borsada kapanmış (DB senkronlandı) — {st.VERSION}",
                 chat_id=cfg.telegram_chat_id)


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
    realized_usd = _realized_since(client, sym, pos.get("entry_fill_time"))
    risk_eff = abs(float(pos.get("eff_entry") or pos["signal_entry"]) - float(pos["signal_sl"]))
    denom = risk_eff * float(pos.get("qty") or 0)
    realized_r = (realized_usd / denom) if denom else None
    st.patch(conn, pos["id"], state=st.CLOSED, exit_reason="reversed", exit_time=now,
             exit_px=_last_price(sym, now), realized_r=realized_r, realized_usd=realized_usd)
    if bt_conn is not None:
        st.writeback_trading_signals(bt_conn, _reload(conn, pos["id"]))
    notify.alert(f"🔄 <b>{sym}</b> ters sinyal → {pos['direction']} kapatıldı "
                 f"({realized_usd:+.2f}$" + (f", {realized_r:+.2f}R" if realized_r is not None else "") + ") — {st.VERSION}",
                 chat_id=cfg.telegram_chat_id)


def _close(conn, bt_conn, pos, *, reason, exit_px, realized_r):
    """Finalize a position in the DB (the MARKET close was already fired by the caller) and
    upsert the result to trading_signals. realized_usd = R × the position's $ risk (risk_eff×qty)."""
    risk_eff = abs(float(pos.get("eff_entry") or pos["signal_entry"]) - float(pos["signal_sl"]))
    realized_usd = (realized_r * risk_eff * float(pos.get("qty") or 0)) if realized_r is not None else None
    st.patch(conn, pos["id"], state=st.CLOSED, exit_reason=reason, exit_px=exit_px,
             exit_time=pd.Timestamp.now(tz="UTC"), realized_r=realized_r, realized_usd=realized_usd)
    if bt_conn is not None:
        st.writeback_trading_signals(bt_conn, _reload(conn, pos["id"]))


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


def _reconcile(cfg, client, conn, bt_conn, xi, pos: dict, now: pd.Timestamp) -> None:
    sym = pos["symbol"]
    state = pos["state"]
    lv = lvl.compute_levels(pos["direction"], float(pos["signal_entry"]), float(pos["signal_sl"]),
                            entry_mode=pos["entry_mode"], confirm_buf=cfg.confirm_buf,
                            first_r=cfg.first_r, close_frac=cfg.close_frac,
                            runner_cap_r=cfg.runner_cap_r)

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
        last = _last_price(sym, now)
        if last is not None:
            lngd = lv.sign
            if (last - lv.eff_entry) * lngd >= lv.risk_eff:      # already at/over +1R from entry
                st.patch(conn, pos["id"], state=st.CANCELLED, exit_reason="slipped")
                notify.alert(f"⏭️ <b>{sym}</b> entry atlandı (fiyat +1R'yi geçti) — {st.VERSION}",
                             chat_id=cfg.telegram_chat_id)
                return
        resp = _market(client, conn, pos, pos["qty"], leg="entry", reduce_only=False)
        avg = _avg_fill(client, sym, resp) or float(lv.eff_entry)
        rl = lvl.reanchor(lv, avg, first_r=cfg.first_r)
        st.patch(conn, pos["id"], state=st.OPEN_FULL, entry_fill_time=now, entry_fill_px=avg,
                 eff_entry=avg, eff_tp1=rl.tp1, eff_be=rl.be, entry_coid=st.coid(pos["id"], "entry"),
                 entry_order_id=resp.get("orderId"), time_stop_at=now + pd.Timedelta(days=cfg.horizon_days))
        notify.alert(f"✅ <b>{sym}</b> {pos['direction']} entry @ {avg:g} (qty {pos['qty']}) — "
                     f"SL {rl.sl:g} TP1 {rl.tp1:g} cap {rl.cap:g} — {st.VERSION}", chat_id=cfg.telegram_chat_id)
        return

    if state == st.OPEN_FULL:
        rl = lvl.reanchor(lv, float(pos["eff_entry"]), first_r=cfg.first_r)
        df1m = tsc.fetch_1m(sym, pd.Timestamp(pos["entry_fill_time"]) - pd.Timedelta(minutes=2), now)
        hit, _ts, _px = _scan(df1m, pos["entry_fill_time"], pos["direction"], rl.sl, rl.tp1)
        if hit == "protect":                                    # −1R full stop
            _market(client, conn, pos, abs(_position_amt(client, sym)), leg="sl")
            _close(conn, bt_conn, pos, reason="sl", exit_px=rl.sl, realized_r=-1.0 - _fee_r(cfg, pos))
            notify.alert(f"🛑 <b>{sym}</b> stopped −1R — {st.VERSION}", chat_id=cfg.telegram_chat_id)
            return
        if hit == "target":                                     # +1R -> book 60%, ride runner
            _market(client, conn, pos, pos["tp1_qty"], leg="tp1")
            runner_qty = xi.floor_qty(sym, abs(_position_amt(client, sym)))
            if runner_qty <= 0:
                _close(conn, bt_conn, pos, reason="tp1_be", exit_px=rl.tp1,
                       realized_r=cfg.close_frac * cfg.first_r - _fee_r(cfg, pos))
                return
            st.patch(conn, pos["id"], state=st.RUNNER, runner_qty=runner_qty,
                     tp1_fill_time=now, tp1_fill_px=rl.tp1)
            notify.alert(f"🎯 <b>{sym}</b> TP1 +1R, booked {int(cfg.close_frac*100)}% "
                         f"({pos['tp1_qty']}) — runner {runner_qty} to +{cfg.runner_cap_r:g}R/BE",
                         chat_id=cfg.telegram_chat_id)
            return
        _maybe_time_stop(cfg, client, conn, bt_conn, sym, pos, now)
        return

    if state == st.RUNNER:
        be, cap = float(pos["eff_be"]), float(pos["eff_cap"])
        df1m = tsc.fetch_1m(sym, pd.Timestamp(pos["tp1_fill_time"]) - pd.Timedelta(minutes=2), now)
        hit, _ts, _px = _scan(df1m, pos["tp1_fill_time"], pos["direction"], be, cap)
        if hit == "protect":                                    # back to breakeven -> runner 0R
            _market(client, conn, pos, abs(_position_amt(client, sym)), leg="be")
            _close(conn, bt_conn, pos, reason="breakeven", exit_px=be,
                   realized_r=cfg.close_frac * cfg.first_r - _fee_r(cfg, pos))
            notify.alert(f"🏁 <b>{sym}</b> runner breakeven (+{cfg.close_frac*cfg.first_r:.1f}R) — {st.VERSION}",
                         chat_id=cfg.telegram_chat_id)
            return
        if hit == "target":                                     # runner ran to +cap
            _market(client, conn, pos, abs(_position_amt(client, sym)), leg="cap")
            r = cfg.close_frac * cfg.first_r + (1 - cfg.close_frac) * cfg.runner_cap_r - _fee_r(cfg, pos)
            _close(conn, bt_conn, pos, reason="cap", exit_px=cap, realized_r=r)
            notify.alert(f"🏁 <b>{sym}</b> runner CAP +{cfg.runner_cap_r:g}R ({r:+.2f}R) — {st.VERSION}",
                         chat_id=cfg.telegram_chat_id)
            return
        _maybe_time_stop(cfg, client, conn, bt_conn, sym, pos, now)
        return


def _last_price(sym, now) -> float | None:
    try:
        d = tsc.fetch_1m(sym, now - pd.Timedelta(minutes=5), now)
        return float(d["close"].iloc[-1]) if d is not None and not d.empty else None
    except Exception:  # noqa: BLE001
        return None


def _maybe_time_stop(cfg, client, conn, bt_conn, sym, pos, now: pd.Timestamp) -> None:
    ts_at = pos.get("time_stop_at")
    if not ts_at:
        return
    if now < pd.Timestamp(ts_at).tz_convert("UTC"):
        return
    # 3-day limit: MARKET-close the residual (mark-to-market), same R math as resolve_scaleout.
    amt = _position_amt(client, sym)
    if amt:
        _market(client, conn, pos, abs(amt), leg="time")
    last = _last_price(sym, now)
    risk = abs(float(pos["eff_entry"] or pos["signal_entry"]) - float(pos["signal_sl"]))
    sign = 1 if str(pos["direction"]).lower() == "long" else -1
    booked = cfg.close_frac * cfg.first_r if pos["state"] == st.RUNNER else 0.0
    runner_r = ((last - float(pos["eff_entry"])) * sign / risk) if (last and risk) else 0.0
    frac = (1 - cfg.close_frac) if pos["state"] == st.RUNNER else 1.0
    r = booked + frac * max(runner_r, 0.0) - _fee_r(cfg, pos)
    _close(conn, bt_conn, pos, reason="time_stop", exit_px=last, realized_r=r)
    notify.alert(f"⏱️ <b>{sym}</b> 3-day mark-to-market ({r:+.2f}R) — {st.VERSION}", chat_id=cfg.telegram_chat_id)


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
    Read-only on Binance; runs whenever credentials exist (even dry-run/halted). Non-fatal."""
    net = "testnet" if cfg.testnet else "mainnet"
    cur = conn.cursor()
    try:
        acc = client.account()
        cur.execute("""
            INSERT INTO ict_trade.live_account
              (network, wallet_balance, available_balance, total_unrealized, can_trade, updated_at)
            VALUES (%s,%s,%s,%s,%s, current_timestamp)
            ON CONFLICT (network) DO UPDATE SET
              wallet_balance=EXCLUDED.wallet_balance, available_balance=EXCLUDED.available_balance,
              total_unrealized=EXCLUDED.total_unrealized, can_trade=EXCLUDED.can_trade,
              updated_at=current_timestamp
        """, (net, float(acc.get("totalWalletBalance", 0) or 0),
              float(acc.get("availableBalance", 0) or 0),
              float(acc.get("totalUnrealizedProfit", 0) or 0), bool(acc.get("canTrade", False))))
        # per-symbol: every enabled symbol + anything currently holding a position
        want = set(cfg.symbols)
        for r in client.position_risk():
            sym = r.get("symbol")
            amt = float(r.get("positionAmt", 0) or 0)
            if sym not in want and amt == 0:
                continue
            cur.execute("""
                INSERT INTO ict_trade.live_account_snapshot
                  (symbol, network, position_amt, entry_price, mark_price, unrealized_pnl, leverage, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s, current_timestamp)
                ON CONFLICT (symbol) DO UPDATE SET
                  network=EXCLUDED.network, position_amt=EXCLUDED.position_amt,
                  entry_price=EXCLUDED.entry_price, mark_price=EXCLUDED.mark_price,
                  unrealized_pnl=EXCLUDED.unrealized_pnl, leverage=EXCLUDED.leverage,
                  updated_at=current_timestamp
            """, (sym, net, amt, float(r.get("entryPrice", 0) or 0),
                  float(r.get("markPrice", 0) or 0), float(r.get("unRealizedProfit", 0) or 0),
                  int(float(r.get("leverage", 0) or 0))))
        conn.commit()
    except (BinanceError, Exception) as e:  # noqa: BLE001
        conn.rollback()
        print(f"  [snapshot] skipped: {e}")
    finally:
        cur.close()


# ------------------------------------------------------------------ main
def main():
    cfg = cfgmod.load_cfg()
    now = pd.Timestamp.now(tz="UTC")
    armed = cfg.armed
    head = ("ARMED (LIVE ORDERS)" if armed else
            ("DRY-RUN (no orders)" if cfg.dry_run else "HALTED (LIVE_TRADING_ENABLED=false)"))
    print(f"=== {st.VERSION} executor @ {now:%Y-%m-%d %H:%M}Z | {head} | mode={cfg.entry_mode} "
          f"cap={cfg.runner_cap_r:g}R | risk=${cfg.risk_usd:g} {cfg.leverage}x {cfg.margin_type} | "
          f"max {cfg.max_concurrent} pos / ${cfg.max_total_risk_usd:g} | {list(cfg.symbols)} ===", flush=True)

    if not cfg.trading_enabled and not cfg.dry_run:
        print("[halt] LIVE_TRADING_ENABLED=false and not a dry-run — no-op.")
        return

    client = _client(cfg)
    try:
        off = client.sync_time()
        xi = _load_exchange_info(cfg, client)
    except BinanceError as e:
        print(f"[fatal] exchangeInfo/time: {e}")
        return
    print(f"  clock offset {off:+d}ms | exchangeInfo: BTC tradable={xi.is_tradable_perp('BTCUSDT')} "
          f"XAU tradable={xi.is_tradable_perp('XAUUSDT')}")

    live = tsc.live_conn()
    bt = tsc.backtest_conn() if armed else None

    # 1) NEW signals -> intents (dry) / positions (armed)
    sigs = _read_recent_signals(cfg, live, now)
    # One position per symbol (Binance one-way mode NETS all orders for a symbol into ONE position,
    # so independent same-symbol pyramiding is impossible). open_by_sym = the currently-open row per
    # symbol; a SAME-direction new signal is ignored, an OPPOSITE one REVERSES (close + flip).
    open_by_sym = {p["symbol"]: p for p in st.fetch_open(live, cfg.symbols)} if armed else {}
    managed = set(open_by_sym)
    print(f"  {len(sigs)} recent dch30_4h signal(s) in window")
    for sig in sigs:
        sym = sig["symbol"]
        lv = _levels_for(cfg, sig)
        qty, tp1q, skip = _size_and_screen(cfg, xi, sig, lv)
        gate, _ = _confirm_status(cfg, sig, now)
        intent = _intent_dict(cfg, sig, lv, qty, tp1q, gate, xi)
        if skip:
            print(f"  · {sym:<9} SKIP: {skip}")
            continue
        if not armed:
            print(f"  · {sym:<9} {sig['direction'].upper():<5} gate={gate}  INTENT:")
            print("    " + json.dumps(intent, default=str))
            continue
        # armed: only act on a CONFIRMED breakout (matches the backtest's confirmed-only rows)
        if gate != "confirmed":
            continue
        existing = open_by_sym.get(sym)
        if existing is not None:
            if (existing["direction"] or "").upper() == sig["direction"].upper():
                continue                                    # same direction -> no pyramiding
            try:                                            # opposite -> reverse (close, then open new)
                _reverse_close(cfg, client, live, bt, existing, now)
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
        if st.total_open_risk_usd(live, cfg.risk_usd) + cfg.risk_usd > cfg.max_total_risk_usd:
            print(f"  · {sig['symbol']:<9} SKIP: MAX_TOTAL_RISK_USD {cfg.max_total_risk_usd} reached")
            continue
        _ensure_account(cfg, client, sig["symbol"])
        fire = pd.Timestamp(sig["signal_time"]).tz_convert("UTC") + pd.Timedelta(minutes=LTF_MIN)
        pos_id = st.create_position(
            live, symbol=sig["symbol"], signal_time=pd.Timestamp(sig["signal_time"]),
            direction=sig["direction"], side=_side(sig["direction"]), entry_mode=cfg.entry_mode,
            lv=lv, qty=qty, tp1_qty=tp1q, leverage=cfg.leverage,
            entry_deadline=fire + pd.Timedelta(minutes=cfg.expiry_min),
            context={"strategy": sig.get("strategy")})
        if pos_id is None:
            continue
        managed.add(sig["symbol"])
        print(f"  + {sig['symbol']:<9} {sig['direction'].upper():<5} position {pos_id} created (gate=confirmed)")

    # 2) reconcile open positions
    if armed:
        for pos in st.fetch_open(live, cfg.symbols):
            try:
                _reconcile(cfg, client, live, bt, xi, pos, now)
            except BinanceError as e:
                print(f"  ! {pos['symbol']} reconcile error: {e}")
                notify.alert(f"⚠️ <b>{pos['symbol']}</b> reconcile error: {e}", chat_id=cfg.telegram_chat_id)

    # 3) snapshot the real exchange state for the dashboard (read-only; needs only credentials)
    if cfg.api_key and cfg.api_secret:
        _write_snapshot(cfg, client, live)
        print(f"  snapshot written ({'testnet' if cfg.testnet else 'mainnet'})")

    live.close()
    if bt:
        bt.close()
    print("  done.")


if __name__ == "__main__":
    main()
