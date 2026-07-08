"""TALOS-ICHI executor — the reconciler (cron #1) + dry-run intent logger for the gold Binance bridge.

Reads the SAME mode='talos_ichi' live signals the paper feed + dashboard use (ict_trade.signals) and drives
real Binance USDⓈ-M Futures orders that reproduce sync/talos_ichi/strategy: a POST-ONLY maker LIMIT entry at
the Keltner-band deep-pullback close, a 1.5*ATR initial stop, then a 3.5*ATR CHANDELIER trailing stop that
ratchets every 1m bar to an 8h / session-close exit. NO fixed take-profit; NO reversal; ONE position.

The exit engine IS sync/talos_ichi/strategy.track_open — the exact function the paper canli.py drives — so
the live stop path is identical to the paper feed by construction (the Faz-0 parity gate).

    TALOS_ICHI_EXEC_DRY_RUN=true  python sync/talos_ichi_exec/executor.py                       # log intents, send NOTHING
    LIVE_TRADING_ENABLED=true TALOS_ICHI_EXEC_ENABLED=true TALOS_ICHI_EXEC_DRY_RUN=false \
        BINANCE_TESTNET=true python sync/talos_ichi_exec/executor.py                        # armed on TESTNET

MULTI-USER (EXEC_MULTI_USER=true — the same one cutover switch as OPUS): main() fans out over
ict_trade.user_stream_settings (stream='talos_ichi', hard-locked testnet in sync/users/store.py) and runs
the SAME per-account tick with each user's keys/risk, per-user try/except isolation, per-user rows
(005a/005b user_id+network scoping) and per-user Web Push instead of the owner's Telegram.

⚠️ COST: TALOS-ICHI is validated on a $0.50/oz FX cost (+142R). On Binance TAKER (~10 bps ≈ $4/oz) the same
trades are ≈ −92R. This bridge runs TESTNET/dry-run first; a Binance-fee simulation gates any mainnet
arming (see parity_report.py + TALOS-ICHI.md). Master no-op when LIVE_TRADING_ENABLED / TALOS_ICHI_EXEC_ENABLED
are false.
"""
from __future__ import annotations

import re
import sys
import json
import time
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve()
# Order matters: config.py + state.py ALSO exist in sync/live_exec (the OPUS executor), so this
# package's own dir MUST be front-most on sys.path or `import config/state` would resolve to OPUS's.
# Insert least-specific first, then our own dir LAST so it wins.
sys.path.insert(0, str(_HERE.parents[1] / "talos_ichi"))         # strategy (the exit engine)
sys.path.insert(0, str(_HERE.parents[1] / "live_exec"))     # reuse binance_futures/exchange_info/sizing/notify
sys.path.insert(0, str(_HERE.parents[1]))                   # sync/           -> trade_sync_common
sys.path.insert(0, str(_HERE.parents[1] / "users"))         # sync/users      -> store (multi-user fan-out)
sys.path.insert(0, str(_HERE.parent))                       # sync/talos_ichi_exec -> config, state (front-most)
import trade_sync_common as tsc                              # noqa: E402
import config as cfgmod                                      # noqa: E402
import state as st                                           # noqa: E402
import sizing                                                # noqa: E402
import notify                                                # noqa: E402
import store as ustore                                       # noqa: E402  (sync/users/store.py)
import killswitch as ks                                      # noqa: E402  (flatten_positions — resolves to OURS, dir is front-most)
import strategy as M                                         # noqa: E402
from binance_futures import BinanceFutures, BinanceError     # noqa: E402
from exchange_info import ExchangeInfo                        # noqa: E402

ALLOW_CONTRACTS = ("PERPETUAL", "TRADIFI_PERPETUAL")         # gold on Binance is TRADIFI_PERPETUAL
NEW_SIGNAL_LOOKBACK_MIN = 15                                 # only enter a signal this fresh (else stale)

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
                         tag="exec", kind=kind)


def _net(cfg) -> str:
    return "testnet" if cfg.testnet else "mainnet"


# ------------------------------------------------------------------ wiring
def _client(cfg) -> BinanceFutures:
    return BinanceFutures(api_key=cfg.api_key, api_secret=cfg.api_secret,
                          base_url=cfg.base_url, proxy=cfg.proxy)


def _tag(cfg) -> str:
    return f"{cfg.exec_name} · {cfg.exec_version}" if cfg.exec_name else cfg.exec_version


def _ensure_account(cfg, client, symbol: str) -> None:
    """Idempotent per-symbol account setup (armed only): isolated margin + fixed leverage. Gold's
    TradFi bracket may be lower than TALOS_ICHI_LEVERAGE — a clamp/error is non-fatal (risk is set by qty)."""
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


