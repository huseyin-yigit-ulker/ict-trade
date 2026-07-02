"""MIDAS executor — the reconciler (cron #1) + dry-run intent logger for the gold Binance bridge.

Reads the SAME mode='midas' live signals the paper feed + dashboard use (ict_trade.signals) and drives
real Binance USDⓈ-M Futures orders that reproduce sync/midas/strategy: a POST-ONLY maker LIMIT entry at
the VWAP-trend pullback close, a 1.5*ATR initial stop, then a 3.5*ATR CHANDELIER trailing stop that
ratchets every 1m bar to an 8h / session-close exit. NO fixed take-profit; NO reversal; ONE position.

The exit engine IS sync/midas/strategy.track_open — the exact function the paper canli.py drives — so
the live stop path is identical to the paper feed by construction (the Faz-0 parity gate).

    MIDAS_EXEC_DRY_RUN=true  python sync/midas_exec/executor.py                       # log intents, send NOTHING
    LIVE_TRADING_ENABLED=true MIDAS_EXEC_ENABLED=true MIDAS_EXEC_DRY_RUN=false \
        BINANCE_TESTNET=true python sync/midas_exec/executor.py                        # armed on TESTNET

⚠️ COST: MIDAS is validated on a $0.50/oz FX cost (+142R). On Binance TAKER (~10 bps ≈ $4/oz) the same
trades are ≈ −92R. This bridge runs TESTNET/dry-run first; a Binance-fee simulation gates any mainnet
arming (see parity_report.py + MIDAS.md). Master no-op when LIVE_TRADING_ENABLED / MIDAS_EXEC_ENABLED
are false.
"""
from __future__ import annotations

import sys
import json
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve()
# Order matters: config.py + state.py ALSO exist in sync/live_exec (the OPUS executor), so this
# package's own dir MUST be front-most on sys.path or `import config/state` would resolve to OPUS's.
# Insert least-specific first, then our own dir LAST so it wins.
sys.path.insert(0, str(_HERE.parents[1] / "midas"))         # strategy (the exit engine)
sys.path.insert(0, str(_HERE.parents[1] / "live_exec"))     # reuse binance_futures/exchange_info/sizing/notify
sys.path.insert(0, str(_HERE.parents[1]))                   # sync/           -> trade_sync_common
sys.path.insert(0, str(_HERE.parent))                       # sync/midas_exec -> config, state (front-most)
import trade_sync_common as tsc                              # noqa: E402
import config as cfgmod                                      # noqa: E402
import state as st                                           # noqa: E402
import sizing                                                # noqa: E402
import notify                                                # noqa: E402
import strategy as M                                         # noqa: E402
from binance_futures import BinanceFutures, BinanceError     # noqa: E402
from exchange_info import ExchangeInfo                        # noqa: E402

ALLOW_CONTRACTS = ("PERPETUAL", "TRADIFI_PERPETUAL")         # gold on Binance is TRADIFI_PERPETUAL
NEW_SIGNAL_LOOKBACK_MIN = 15                                 # only enter a signal this fresh (else stale)


# ------------------------------------------------------------------ wiring
def _client(cfg) -> BinanceFutures:
    return BinanceFutures(api_key=cfg.api_key, api_secret=cfg.api_secret,
                          base_url=cfg.base_url, proxy=cfg.proxy)


def _load_exchange_info(cfg, client) -> ExchangeInfo:
    """exchangeInfo is PUBLIC — works in dry-run without API keys."""
    return ExchangeInfo(client.exchange_info())


def _tag(cfg) -> str:
    return f"{cfg.exec_name} · {cfg.exec_version}" if cfg.exec_name else cfg.exec_version


