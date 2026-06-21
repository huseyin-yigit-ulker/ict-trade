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


def _place_entry(cfg, client, conn, xi, pos: dict, lv: lvl.Levels) -> None:
    sym = pos["symbol"]
    coid = st.coid(pos["id"], "entry")
    params = dict(symbol=sym, side=_side(pos["direction"]), quantity=pos["qty"],
                  newClientOrderId=coid, workingType="CONTRACT_PRICE")
    if cfg.entry_mode == "B":
        params.update(type="STOP_MARKET", stopPrice=xi.round_price(sym, lv.entry_stop))
    else:
        params.update(type="LIMIT", price=xi.round_price(sym, lv.entry_stop), timeInForce="GTC")
    resp = client.new_order(**params)
    st.log_order(conn, position_id=pos["id"], symbol=sym, leg="entry", action="place",
                 client_order_id=coid, order_id=resp.get("orderId"), payload=resp)
    st.patch(conn, pos["id"], state=st.ENTRY_WORKING, entry_coid=coid,
             entry_order_id=resp.get("orderId"))


def _place_protective(cfg, client, conn, xi, pos: dict, lv: lvl.Levels) -> None:
    """OPEN_FULL legs: full SL (closePosition) + TP1 (reduceOnly, 60%)."""
    sym = pos["symbol"]
    sl_coid, tp1_coid = st.coid(pos["id"], "sl"), st.coid(pos["id"], "tp1")
    sl = client.new_order(symbol=sym, side=_exit_side(pos["direction"]), type="STOP_MARKET",
                          closePosition="true", stopPrice=xi.round_price(sym, lv.sl),
                          workingType="MARK_PRICE", newClientOrderId=sl_coid)
    st.log_order(conn, position_id=pos["id"], symbol=sym, leg="sl", action="place",
                 client_order_id=sl_coid, order_id=sl.get("orderId"), payload=sl)
    tp1 = client.new_order(symbol=sym, side=_exit_side(pos["direction"]), type="TAKE_PROFIT_MARKET",
                           reduceOnly="true", quantity=pos["tp1_qty"],
                           stopPrice=xi.round_price(sym, lv.tp1), workingType="MARK_PRICE",
                           newClientOrderId=tp1_coid)
    st.log_order(conn, position_id=pos["id"], symbol=sym, leg="tp1", action="place",
                 client_order_id=tp1_coid, order_id=tp1.get("orderId"), payload=tp1)
    st.patch(conn, pos["id"], sl_coid=sl_coid, sl_order_id=sl.get("orderId"),
             tp1_coid=tp1_coid, tp1_order_id=tp1.get("orderId"))


def _place_runner(cfg, client, conn, xi, pos: dict, runner_qty: float) -> None:
    """RUNNER legs after TP1: cancel full SL, place BE-stop + cap on the real residual."""
    sym = pos["symbol"]
    client.cancel_order(sym, client_order_id=pos.get("sl_coid"))
    be_coid, cap_coid = st.coid(pos["id"], "be"), st.coid(pos["id"], "cap")
    be = client.new_order(symbol=sym, side=_exit_side(pos["direction"]), type="STOP_MARKET",
                          reduceOnly="true", quantity=runner_qty,
                          stopPrice=xi.round_price(sym, float(pos["eff_be"])),
                          workingType="MARK_PRICE", newClientOrderId=be_coid)
    st.log_order(conn, position_id=pos["id"], symbol=sym, leg="be", action="place",
                 client_order_id=be_coid, order_id=be.get("orderId"), payload=be)
    cap = client.new_order(symbol=sym, side=_exit_side(pos["direction"]), type="TAKE_PROFIT_MARKET",
                           reduceOnly="true", quantity=runner_qty,
                           stopPrice=xi.round_price(sym, float(pos["eff_cap"])),
                           workingType="MARK_PRICE", newClientOrderId=cap_coid)
    st.log_order(conn, position_id=pos["id"], symbol=sym, leg="cap", action="place",
                 client_order_id=cap_coid, order_id=cap.get("orderId"), payload=cap)
    st.patch(conn, pos["id"], state=st.RUNNER, runner_qty=runner_qty,
             be_coid=be_coid, be_order_id=be.get("orderId"),
             cap_coid=cap_coid, cap_order_id=cap.get("orderId"))