# ------------------------------------------------------------------ shared per-tick caches
class SharedTick:
    """Everything user-INDEPENDENT in one cron tick, computed once and memoized so N users
    never multiply the market-data footprint (Binance REQUEST_WEIGHT is per IP — the shared
    VM egress is the scarce resource, account calls are per-key). At */1 cadence the 1m-kline
    memo is what matters for the single TALOS-ICHI symbol:
      * the fresh-signal window per symbol (one query — no user filter exists in it)
      * exchangeInfo + clock offset per network base URL
      * 1m klines per symbol (widest-range cache; narrower asks are slices)
      * the FX-gold session check (pure market data — user-independent)."""

    def __init__(self, now: pd.Timestamp):
        self.now = now
        self._signals: dict[str, list[dict]] = {}
        self._xi: dict[str, ExchangeInfo] = {}
        self._off: dict[str, int] = {}
        self._k1m: dict[str, tuple[pd.Timestamp, object]] = {}
        self._in_sess: bool | None = None

    def signals(self, live_conn, symbol: str) -> list[dict]:
        """Fresh mode='talos_ichi' signals for `symbol` that are not yet closed in the paper feed."""
        if symbol not in self._signals:
            w_start = self.now - pd.Timedelta(minutes=NEW_SIGNAL_LOOKBACK_MIN)
            cur = live_conn.cursor()
            cur.execute("""
                SELECT symbol, signal_time, direction, entry, sl, tp, context
                FROM ict_trade.signals
                WHERE mode='talos_ichi' AND signal_time >= %s AND symbol = %s
                  AND COALESCE(context->>'pos','open') <> 'closed'
                ORDER BY signal_time DESC
            """, (w_start.to_pydatetime(), symbol))
            cols = [d[0] for d in cur.description]
            self._signals[symbol] = [dict(zip(cols, r)) for r in cur.fetchall()]
            cur.close()
        return self._signals[symbol]

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

    def in_session(self) -> bool:
        if self._in_sess is None:
            self._in_sess = _in_session(self.now)
        return self._in_sess


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


def _last_price(sym, now, shared: SharedTick | None = None) -> float | None:
    try:
        fetch = shared.fetch_1m if shared is not None else tsc.fetch_1m
        d = fetch(sym, now - pd.Timedelta(minutes=5), now)
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
    except BinanceError as e:
        print(f"  ! {sym} userTrades error (realized=0 varsayıldı): {e}")
        return 0.0


def _funding_since(client, sym, since) -> float:
    """Sum FUNDING_FEE income (USDT) for `sym` since `since` — funding paid (<0) / received (>0) over
    the open position. Settled every 8h; NOT part of userTrades.realizedPnl, so tracked separately."""
    if not since:
        return 0.0
    try:
        start_ms = int(pd.Timestamp(since).timestamp() * 1000)
        return sum(float(r.get("income", 0) or 0)
                   for r in client.income(symbol=sym, income_type="FUNDING_FEE", start_ms=start_ms))
    except BinanceError:
        return 0.0