def _ensure_account(cfg, client, symbol: str) -> None:
    """Idempotent per-symbol account setup (armed only): isolated margin + fixed leverage. Gold's
    TradFi bracket may be lower than MIDAS_LEVERAGE — a clamp/error is non-fatal (risk is set by qty)."""
    if not cfg.armed:
        return
    try:
        client.set_margin_type(symbol, cfg.margin_type)
    except BinanceError as e:
        print(f"  ! {symbol} set_margin_type: {e}")
    try:
        client.set_leverage(symbol, cfg.leverage)
    except BinanceError as e:
        print(f"  ! {symbol} set_leverage({cfg.leverage}): {e} (kept exchange default)")


# ------------------------------------------------------------------ helpers
def _side(direction: str) -> str:
    return "BUY" if str(direction).lower() in ("long", "buy") else "SELL"


def _exit_side(direction: str) -> str:
    return "SELL" if str(direction).lower() in ("long", "buy") else "BUY"


def _sign(direction: str) -> int:
    return 1 if str(direction).lower() in ("long", "buy") else -1


def _ctx(pos: dict) -> dict:
    c = pos.get("context")
    if isinstance(c, str):
        try:
            c = json.loads(c)
        except (ValueError, TypeError):
            c = {}
    return dict(c or {})


def _last_price(sym, now) -> float | None:
    try:
        d = tsc.fetch_1m(sym, now - pd.Timedelta(minutes=5), now)
        return float(d["close"].iloc[-1]) if d is not None and not d.empty else None
    except Exception:  # noqa: BLE001
        return None


def _position_amt(client, sym) -> float:
    for p in client.position_risk(sym):
        if p.get("symbol") == sym:
            return float(p.get("positionAmt", 0) or 0)
    return 0.0


def _get_order(client, sym, coid) -> dict | None:
    if not coid:
        return None
    try:
        return client.get_order(sym, client_order_id=coid)
    except BinanceError:
        return None


def _order_fill_time(o: dict, now) -> pd.Timestamp:
    t = o.get("updateTime") or o.get("time")
    try:
        return pd.Timestamp(int(t), unit="ms", tz="UTC") if t else now
    except (TypeError, ValueError):
        return now


def _realized_since(client, sym, since) -> float:
    """Sum realizedPnl (USDT) from userTrades since `since` — the true $ result of the position."""
    if not since:
        return 0.0
    try:
        start_ms = int(pd.Timestamp(since).timestamp() * 1000)
        return sum(float(t.get("realizedPnl", 0) or 0)
                   for t in client.user_trades(sym, limit=200, start_ms=start_ms))
    except BinanceError:
        return 0.0


def _in_session(now) -> bool:
    """True if the last CLOSED 1m bar is within real FX-gold hours (add_market_open). Fail-OPEN on a
    data error so a transient fetch glitch never blocks a legit entry (the exchange also rejects
    out-of-hours orders on a TradFi perp, and track_open force-closes at the session boundary)."""
    try:
        df = M.load_1m(now - pd.Timedelta(hours=3), now)
        if df is None or df.empty:
            return True
        df = M.add_market_open(df)
        df = df[df.index + pd.Timedelta(minutes=1) <= now]
        return True if df.empty else bool(df["open_mkt"].iloc[-1])
    except Exception:  # noqa: BLE001
        return True


# ------------------------------------------------------------------ exchange order legs (armed)
def _market_close(cfg, client, conn, pos, qty, *, leg) -> dict | None:
    qty = float(qty or 0)
    if qty <= 0:
        return None
    sym = pos["symbol"]
    coid = st.coid(pos["id"], leg)
    try:
        resp = client.new_order(symbol=sym, side=_exit_side(pos["direction"]), type="MARKET",
                                quantity=qty, reduceOnly="true", newClientOrderId=coid)
    except BinanceError as e:
        print(f"  ! {sym} market close {leg}: {e}")
        return None
    st.log_order(conn, position_id=pos["id"], symbol=sym, leg=leg, action="fill",
                 client_order_id=coid, order_id=resp.get("orderId"), payload=resp)
    return resp