def _flatten_and_close(client, conn, sym, pos, *, reason, exit_px, realized_r):
    """Cancel all open orders, market-close any residual, mark CLOSED."""
    client.cancel_all_open_orders(sym)
    risk = abs(float(pos["eff_entry"] or pos["signal_entry"]) - float(pos["signal_sl"]))
    st.patch(conn, pos["id"], state=st.CLOSED, exit_reason=reason, exit_px=exit_px,
             exit_time=pd.Timestamp.now(tz="UTC"), realized_r=realized_r,
             realized_usd=(realized_r * (risk and pos.get("qty", 0))) if realized_r is not None else None)


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

    if state == st.PENDING_ENTRY:
        _place_entry(cfg, client, conn, xi, pos, lv)
        return

    if state == st.ENTRY_WORKING:
        filled = _order_filled(client, sym, pos.get("entry_coid"))
        if filled:
            avg = float(filled.get("avgPrice") or filled.get("price") or lv.eff_entry)
            rl = lvl.reanchor(lv, avg, first_r=cfg.first_r)
            time_stop = now + pd.Timedelta(days=cfg.horizon_days)   # horizon from fill
            st.patch(conn, pos["id"], state=st.OPEN_FULL, entry_fill_time=now, entry_fill_px=avg,
                     eff_entry=avg, eff_tp1=rl.tp1, eff_be=rl.be, time_stop_at=time_stop)
            pos = {**pos, "eff_entry": avg, "eff_tp1": rl.tp1, "eff_be": rl.be}
            _place_protective(cfg, client, conn, xi, pos, rl)
            notify.alert(f"✅ <b>{sym}</b> entry filled @ {avg:g} ({pos['direction']}) — d30so8c",
                         chat_id=cfg.telegram_chat_id)
            return
        # not filled: cancel if reversed (adverse −0.5R first) or entry window expired
        deadline = pd.Timestamp(pos["entry_deadline"]).tz_convert("UTC")
        adverse = _adverse_hit(cfg, pos, now)
        if adverse or now >= deadline:
            client.cancel_order(sym, client_order_id=pos.get("entry_coid"))
            st.patch(conn, pos["id"], state=st.CANCELLED,
                     exit_reason="reversed" if adverse else "entry_expired")
            st.writeback_trading_signals(bt_conn, {**pos, "state": st.CANCELLED,
                                                   "exit_reason": "entry_expired"})
        return

    if state == st.OPEN_FULL:
        # SL hit?
        if _order_filled(client, sym, pos.get("sl_coid")) or _position_amt(client, sym) == 0:
            _flatten_and_close(client, conn, sym, pos, reason="sl",
                               exit_px=float(pos["signal_sl"]), realized_r=-1.0 - _fee_r(cfg, pos))
            st.writeback_trading_signals(bt_conn, _reload(conn, pos["id"]))
            notify.alert(f"🛑 <b>{sym}</b> stopped −1R — d30so8c", chat_id=cfg.telegram_chat_id)
            return
        # TP1 hit? -> book 60%, transition to runner
        if _order_filled(client, sym, pos.get("tp1_coid")):
            runner_qty = abs(_position_amt(client, sym))
            runner_qty = xi.floor_qty(sym, runner_qty)
            if runner_qty <= 0:
                _flatten_and_close(client, conn, sym, pos, reason="tp1_be",
                                   exit_px=float(pos["eff_tp1"]),
                                   realized_r=cfg.close_frac * cfg.first_r - _fee_r(cfg, pos))
                st.writeback_trading_signals(bt_conn, _reload(conn, pos["id"]))
                return
            st.patch(conn, pos["id"], tp1_fill_time=now, tp1_fill_px=float(pos["eff_tp1"]))
            _place_runner(cfg, client, conn, xi, {**pos}, runner_qty)
            notify.alert(f"🎯 <b>{sym}</b> TP1 +1R, booked {int(cfg.close_frac*100)}% — runner to +{cfg.runner_cap_r:g}R/BE",
                         chat_id=cfg.telegram_chat_id)
            return
        _maybe_time_stop(cfg, client, conn, bt_conn, sym, pos, now)
        return

    if state == st.RUNNER:
        amt = _position_amt(client, sym)
        if amt == 0 or _order_filled(client, sym, pos.get("cap_coid")) or _order_filled(client, sym, pos.get("be_coid")):
            cap_hit = bool(_order_filled(client, sym, pos.get("cap_coid")))
            if cap_hit:
                r = cfg.close_frac * cfg.first_r + (1 - cfg.close_frac) * cfg.runner_cap_r - _fee_r(cfg, pos)
                reason, px = "cap", float(pos["eff_cap"])
            else:
                r = cfg.close_frac * cfg.first_r - _fee_r(cfg, pos)     # BE: runner 0R
                reason, px = "breakeven", float(pos["eff_be"])
            _flatten_and_close(client, conn, sym, pos, reason=reason, exit_px=px, realized_r=r)
            st.writeback_trading_signals(bt_conn, _reload(conn, pos["id"]))
            notify.alert(f"🏁 <b>{sym}</b> runner {reason} ({r:+.2f}R) — d30so8c", chat_id=cfg.telegram_chat_id)
            return
        _maybe_time_stop(cfg, client, conn, bt_conn, sym, pos, now)
        return