def _open_entry_times(conn, symbols, user_id=None, network=None) -> dict:
    """symbol -> entry_fill_time of the currently-open TALOS-ICHI position (anchors funding-since-entry)."""
    cur = conn.cursor()
    q = """
        SELECT symbol, min(entry_fill_time)
        FROM ict_trade.talos_ichi_positions
        WHERE state = 'OPEN' AND entry_fill_time is not null AND symbol = ANY(%s)
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


def _fx_day_open_utc(ts: pd.Timestamp) -> pd.Timestamp:
    """UTC instant of the fx-day open (18:00 ET) that `ts` belongs to. Same DST-safe (+6h)
    convention as strategy._fx_day: the 6h span 18:00->midnight never crosses the 02:00 jump."""
    et = pd.Timestamp(ts).tz_convert("America/New_York")
    day0 = (et + pd.Timedelta(hours=6)).normalize()          # fx-day id (midnight of the shifted day)
    return (day0 - pd.Timedelta(hours=6)).tz_convert("UTC")  # back to the 18:00 ET wall-clock open


def _after_loss_gate(cfg, live_conn, sig) -> str | None:
    """AFTER-LOSS exec gate (TALOS_ICHI_EXEC_AFTER_LOSS_ONLY; 2026-07-07 backtest — TALOS-ICHI.md changelog).
    Enter ONLY when the SAME fx-day's previous SETTLED paper trade (mode='talos_ichi') closed NEGATIVE:
    the day's first signal and after-a-win signals are skipped. Exec-only overlay — the paper feed
    keeps trading everything, which is exactly what makes "previous trade" well-defined here.
    2026 (Binance-vol): 204tr +53.6R PF1.37 @taker vs full 398tr +27.1R PF1.09; loose definition
    (any pnl_r<0, incl. session/time exits) tested BETTER than strict SL-only. ⚠️ NOT a regime
    shield: 2024/2025 multi-year OOS stays negative (softer, not positive).
    Returns None to trade, else a human-readable skip reason. Fail-CLOSED on malformed rows
    (an unreadable previous trade means the premise is unverifiable -> skip)."""
    if not cfg.after_loss_only:
        return None
    st_time = pd.Timestamp(sig["signal_time"])
    day_open = _fx_day_open_utc(st_time)
    cur = live_conn.cursor()
    cur.execute("""
        SELECT context FROM ict_trade.signals
        WHERE mode='talos_ichi' AND symbol=%s AND signal_time >= %s AND signal_time < %s
        ORDER BY signal_time DESC LIMIT 1
    """, (sig["symbol"], day_open.to_pydatetime(), st_time.to_pydatetime()))
    row = cur.fetchone()
    cur.close()
    if row is None:
        return "after-loss gate: günün ilk işlemi (bu fx-gününde önceki işlem yok)"
    ctx = row[0]
    if isinstance(ctx, str):
        try:
            ctx = json.loads(ctx)
        except ValueError:
            ctx = {}
    ctx = ctx or {}
    if ctx.get("pos") != "closed":
        return "after-loss gate: önceki işlem henüz kapanmamış görünüyor"
    r = ctx.get("pnl_r")
    if r is None:
        return "after-loss gate: önceki işlemin pnl_r kaydı yok"
    if float(r) >= 0:
        return f"after-loss gate: önceki işlem kazançlı kapandı ({float(r):+.2f}R)"
    return None


def _mark_gate(cfg, live_conn, sig, now, *, skipped: bool, reason: str | None) -> None:
    """Persist the gate decision onto the paper signal row (context.exec_gate) and, on a SKIP,
    Telegram/push-alert ONCE per signal. The atomic jsonb merge guarded by `? 'exec_gate'` is the
    dedup: the signal sits in the 15-min entry window and would otherwise re-alert every tick.
    The UI (MidasXLivePage 'Kapı Kararları') renders this same key, so one write feeds both.
    NB: canli's _track_open_positions does a read-modify-write of the whole context; its cron
    offset (:20s vs our :35s) makes a clobber unlikely, and the `?` guard simply re-marks (worst
    case one duplicate alert) — harmless."""
    payload = {"exec_gate": {"skipped": skipped, "reason": reason,
                             "at": str(pd.Timestamp(now).floor("s"))}}
    cur = live_conn.cursor()
    cur.execute("""
        UPDATE ict_trade.signals
        SET context = COALESCE(context,'{}'::jsonb) || %s::jsonb
        WHERE mode='talos_ichi' AND symbol=%s AND signal_time=%s
          AND NOT (COALESCE(context,'{}'::jsonb) ? 'exec_gate')
        RETURNING id
    """, (json.dumps(payload), sig["symbol"], pd.Timestamp(sig["signal_time"]).to_pydatetime()))
    first_mark = cur.fetchone() is not None
    live_conn.commit()
    cur.close()
    if skipped and first_mark:
        d = str(sig["direction"]).upper()
        arrow = "🟢 LONG ▲" if d == "LONG" else "🔴 SHORT ▼"
        _alert(cfg, live_conn,
               f"🚧 <b>{cfg.exec_name}</b> · <b>{sig['symbol']}</b> {arrow} sinyali <b>AÇILMADI</b>\n"
               f"Sebep: {reason}\n"
               f"<i>Kayıp-sonrası kapısı: yalnız aynı fx-gününün önceki işlemi zararla kapandıysa "
               f"emir açılır. Paper akışı bu işlemi izlemeye devam ediyor.</i>",
               title="Kapı: sinyal atlandı", kind="system")


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
                 client_order_id=coid, order_id=resp.get("orderId"), payload=resp,
                 user_id=pos.get("user_id"))
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
                     client_order_id=resp.get("clientAlgoId"), order_id=resp.get("algoId"), payload=resp,
                     user_id=pos.get("user_id"))
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
def _abandon_entry(cfg, client, conn, pos, coid, status, reason: str, now) -> None:
    """Cancel whatever entry leg is resting and mark the position CANCELLED. reason is 'slipped'
    (price ran past entry_max_slip_r) or 'unfilled' (deadline hit with no fill and no taker
    fallback left). Both are silent misses of a live signal, so they get a forensic order row."""
    sym = pos["symbol"]
    if status in ("NEW", "PARTIALLY_FILLED"):
        try:
            client.cancel_order(sym, client_order_id=coid)
        except BinanceError:
            pass
    st.patch(conn, pos["id"], state=st.CANCELLED, exit_reason=reason, exit_time=now)
    st.log_order(conn, position_id=pos["id"], symbol=sym, leg="entry", action="cancel",
                 client_order_id=coid, payload={"reason": reason, "order_status": status},
                 user_id=pos.get("user_id"))
    _alert(cfg, conn, f"⏭️ <b>GİRİŞ İPTAL</b> · <b>{sym}</b> {str(pos['direction']).upper()} #{pos['id']}\n"
                      f"maker limit {'fiyat kaçtı (+%.2gR)' % cfg.entry_max_slip_r if reason == 'slipped' else 'dolmadı (süre doldu)'}"
                      f" — {_tag(cfg)}", kind="entry")
    print(f"  ⏭️ {sym} entry {reason} — cancelled")


def _manage_entry(cfg, client, conn, xi, pos, now, shared: SharedTick | None = None) -> None:
    sym = pos["symbol"]
    sign = _sign(pos["direction"])
    signal_entry = float(pos["signal_entry"])
    risk0 = float(pos["risk0"])
    coid = pos.get("entry_coid") or st.coid(pos["id"], "entry", 0)
    o = _get_order(client, sym, coid)
    status = (o or {}).get("status")

    if status == "FILLED":
        avg = float(o.get("avgPrice") or 0) or signal_entry
        _enter_open(cfg, client, conn, xi, pos, avg, _order_fill_time(o, now), o, now)
        return

    last = _last_price(sym, now, shared)
    slipped = last is not None and ((last - signal_entry) * sign) > cfg.entry_max_slip_r * risk0
    dl = pos.get("entry_deadline")
    expired = dl is not None and now > pd.Timestamp(dl).tz_convert("UTC")

    # Price ran past the tolerance — abandon regardless of the clock. Chasing is how a +0.5R
    # signal turns into a −0.5R one.
    if slipped:
        _abandon_entry(cfg, client, conn, pos, coid, status, "slipped", now)
        return

    # ---- maker→taker FALLBACK (2026-07-08, pos#47 post-mortem): the resting GTX only fills on an
    # adverse comeback; if it's still unfilled after entry_taker_fallback_sec but price is STILL
    # within the slip tolerance (checked above), missing the trade costs more than the taker fee —
    # cancel the GTX and go MARKET. Partial fills are excluded (the partial leg is a real position;
    # the normal FILLED/slip paths handle it). Cancel/fill race is re-checked before the MARKET send.
    #
    # Evaluated BEFORE `expired` (2026-07-08, pos#1 post-mortem): entry_timeout_sec,
    # entry_taker_fallback_sec and the cron period are all 60s-aligned and phase-locked to the same
    # second, so a tick can land a few hundred ms short of [created+fallback, deadline] and then
    # trip `expired` on the next one. On pos#1 the nominally-60s window caught ZERO ticks and the
    # signal was cancelled having never reached the exchange. `slipped` is False here, so price is
    # in tolerance: a late tick must still take the trade, not drop it.
    if (cfg.maker_entry and cfg.entry_taker_fallback_sec > 0 and dl is not None
            and status != "PARTIALLY_FILLED" and not _ctx(pos).get("taker_fallback")):
        created = pd.Timestamp(dl).tz_convert("UTC") - pd.Timedelta(seconds=cfg.entry_timeout_sec)
        if now >= created + pd.Timedelta(seconds=cfg.entry_taker_fallback_sec):
            if status == "NEW":
                try:
                    client.cancel_order(sym, client_order_id=coid)
                except BinanceError:
                    pass
                o2 = _get_order(client, sym, coid)   # cancel/fill race: it may have JUST filled
                if o2 and (o2.get("status") == "FILLED" or float(o2.get("executedQty") or 0) > 0):
                    avg = float(o2.get("avgPrice") or 0) or signal_entry
                    _enter_open(cfg, client, conn, xi, pos, avg, _order_fill_time(o2, now), o2, now)
                    return
            ctx = _ctx(pos); ctx["taker_fallback"] = True
            st.patch(conn, pos["id"], context=ctx)
            pos["context"] = ctx
            print(f"  ⚡ {sym} maker→taker fallback ({cfg.entry_taker_fallback_sec}s dolmadı, fiyat toleransta)")
            _place_entry(cfg, client, conn, xi, pos, now, taker=True)
            return

    # Deadline reached with no fallback left: it's disabled, it already fired (a MARKET that never
    # came back), or a partial leg is resting. Bounds the taker attempt too.
    if expired:
        _abandon_entry(cfg, client, conn, pos, coid, status, "unfilled", now)
        return

    if status in ("NEW", "PARTIALLY_FILLED"):
        if pos["state"] != st.ENTRY_WORKING:
            st.patch(conn, pos["id"], state=st.ENTRY_WORKING, entry_coid=coid,
                     entry_order_id=(o or {}).get("orderId"))
        return

    # once the fallback fired, any re-place stays TAKER (e.g. a rejected MARKET retried next tick)
    _place_entry(cfg, client, conn, xi, pos, now, taker=bool(_ctx(pos).get("taker_fallback")))


def _place_entry(cfg, client, conn, xi, pos, now, taker: bool = False) -> None:
    sym = pos["symbol"]
    _ensure_account(cfg, client, sym)
    # Auto-leverage (OPUS rule, 2026-07-07): per-trade leverage from the SL distance so the
    # liquidation sits ~2x the SL distance beyond entry (1/L ≈ 2*SL%) — liquidation can NEVER
    # precede the −1R stop, so the loss stays $risk_usd. Capped at leverage_max. Risk is fixed
    # by qty (risk_usd/|entry−sl|); leverage only sets the margin + liquidation distance.
    # Gold's tiny SL% (~0.1-0.4%) means this effectively pins the cap — which is the point:
    # minimum margin per entry on the shared wallet.
    lev = cfg.leverage
    if cfg.armed and cfg.auto_leverage:
        entry_ref = float(pos["signal_entry"])
        slpct = (abs(entry_ref - float(pos["signal_sl"])) / entry_ref) if entry_ref else 0.0
        if slpct > 0:
            lev = max(1, min(cfg.leverage_max, int(0.5 / slpct)))
        try:
            client.set_leverage(sym, lev)
        except BinanceError as e:
            _alert(cfg, conn, f"⚠️ <b>{sym}</b> set_leverage({lev}) hata: {e} — {cfg.leverage}x'e düşüldü",
                   kind="system")
            lev = cfg.leverage
        if lev != int(pos.get("leverage") or 0):
            st.patch(conn, pos["id"], leverage=lev)
            pos["leverage"] = lev
    qty = float(pos["qty"])
    coid = st.coid(pos["id"], "entry", 1 if taker else 0)   # fallback MARKET gets its own coid gen
    params = dict(symbol=sym, side=_side(pos["direction"]), quantity=qty, newClientOrderId=coid)
    if cfg.maker_entry and not taker:
        price = xi.round_price(sym, float(pos["signal_entry"]), mode="nearest")
        params.update(type="LIMIT", timeInForce="GTX", price=price)
    else:
        params.update(type="MARKET")
    try:
        resp = client.new_order(**params)
    except BinanceError as e:
        if e.code in (-2010, -5022) and cfg.maker_entry and not taker:
            # Post-only cross (2026-07-08, pos#1 post-mortem). The rejection PROVES the book is
            # already at-or-better than signal_entry — a BUY limit above the ask, a SELL below the
            # bid. So the GTX can only ever come to rest once price has moved AGAINST the signal
            # (the adverse-selection trap), and re-sending the identical price next tick is a
            # deterministic no-op loop: pos#1 burned its entire entry window this way and never
            # reached the exchange. _manage_entry's `slipped` guard has already established price is
            # inside tolerance, and here it is on the FAVOURABLE side of the reference. Take it.
            ctx = _ctx(pos); ctx["taker_fallback"] = True
            st.patch(conn, pos["id"], context=ctx)
            pos["context"] = ctx
            st.log_order(conn, position_id=pos["id"], symbol=sym, leg="entry", action="reject",
                         client_order_id=coid,
                         payload={"err": str(e), "code": e.code, "escalate": "taker",
                                  "gtx_price": params.get("price")},
                         user_id=pos.get("user_id"))
            _alert(cfg, conn, f"⚡ <b>{sym}</b> {str(pos['direction']).upper()} #{pos['id']}: maker limit piyasayı "
                              f"keserdi (fiyat lehte) → taker girişe geçildi — {_tag(cfg)}", kind="entry")
            print(f"  ⚡ {sym} GTX would cross (price favourable) — escalating to taker")
            _place_entry(cfg, client, conn, xi, pos, now, taker=True)
            return
        if e.code == -4411:                                 # account hasn't accepted the TradFi-Perps agreement
            print(f"  ✋ {sym} gold trading blocked: sign the Binance 'TradFi-Perps agreement' on this "
                  f"account (one-time) before TALOS-ICHI-X can place orders.")
            st.log_order(conn, position_id=pos["id"], symbol=sym, leg="entry", action="error",
                         client_order_id=coid, payload={"err": str(e)}, user_id=pos.get("user_id"))
            _alert(cfg, conn, f"✋ <b>{sym}</b> TALOS-ICHI-X: hesap 'TradFi-Perps' sözleşmesini imzalamamış — Binance'te "
                              f"altın işlemi için bir kereliğine onayla (aksi halde emir gitmez) — {_tag(cfg)}",
                   kind="system")
            return
        print(f"  ! {sym} entry place error: {e}")
        st.log_order(conn, position_id=pos["id"], symbol=sym, leg="entry", action="error",
                     client_order_id=coid, payload={"err": str(e)}, user_id=pos.get("user_id"))
        return
    st.log_order(conn, position_id=pos["id"], symbol=sym, leg="entry", action="place",
                 client_order_id=coid, order_id=resp.get("orderId"), payload=resp,
                 user_id=pos.get("user_id"))
    if resp.get("status") == "FILLED":
        avg = float(resp.get("avgPrice") or 0) or float(pos["signal_entry"])
        _enter_open(cfg, client, conn, xi, pos, avg, now, resp, now)
    else:
        st.patch(conn, pos["id"], state=st.ENTRY_WORKING, entry_coid=coid, entry_order_id=resp.get("orderId"))
        print(f"  ⏳ {sym} {'taker (fallback) entry sent' if taker else 'maker entry resting'} @ "
              f"{params.get('price', 'MARKET')}")


def _enter_open(cfg, client, conn, xi, pos, avg: float, fill_time, resp, now) -> None:
    sym = pos["symbol"]
    time_stop = pd.Timestamp(fill_time) + pd.Timedelta(minutes=M.MAX_HOLD_MIN)
    ctx = _ctx(pos)
    ctx.update(init_sl=float(pos["signal_sl"]), placed_sl=None, pos="open")
    st.patch(conn, pos["id"], state=st.OPEN, eff_entry=avg, entry_fill_time=fill_time, entry_fill_px=avg,
             time_stop_at=time_stop,
             entry_coid=(resp or {}).get("clientOrderId") or st.coid(pos["id"], "entry", 0),
             entry_order_id=(resp or {}).get("orderId"), context=ctx)
    if _place_protective_stop(cfg, client, conn, xi, pos, float(pos["signal_sl"])):
        ctx["placed_sl"] = float(pos["signal_sl"])
        st.patch(conn, pos["id"], context=ctx)
    lev = int(pos.get("leverage") or cfg.leverage)
    _alert(cfg, conn, f"✅ <b>GİRİŞ</b> · <b>{sym}</b> {str(pos['direction']).upper()} #{pos['id']}\n"
                      f"giriş {avg:g} · {float(pos['qty']):g} adet (${float(pos['qty'])*avg:.0f}) · risk ${cfg.risk_usd:g}"
                      f" · {lev}x{' (oto)' if cfg.auto_leverage else ''}\n"
                      f"SL {float(pos['signal_sl']):g} (−1R · 1.5·ATR) · 3.5·ATR iz-süren · 8s/seans "
                      f"({'borsa STOP' if not cfg.testnet else 'sentetik'}) — {_tag(cfg)}", kind="entry")
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
        # userTrades can LAG the just-sent exit MARKET order by a beat, and _realized_since returns
        # 0.0 both on lag and on BinanceError — a premature read was written back permanently as
        # realized_r=0.000 (seen on positions #3/#6, 2026-07-03/06). If the walk says the position
        # was NOT breakeven but the income sum reads 0, retry briefly before accepting it.
        if realized_usd == 0.0 and qty > 0 and abs(res_pnl_r or 0) > 0.02:
            for _ in range(3):
                time.sleep(2)
                realized_usd = _realized_since(client, sym, pos.get("entry_fill_time"))
                if realized_usd != 0.0:
                    break
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
    _alert(cfg, conn, f"{emoji} <b>KAPANDI</b> · <b>{sym}</b> {str(pos['direction']).upper()} #{pos['id']}\n"
                      f"Çıkış {exit_px:g} ({label}) · <b>{r_txt}</b>{usd_txt} — {_tag(cfg)}", kind="exit")
    print(f"  🏁 {sym} CLOSED {r_txt} ({reason})")


def _reconcile(cfg, client, conn, bt, xi, pos, now, shared: SharedTick | None = None) -> None:
    sym = pos["symbol"]
    state = pos["state"]
    if state in (st.PENDING_ENTRY, st.ENTRY_WORKING):
        _manage_entry(cfg, client, conn, xi, pos, now, shared)
        return
    if state != st.OPEN:
        return

    # exchange truth wins: DB says OPEN but Binance is flat -> the resting stop fired (mainnet) or a
    # manual/liquidation close happened. Finalize from realizedPnl instead of looping.
    if pos.get("entry_fill_time") and _position_amt(client, sym) == 0:
        _finalize(cfg, client, conn, bt, pos, reason="closed_externally",
                  exit_px=_last_price(sym, now, shared), exit_time=now, res_pnl_r=None, now=now)
        return

    # the trailing engine — the SAME call the paper canli.py drives (parity by construction)
    res = M.track_open(pd.Timestamp(pos["entry_fill_time"]), _sign(pos["direction"]),
                       float(pos["signal_entry"]), float(pos["signal_sl"]), now)
    if res is None:
        tstop = pos.get("time_stop_at")
        if tstop and now >= pd.Timestamp(tstop).tz_convert("UTC"):   # data-gap fallback past the 8h cap
            _finalize(cfg, client, conn, bt, pos, reason="time", exit_px=_last_price(sym, now, shared),
                      exit_time=now, res_pnl_r=None, now=now)
        return
    if res["status"] == "closed":
        _finalize(cfg, client, conn, bt, pos, reason=res["reason"], exit_px=float(res["exit_px"]),
                  exit_time=res.get("exit_time"), res_pnl_r=res.get("pnl_r"), now=now)
        return
    _update_trailing(cfg, client, conn, xi, pos, res, now)


# ------------------------------------------------------------------ new signal -> position
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


def _create(cfg, xi, live, sig, now, shared: SharedTick | None = None) -> int | None:
    sym = sig["symbol"]; direction = sig["direction"]
    qty, risk0, skip = _size_screen(cfg, xi, sig)
    if skip:
        print(f"  · {sym} SKIP: {skip}")
        return None
    in_sess = shared.in_session() if shared is not None else _in_session(now)
    if not in_sess:
        print(f"  · {sym} SKIP: out of FX-gold session")
        return None
    entry = float(sig["entry"]); sl = float(sig["sl"])
    sign = _sign(direction)
    tp_ref = entry + sign * M.TP_REF_MULT * risk0
    ctx = {"strategy": "TALOS-ICHI Keltner-Trend (live, Binance)", "kind": "trailing", "init_sl": sl,
           "tp_ref": tp_ref, "trail_mult": M.TRAIL_MULT, "atr_mult": M.ATR_INIT_MULT,
           "pos": "open", "paper": False}
    pos_id = st.create_position(
        live, symbol=sym, signal_time=pd.Timestamp(sig["signal_time"]), direction=direction,
        side=_side(direction), signal_entry=entry, signal_sl=sl, risk0=risk0, qty=qty,
        leverage=cfg.leverage, entry_deadline=now + pd.Timedelta(seconds=cfg.entry_timeout_sec),
        version=cfg.exec_version, context=ctx,
        user_id=cfg.user_id, network=_net(cfg) if cfg.user_id else None)
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
        want = set(cfg.symbols)
        entry_times = _open_entry_times(conn, want, uid, net if uid else None)   # funding since entry
        for r in client.position_risk():
            sym = r.get("symbol")
            amt = float(r.get("positionAmt", 0) or 0)
            if sym not in want and amt == 0:
                continue
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
    sym_filter = [cfg.symbol] if uid is None else None      # user mode reconciles ALL their rows
    bt_conn = bt if cfg.is_canonical else None              # writeback = canonical/owner only

    client = _client(cfg)
    try:
        off = shared.sync_client(client)
        xi = shared.xi_for(client)
    except BinanceError as e:
        print(f"  [{label}] fatal exchangeInfo/time: {e}")
        return
    f = xi.get(cfg.symbol)
    print(f"  [{label}/{net}] offset {off:+d}ms | {cfg.symbol} "
          f"tradable={xi.is_tradable(cfg.symbol, allow=ALLOW_CONTRACTS)} "
          f"(type={getattr(f, 'contract_type', '?')} status={getattr(f, 'status', '?')}) | "
          f"risk ${cfg.risk_usd:g}", flush=True)

    # ---- kill switch: flatten everything, drop the flag, disable — nothing else this tick
    if user is not None and user.kill_requested:
        n = 0
        if armed:
            try:
                n = ks.flatten_positions(cfg, client, live, user_id=uid, network=net, reason="killswitch")
            except Exception as e:  # noqa: BLE001
                print(f"  [{label}] kill flatten error: {e}")
        ustore.clear_kill(live, user.settings_id)
        ustore.audit(live, uid, "kill_executed", {"stream": "talos_ichi", "network": net, "flattened": n})
        _alert(cfg, live, f"🟥 <b>ACİL DURDUR</b> · {n} pozisyon kapatıldı, TALOS-ICHI/{net} devre dışı bırakıldı — {_tag(cfg)}",
               title="Acil durdurma tamamlandı", kind="system")
        return

    # ---- entry gates: activation + daily loss cap (reconcile ALWAYS continues below)
    entries_ok = armed and (user is None or user.entries_allowed)
    if entries_ok and user is not None and user.daily_loss_cap_usd:
        lost = ustore.realized_today_usd(live, uid, net, "talos_ichi")
        if lost <= -float(user.daily_loss_cap_usd):
            entries_ok = False
            if not ustore.daily_pause_notified(live, uid, "talos_ichi"):
                ustore.audit(live, uid, "daily_loss_pause",
                             {"stream": "talos_ichi", "network": net, "lost_usd": lost,
                              "cap_usd": user.daily_loss_cap_usd})
                _alert(cfg, live, f"⛔ Günlük zarar limiti aşıldı ({lost:+.2f}$ ≤ −{user.daily_loss_cap_usd:g}$) — "
                                  f"bugün yeni işlem açılmayacak. Açık pozisyonlar yönetilmeye devam ediyor.",
                       title="Günlük zarar limiti", kind="system")

    sigs = shared.signals(live, cfg.symbol)
    print(f"  [{label}] {len(sigs)} recent talos_ichi signal(s) in window")

    if not armed:
        for sig in sigs:
            gate_skip = _after_loss_gate(cfg, live, sig)
            if gate_skip:
                print(f"  · {sig['symbol']:<9} {sig['direction'].upper():<5} SKIP: {gate_skip}")
                continue
            _log_intent(cfg, xi, sig, now)
    else:
        if (entries_ok and sigs
                and st.count_open(live, sym_filter, user_id=uid, network=net if uid else None) == 0):
            gate_skip = _after_loss_gate(cfg, live, sigs[0])
            if gate_skip:
                print(f"  · {cfg.symbol} SKIP: {gate_skip}")
                _mark_gate(cfg, live, sigs[0], now, skipped=True, reason=gate_skip)
            else:
                if cfg.after_loss_only:
                    _mark_gate(cfg, live, sigs[0], now, skipped=False, reason=None)
                _create(cfg, xi, live, sigs[0], now, shared)    # single position: newest fresh signal only
        for pos in st.fetch_open(live, sym_filter, user_id=uid, network=net if uid else None):
            try:
                _reconcile(cfg, client, live, bt_conn, xi, pos, now, shared)
            except BinanceError as e:
                print(f"  ! {pos['symbol']} reconcile error: {e}")
                _alert(cfg, live, f"⚠️ <b>{pos['symbol']}</b> TALOS-ICHI reconcile error: {e}", kind="system")

    if cfg.api_key and cfg.api_secret:
        _write_snapshot(cfg, client, live)
        print(f"  [{label}] snapshot written ({net})")


# ------------------------------------------------------------------ main
def main():
    base = cfgmod.load_cfg()
    now = pd.Timestamp.now(tz="UTC")
    armed = base.armed
    head = ("ARMED (LIVE ORDERS)" if armed else
            ("DRY-RUN (no orders)" if base.dry_run else "HALTED (disabled)"))
    net = "testnet" if base.testnet else "MAINNET"
    print(f"=== {_tag(base)} executor @ {now:%Y-%m-%d %H:%M}Z | {head} | {net} | {base.symbol} "
          f"risk ${base.risk_usd:g} {base.leverage}x {base.margin_type} | maker={base.maker_entry} | "
          f"{'MULTI-USER' if base.multi_user else 'single (env)'} ===", flush=True)

    if not (base.trading_enabled and base.exec_enabled) and not base.dry_run:
        print("[halt] LIVE_TRADING_ENABLED / TALOS_ICHI_EXEC_ENABLED false and not a dry-run — no-op.")
        return

    live = tsc.live_conn()
    bt = tsc.backtest_conn() if armed else None
    shared = SharedTick(now)

    if base.multi_user:
        try:
            users = ustore.load_exec_users(live, "talos_ichi")
        except Exception as e:  # noqa: BLE001
            print(f"[fatal] load_exec_users: {e}")
            notify.alert(f"⚠️ {_tag(base)} executor: kullanıcılar yüklenemedi: {e}", chat_id=base.telegram_chat_id)
            live.close()
            if bt:
                bt.close()
            return
        print(f"  {len(users)} exec user-network row(s) loaded")
        for u in users:
            try:
                _run_tick(cfgmod.cfg_for_user(base, u), u, live, bt, shared, now)
            except Exception as e:  # noqa: BLE001 — one user can NEVER break another's reconcile
                print(f"  ! user {u.email}/{u.network} tick error: {e}")
                notify.alert(f"⚠️ {_tag(base)} exec kullanıcı hatası · {u.email}/{u.network}: {e}",
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