def _place_protective_stop(cfg, client, conn, xi, pos, level: float) -> bool:
    """Resting STOP_MARKET(closePosition) at `level` — MAINNET only (testnet rejects conditional
    orders with -4120, where the synthetic reconciler is the protection). Best-effort."""
    if cfg.testnet:
        return False
    sym = pos["symbol"]
    try:
        resp = client.new_algo_order(
            symbol=sym, side=_exit_side(pos["direction"]), type="STOP_MARKET",
            triggerPrice=xi.round_price(sym, level, mode="nearest"),
            closePosition="true", workingType="MARK_PRICE")
        st.log_order(conn, position_id=pos["id"], symbol=sym, leg="sl", action="place",
                     client_order_id=resp.get("clientAlgoId"), order_id=resp.get("algoId"), payload=resp)
        return True
    except BinanceError as e:
        print(f"  ! {sym} protective stop algo failed: {e} (safety_sweep backstops)")
        return False


def _cancel_resting(cfg, client, sym: str) -> None:
    if cfg.testnet:
        return
    for fn in (client.cancel_all_open_orders, client.cancel_all_algo_orders):
        try:
            fn(sym)
        except BinanceError:
            pass


# ------------------------------------------------------------------ entry lifecycle
def _manage_entry(cfg, client, conn, xi, pos, now) -> None:
    sym = pos["symbol"]
    sign = _sign(pos["direction"])
    signal_entry = float(pos["signal_entry"])
    risk0 = float(pos["risk0"])
    coid = st.coid(pos["id"], "entry", 0)
    o = _get_order(client, sym, coid)
    status = (o or {}).get("status")

    if status == "FILLED":
        avg = float(o.get("avgPrice") or 0) or signal_entry
        _enter_open(cfg, client, conn, xi, pos, avg, _order_fill_time(o, now), o, now)
        return

    last = _last_price(sym, now)
    slipped = last is not None and ((last - signal_entry) * sign) > cfg.entry_max_slip_r * risk0
    dl = pos.get("entry_deadline")
    expired = dl is not None and now > pd.Timestamp(dl).tz_convert("UTC")
    if slipped or expired:
        if status in ("NEW", "PARTIALLY_FILLED"):
            try:
                client.cancel_order(sym, client_order_id=coid)
            except BinanceError:
                pass
        reason = "slipped" if slipped else "unfilled"
        st.patch(conn, pos["id"], state=st.CANCELLED, exit_reason=reason, exit_time=now)
        notify.alert(f"⏭️ <b>GİRİŞ İPTAL</b> · <b>{sym}</b> {str(pos['direction']).upper()} #{pos['id']}\n"
                     f"maker limit {'fiyat kaçtı (+%.2gR)' % cfg.entry_max_slip_r if slipped else 'dolmadı (süre doldu)'}"
                     f" — {_tag(cfg)}", chat_id=cfg.telegram_chat_id)
        print(f"  ⏭️ {sym} entry {reason} — cancelled")
        return

    if status in ("NEW", "PARTIALLY_FILLED"):
        if pos["state"] != st.ENTRY_WORKING:
            st.patch(conn, pos["id"], state=st.ENTRY_WORKING, entry_coid=coid,
                     entry_order_id=(o or {}).get("orderId"))
        return

    _place_entry(cfg, client, conn, xi, pos, now)