def _adverse_hit(cfg, pos: dict, now: pd.Timestamp) -> bool:
    """True if the adverse −buf*risk level printed on 1m since the bar close (Mode B gate:
    a breakout that moved against us by 0.5R before confirming is NOT taken)."""
    if pos["entry_mode"] != "B":
        return False
    fire = pd.Timestamp(pos["signal_time"]).tz_convert("UTC") + pd.Timedelta(minutes=LTF_MIN)
    df1m = tsc.fetch_1m(pos["symbol"], fire - pd.Timedelta(minutes=2), now)
    if df1m is None or df1m.empty:
        return False
    cf = tsc.confirm_fill(df1m, fire, pos["direction"], float(pos["signal_entry"]),
                          float(pos["signal_sl"]), expiry_minutes=cfg.expiry_min)
    return cf is None and now < fire + pd.Timedelta(minutes=cfg.expiry_min + 1)


def _maybe_time_stop(cfg, client, conn, bt_conn, sym, pos, now: pd.Timestamp) -> None:
    ts_at = pos.get("time_stop_at")
    if not ts_at:
        return
    if now < pd.Timestamp(ts_at).tz_convert("UTC"):
        return
    # 3-day limit: market-close residual (mark-to-market)
    amt = _position_amt(client, sym)
    last = None
    try:
        d = tsc.fetch_1m(sym, now - pd.Timedelta(minutes=5), now)
        last = float(d["close"].iloc[-1]) if d is not None and not d.empty else None
    except Exception:  # noqa: BLE001
        pass
    risk = abs(float(pos["eff_entry"] or pos["signal_entry"]) - float(pos["signal_sl"]))
    sign = 1 if str(pos["direction"]).lower() == "long" else -1
    booked = cfg.close_frac * cfg.first_r if pos["state"] == st.RUNNER else 0.0
    runner_r = ((last - float(pos["eff_entry"])) * sign / risk) if (last and risk) else 0.0
    frac = (1 - cfg.close_frac) if pos["state"] == st.RUNNER else 1.0
    r = booked + frac * max(runner_r, 0.0) - _fee_r(cfg, pos)
    _flatten_and_close(client, conn, sym, pos, reason="time_stop", exit_px=last, realized_r=r)
    st.writeback_trading_signals(bt_conn, _reload(conn, pos["id"]))
    notify.alert(f"⏱️ <b>{sym}</b> 3-day mark-to-market ({r:+.2f}R) — d30so8c", chat_id=cfg.telegram_chat_id)


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
    print(f"=== d30so8c executor @ {now:%Y-%m-%d %H:%M}Z | {head} | mode={cfg.entry_mode} "
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
    managed = st.open_symbols(live) if armed else set()
    print(f"  {len(sigs)} recent dch30_4h signal(s) in window")
    for sig in sigs:
        lv = _levels_for(cfg, sig)
        qty, tp1q, skip = _size_and_screen(cfg, xi, sig, lv)
        gate, _ = _confirm_status(cfg, sig, now)
        intent = _intent_dict(cfg, sig, lv, qty, tp1q, gate, xi)
        if skip:
            print(f"  · {sig['symbol']:<9} SKIP: {skip}")
            continue
        if not armed:
            print(f"  · {sig['symbol']:<9} {sig['direction'].upper():<5} gate={gate}  INTENT:")
            print("    " + json.dumps(intent, default=str))
            continue
        # armed: only act on a CONFIRMED breakout (matches the backtest's confirmed-only rows)
        if gate != "confirmed":
            continue
        if sig["symbol"] in managed:
            continue
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
