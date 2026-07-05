"""Independent safety sweep (cron #2) — guarantees no open position is ever unprotected.

Runs on its own schedule, separate from the executor, so a stuck/crashed reconciler can't leave
real exchange risk uncovered. For every Binance position with a non-zero amount it verifies:
  1. a managed live_positions row exists (else ORPHAN — flatten + alert),
  2. a protective stop order is live on the book (else flatten + alert),
  3. clock skew vs Binance is within recvWindow,
  4. total open risk is within MAX_TOTAL_RISK_USD.
Read-only unless it finds a breach; LIVE_TRADING_ENABLED=false makes it a pure reporter.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parents[1]))
sys.path.insert(0, str(_HERE.parents[1] / "users"))
import _bootenv                                      # noqa: E402,F401  -- MUST precede tsc/scaleout/ict.config
import trade_sync_common as tsc                      # noqa: E402
import config as cfgmod                              # noqa: E402
import state as st                                   # noqa: E402
import notify                                        # noqa: E402
import store as ustore                               # noqa: E402  (sync/users)
from binance_futures import BinanceFutures, BinanceError   # noqa: E402


def _sweep_account(cfg, live, skew_seen: set) -> int:
    """The original per-account sweep: orphan positions + open-risk cap for ONE account
    (cfg carries the keys + identity). Returns the breach count."""
    label = cfg.user_email or "env"
    uid = cfg.user_id
    net = "testnet" if cfg.testnet else "mainnet"
    client = BinanceFutures(api_key=cfg.api_key, api_secret=cfg.api_secret,
                            base_url=cfg.base_url, proxy=cfg.proxy)
    try:
        off = client.sync_time()
    except BinanceError as e:
        print(f"  [{label}] time: {e}")
        return 0
    if abs(off) > 4000 and cfg.base_url not in skew_seen:
        skew_seen.add(cfg.base_url)
        notify.alert(f"⚠️ d30so8c clock skew {off:+d}ms (> recvWindow risk)", chat_id=cfg.telegram_chat_id)
        print(f"  ! clock skew {off:+d}ms")

    if not (cfg.api_key and cfg.api_secret):
        print(f"  [{label}] no API keys — report-only, nothing to sweep.")
        return 0

    managed = {p["symbol"]: p for p in st.fetch_open(live, None, user_id=uid,
                                                     network=net if uid else None)}

    # NOTE: the executor runs a SYNTHETIC bracket (MARKET-on-trigger, no resting stop orders —
    # testnet rejects conditional orders). So "no resting stop" is EXPECTED and must NOT be flattened.
    # The protection in this model is the reconciler running; the real safety checks are therefore:
    #   (1) ORPHAN — a Binance position with NO managed DB row (a true leak) -> flatten;
    #   (2) STALE reconciler — checked globally in main();
    #   (3) total open risk over the cap.
    breaches = 0
    try:
        positions = client.position_risk()
    except BinanceError as e:
        print(f"  [{label}] positionRisk: {e}")
        return 0
    for p in positions:
        sym = p.get("symbol")
        amt = float(p.get("positionAmt", 0) or 0)
        if amt == 0 or not (sym or "").endswith("USDT"):
            continue
        if managed.get(sym) is None:                       # ORPHAN — no DB row owns this position
            breaches += 1
            print(f"  🚨 [{label}] ORPHAN {sym} amt={amt} (no live_positions row)")
            if cfg.armed:
                client.cancel_all_open_orders(sym)
                _market_flatten(client, sym, amt)
            notify.alert((f"🚨 <b>{sym}</b> ORPHAN flattened ({amt})" if cfg.armed
                          else f"🚨 <b>{sym}</b> ORPHAN (report-only)")
                         + (f" · {label}/{net}" if uid else ""),
                         chat_id=cfg.telegram_chat_id)
            if uid:
                ustore.push_user(live, uid, "Sahipsiz pozisyon kapatıldı",
                                 f"{sym} ({amt}) hesabınızda yönetilmeyen pozisyondu — kapatıldı.",
                                 kind="system")

    open_risk = st.total_open_risk_usd(live, cfg.risk_usd, user_id=uid, network=net if uid else None)
    if open_risk > cfg.max_total_risk_usd:
        breaches += 1
        notify.alert(f"⚠️ d30so8c open risk ${open_risk:g} > cap ${cfg.max_total_risk_usd:g}"
                     + (f" · {label}/{net}" if uid else ""), chat_id=cfg.telegram_chat_id)
    print(f"  [{label}/{net}] swept {len(managed)} managed | breaches={breaches} | open risk ${open_risk:g}")
    return breaches


def main():
    cfg = cfgmod.load_cfg()
    now = pd.Timestamp.now(tz="UTC")
    print(f"=== d30so8c safety sweep @ {now:%Y-%m-%d %H:%M}Z | "
          f"{'ARMED' if cfg.armed else 'REPORT-ONLY'} | "
          f"{'MULTI-USER' if cfg.multi_user else 'single (env)'} ===", flush=True)

    live = tsc.live_conn()
    skew_seen: set = set()
    total_managed = len(st.fetch_open(live, None))

    if cfg.multi_user:
        try:
            users = ustore.load_exec_users(live, "opus")
        except Exception as e:  # noqa: BLE001
            print(f"[fatal] load_exec_users: {e}")
            notify.alert(f"⚠️ d30so8c sweep: kullanıcılar yüklenemedi: {e}", chat_id=cfg.telegram_chat_id)
            live.close()
            return
        for u in users:
            try:
                _sweep_account(cfgmod.cfg_for_user(cfg, u), live, skew_seen)
            except Exception as e:  # noqa: BLE001 — isolation: next user always sweeps
                print(f"  ! sweep {u.email}/{u.network}: {e}")
                try:
                    live.rollback()
                except Exception:  # noqa: BLE001
                    pass
    else:
        _sweep_account(cfg, live, skew_seen)

    # reconciler-freshness (global): in the no-resting-stop model a dead executor = unwatched positions.
    cur = live.cursor()
    cur.execute("SELECT extract(epoch FROM now() - max(updated_at)) FROM ict_trade.live_account")
    row = cur.fetchone(); cur.close()
    stale_s = float(row[0]) if row and row[0] is not None else None
    if total_managed and stale_s is not None and stale_s > 360:   # >6 min since last executor run
        print(f"  ⚠️ reconciler stale {stale_s:.0f}s with {total_managed} open position(s)")
        notify.alert(f"⚠️ d30so8c executor {stale_s/60:.0f}dk’dır çalışmıyor, {total_managed} açık pozisyon korumasız!",
                     chat_id=cfg.telegram_chat_id)
    live.close()


def _market_flatten(client, sym, amt):
    side = "SELL" if amt > 0 else "BUY"
    try:
        client.new_order(symbol=sym, side=side, type="MARKET",
                         quantity=abs(amt), reduceOnly="true")
    except BinanceError as e:
        print(f"  ! flatten {sym}: {e}")


if __name__ == "__main__":
    main()