def _place_entry(cfg, client, conn, xi, pos, now) -> None:
    sym = pos["symbol"]
    _ensure_account(cfg, client, sym)
    qty = float(pos["qty"])
    coid = st.coid(pos["id"], "entry", 0)
    params = dict(symbol=sym, side=_side(pos["direction"]), quantity=qty, newClientOrderId=coid)
    if cfg.maker_entry:
        price = xi.round_price(sym, float(pos["signal_entry"]), mode="nearest")
        params.update(type="LIMIT", timeInForce="GTX", price=price)
    else:
        params.update(type="MARKET")
    try:
        resp = client.new_order(**params)
    except BinanceError as e:
        if e.code in (-2010, -5022):                        # post-only would immediately match -> retry
            print(f"  · {sym} maker entry would cross (post-only) — retry next tick")
            return
        if e.code == -4411:                                 # account hasn't accepted the TradFi-Perps agreement
            print(f"  ✋ {sym} gold trading blocked: sign the Binance 'TradFi-Perps agreement' on this "
                  f"account (one-time) before MIDAS-X can place orders.")
            st.log_order(conn, position_id=pos["id"], symbol=sym, leg="entry", action="error",
                         client_order_id=coid, payload={"err": str(e)})
            notify.alert(f"✋ <b>{sym}</b> MIDAS-X: hesap 'TradFi-Perps' sözleşmesini imzalamamış — Binance'te "
                         f"altın işlemi için bir kereliğine onayla (aksi halde emir gitmez) — {_tag(cfg)}",
                         chat_id=cfg.telegram_chat_id)
            return
        print(f"  ! {sym} entry place error: {e}")
        st.log_order(conn, position_id=pos["id"], symbol=sym, leg="entry", action="error",
                     client_order_id=coid, payload={"err": str(e)})
        return
    st.log_order(conn, position_id=pos["id"], symbol=sym, leg="entry", action="place",
                 client_order_id=coid, order_id=resp.get("orderId"), payload=resp)
    if resp.get("status") == "FILLED":
        avg = float(resp.get("avgPrice") or 0) or float(pos["signal_entry"])
        _enter_open(cfg, client, conn, xi, pos, avg, now, resp, now)
    else:
        st.patch(conn, pos["id"], state=st.ENTRY_WORKING, entry_coid=coid, entry_order_id=resp.get("orderId"))
        print(f"  ⏳ {sym} maker entry resting @ {params.get('price', 'MARKET')}")


def _enter_open(cfg, client, conn, xi, pos, avg: float, fill_time, resp, now) -> None:
    sym = pos["symbol"]
    time_stop = pd.Timestamp(fill_time) + pd.Timedelta(minutes=M.MAX_HOLD_MIN)
    ctx = _ctx(pos)
    ctx.update(init_sl=float(pos["signal_sl"]), placed_sl=None, pos="open")
    st.patch(conn, pos["id"], state=st.OPEN, eff_entry=avg, entry_fill_time=fill_time, entry_fill_px=avg,
             time_stop_at=time_stop, entry_coid=st.coid(pos["id"], "entry", 0),
             entry_order_id=(resp or {}).get("orderId"), context=ctx)
    if _place_protective_stop(cfg, client, conn, xi, pos, float(pos["signal_sl"])):
        ctx["placed_sl"] = float(pos["signal_sl"])
        st.patch(conn, pos["id"], context=ctx)
    notify.alert(f"✅ <b>GİRİŞ</b> · <b>{sym}</b> {str(pos['direction']).upper()} #{pos['id']}\n"
                 f"giriş {avg:g} · {float(pos['qty']):g} adet (${float(pos['qty'])*avg:.0f}) · risk ${cfg.risk_usd:g}\n"
                 f"SL {float(pos['signal_sl']):g} (−1R · 1.5·ATR) · 3.5·ATR iz-süren · 8s/seans "
                 f"({'borsa STOP' if not cfg.testnet else 'sentetik'}) — {_tag(cfg)}",
                 chat_id=cfg.telegram_chat_id)
    print(f"  ✅ {sym} ENTERED @ {avg:g} · SL {float(pos['signal_sl']):g}")


# ------------------------------------------------------------------ open-position reconcile
def _update_trailing(cfg, client, conn, xi, pos, res, now) -> None:
    sym = pos["symbol"]
    cur_sl = float(res["cur_sl"])
    ctx = _ctx(pos)
    ctx.update(cur_sl=cur_sl, best=float(res["best"]), locked_r=round(float(res["locked_r"]), 3),
               trail=res.get("trail"), init_sl=float(res["init_sl"]), pos="open")
    fields: dict = dict(cur_sl=cur_sl, best=float(res["best"]), locked_r=round(float(res["locked_r"]), 3))
    if not cfg.testnet:                                     # mainnet: cancel/replace the resting stop
        placed = ctx.get("placed_sl")
        f = xi.get(sym)
        tick = f.tick_size if f else 0.0
        if placed is None or abs(cur_sl - float(placed)) >= max(cfg.sl_deadband_ticks, 1) * tick:
            _cancel_resting(cfg, client, sym)
            if _place_protective_stop(cfg, client, conn, xi, pos, cur_sl):
                ctx["placed_sl"] = cur_sl
                fields["trail_gen"] = int(pos.get("trail_gen") or 0) + 1
    fields["context"] = ctx
    st.patch(conn, pos["id"], **fields)
    print(f"  🔁 {sym} SL→{cur_sl:g} · {res['locked_r']:+.2f}R")


def _finalize(cfg, client, conn, bt, pos, *, reason, exit_px, exit_time, res_pnl_r, now) -> None:
    """Common close path: MARKET-close any residual, drop resting orders, record REAL R/USD, writeback."""
    sym = pos["symbol"]
    amt = _position_amt(client, sym)
    if amt:
        _market_close(cfg, client, conn, pos, abs(amt), leg="exit")
    _cancel_resting(cfg, client, sym)
    risk0 = float(pos["risk0"]); qty = float(pos.get("qty") or 0)
    if cfg.armed:
        realized_usd = _realized_since(client, sym, pos.get("entry_fill_time"))
        denom = risk0 * qty
        realized_r = (realized_usd / denom) if denom else res_pnl_r
    else:
        realized_usd = None
        realized_r = res_pnl_r
    ctx = _ctx(pos)
    ctx.update(pos="closed", exit_px=exit_px,
               pnl_r=(round(realized_r, 3) if realized_r is not None else None))
    st.patch(conn, pos["id"], state=st.CLOSED, exit_reason=reason, exit_px=exit_px,
             exit_time=exit_time or now, realized_r=realized_r, realized_usd=realized_usd, context=ctx)
    if bt is not None:
        st.writeback_trading_signals(bt, st.reload(conn, pos["id"]))
    r_txt = f"{realized_r:+.2f}R" if realized_r is not None else "R bilinmiyor"
    usd_txt = f" · {realized_usd:+.2f}$" if realized_usd is not None else ""
    emoji = "✅" if (realized_r is not None and realized_r >= 0) else "❌"
    label = {"trail/stop": "iz-süren stop", "time": "8s süre", "session": "seans sonu",
             "closed_externally": "borsa/likidite kapanışı"}.get(reason, reason)
    notify.alert(f"{emoji} <b>KAPANDI</b> · <b>{sym}</b> {str(pos['direction']).upper()} #{pos['id']}\n"
                 f"Çıkış {exit_px:g} ({label}) · <b>{r_txt}</b>{usd_txt} — {_tag(cfg)}",
                 chat_id=cfg.telegram_chat_id)
    print(f"  🏁 {sym} CLOSED {r_txt} ({reason})")


def _reconcile(cfg, client, conn, bt, xi, pos, now) -> None:
    sym = pos["symbol"]
    state = pos["state"]
    if state in (st.PENDING_ENTRY, st.ENTRY_WORKING):
        _manage_entry(cfg, client, conn, xi, pos, now)
        return
    if state != st.OPEN:
        return

    # exchange truth wins: DB says OPEN but Binance is flat -> the resting stop fired (mainnet) or a
    # manual/liquidation close happened. Finalize from realizedPnl instead of looping.
    if pos.get("entry_fill_time") and _position_amt(client, sym) == 0:
        _finalize(cfg, client, conn, bt, pos, reason="closed_externally", exit_px=_last_price(sym, now),
                  exit_time=now, res_pnl_r=None, now=now)
        return

    # the trailing engine — the SAME call the paper canli.py drives (parity by construction)
    res = M.track_open(pd.Timestamp(pos["entry_fill_time"]), _sign(pos["direction"]),
                       float(pos["signal_entry"]), float(pos["signal_sl"]), now)
    if res is None:
        tstop = pos.get("time_stop_at")
        if tstop and now >= pd.Timestamp(tstop).tz_convert("UTC"):   # data-gap fallback past the 8h cap
            _finalize(cfg, client, conn, bt, pos, reason="time", exit_px=_last_price(sym, now),
                      exit_time=now, res_pnl_r=None, now=now)
        return
    if res["status"] == "closed":
        _finalize(cfg, client, conn, bt, pos, reason=res["reason"], exit_px=float(res["exit_px"]),
                  exit_time=res.get("exit_time"), res_pnl_r=res.get("pnl_r"), now=now)
        return
    _update_trailing(cfg, client, conn, xi, pos, res, now)


# ------------------------------------------------------------------ new signal -> position
def _read_midas_signals(cfg, live, now) -> list[dict]:
    """Fresh mode='midas' signals for our symbol that are not yet closed in the paper feed."""
    w_start = now - pd.Timedelta(minutes=NEW_SIGNAL_LOOKBACK_MIN)
    cur = live.cursor()
    cur.execute("""
        SELECT symbol, signal_time, direction, entry, sl, tp, context
        FROM ict_trade.signals
        WHERE mode='midas' AND signal_time >= %s AND symbol = %s
          AND COALESCE(context->>'pos','open') <> 'closed'
        ORDER BY signal_time DESC
    """, (w_start.to_pydatetime(), cfg.symbol))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return rows


def _size_screen(cfg, xi, sig) -> tuple[float, float, str]:
    """Return (qty, risk0, skip_reason). skip_reason='' means OK."""
    sym = sig["symbol"]
    entry = float(sig["entry"]); sl = float(sig["sl"])
    risk0 = abs(entry - sl)
    if risk0 <= 0:
        return 0.0, 0.0, "risk0<=0"
    if not xi.is_tradable(sym, allow=ALLOW_CONTRACTS):
        f = xi.get(sym)
        return 0.0, risk0, f"not tradable (status={getattr(f,'status','?')} type={getattr(f,'contract_type','?')})"
    qty = xi.floor_qty(sym, sizing.qty_for_risk(entry, sl, cfg.risk_usd))
    if qty <= 0:
        return 0.0, risk0, "qty rounds to 0"
    if not xi.passes_min_notional(sym, qty, entry):
        return 0.0, risk0, f"below MIN_NOTIONAL (qty={qty} px={entry:g})"
    return qty, risk0, ""


def _create(cfg, xi, live, sig, now) -> int | None:
    sym = sig["symbol"]; direction = sig["direction"]
    qty, risk0, skip = _size_screen(cfg, xi, sig)
    if skip:
        print(f"  · {sym} SKIP: {skip}")
        return None
    if not _in_session(now):
        print(f"  · {sym} SKIP: out of FX-gold session")
        return None
    entry = float(sig["entry"]); sl = float(sig["sl"])
    sign = _sign(direction)
    tp_ref = entry + sign * M.TP_REF_MULT * risk0
    ctx = {"strategy": "MIDAS VWAP-Trend (live, Binance)", "kind": "trailing", "init_sl": sl,
           "tp_ref": tp_ref, "trail_mult": M.TRAIL_MULT, "atr_mult": M.ATR_INIT_MULT,
           "pos": "open", "paper": False}
    pos_id = st.create_position(
        live, symbol=sym, signal_time=pd.Timestamp(sig["signal_time"]), direction=direction,
        side=_side(direction), signal_entry=entry, signal_sl=sl, risk0=risk0, qty=qty,
        leverage=cfg.leverage, entry_deadline=now + pd.Timedelta(seconds=cfg.entry_timeout_sec),
        version=cfg.exec_version, context=ctx)
    if pos_id is not None:
        print(f"  + {sym} {direction.upper()} position {pos_id} created (maker entry pending)")
    return pos_id


def _log_intent(cfg, xi, sig, now) -> None:
    sym = sig["symbol"]
    qty, risk0, skip = _size_screen(cfg, xi, sig)
    if skip:
        print(f"  · {sym:<9} {sig['direction'].upper():<5} SKIP: {skip}")
        return
    price = xi.round_price(sym, float(sig["entry"]), mode="nearest")
    intent = {"symbol": sym, "direction": sig["direction"], "signal_time": str(pd.Timestamp(sig["signal_time"])),
              "entry": {"type": "LIMIT(GTX)" if cfg.maker_entry else "MARKET", "price": price, "qty": qty},
              "init_sl": float(sig["sl"]), "risk0": round(risk0, 6), "risk_usd": cfg.risk_usd,
              "exit": "3.5*ATR chandelier trail / 8h / session (track_open)"}
    print(f"  · {sym:<9} {sig['direction'].upper():<5} INTENT: {json.dumps(intent, default=str)}")


# ------------------------------------------------------------------ dashboard snapshot
def _write_snapshot(cfg, client, conn) -> None:
    """Snapshot the REAL exchange state into ict_trade.live_account(_snapshot) for the dashboard.
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
            ("DRY-RUN (no orders)" if cfg.dry_run else "HALTED (disabled)"))
    net = "testnet" if cfg.testnet else "MAINNET"
    print(f"=== {_tag(cfg)} executor @ {now:%Y-%m-%d %H:%M}Z | {head} | {net} | {cfg.symbol} "
          f"risk ${cfg.risk_usd:g} {cfg.leverage}x {cfg.margin_type} | maker={cfg.maker_entry} ===", flush=True)

    if not (cfg.trading_enabled and cfg.exec_enabled) and not cfg.dry_run:
        print("[halt] LIVE_TRADING_ENABLED / MIDAS_EXEC_ENABLED false and not a dry-run — no-op.")
        return

    client = _client(cfg)
    try:
        off = client.sync_time()
        xi = _load_exchange_info(cfg, client)
    except BinanceError as e:
        print(f"[fatal] exchangeInfo/time: {e}")
        return
    f = xi.get(cfg.symbol)
    print(f"  clock offset {off:+d}ms | {cfg.symbol} tradable={xi.is_tradable(cfg.symbol, allow=ALLOW_CONTRACTS)} "
          f"(type={getattr(f, 'contract_type', '?')} status={getattr(f, 'status', '?')})")

    live = tsc.live_conn()
    bt = tsc.backtest_conn() if armed else None

    sigs = _read_midas_signals(cfg, live, now)
    print(f"  {len(sigs)} recent midas signal(s) in window")

    if not armed:
        for sig in sigs:
            _log_intent(cfg, xi, sig, now)
    else:
        if st.count_open(live, [cfg.symbol]) == 0 and sigs:
            _create(cfg, xi, live, sigs[0], now)            # single position: newest fresh signal only
        for pos in st.fetch_open(live, [cfg.symbol]):
            try:
                _reconcile(cfg, client, live, bt, xi, pos, now)
            except BinanceError as e:
                print(f"  ! {pos['symbol']} reconcile error: {e}")
                notify.alert(f"⚠️ <b>{pos['symbol']}</b> MIDAS reconcile error: {e}",
                             chat_id=cfg.telegram_chat_id)

    if cfg.api_key and cfg.api_secret:
        _write_snapshot(cfg, client, live)
        print(f"  snapshot written ({net})")

    live.close()
    if bt:
        bt.close()
    print("  done.")


if __name__ == "__main__":
    main()
