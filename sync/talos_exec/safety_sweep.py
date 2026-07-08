"""Independent TALOS safety sweep (cron #2) — guarantees the gold position is never left unwatched.

Runs on its own schedule, separate from the executor, and is SCOPED to TALOS's symbol only (XAUUSDT)
so it can never touch the OPUS/Donchian positions (and vice-versa). For the TALOS symbol it checks:
  1. ORPHAN — a Binance XAUUSDT position with no managed talos_positions row (flatten + alert),
  2. reconciler-freshness — TALOS's own XAUUSDT snapshot is stale, so the 8h/session time-exits (which
     depend on the cron running) aren't being enforced (alert),
  3. clock skew vs Binance within recvWindow.
Read-only unless it finds a breach; disabled/dry-run makes it a pure reporter.

MULTI-USER (EXEC_MULTI_USER=true): the per-account sweep loops over every loadable
user_stream_settings row (stream='talos'), each with their own keys and their own talos_positions
scope, isolated per user; the reconciler-freshness check stays GLOBAL (one stale executor endangers
every account equally).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve()
# our own dir MUST be front-most (config.py/state.py also exist in sync/live_exec) — insert it LAST.
sys.path.insert(0, str(_HERE.parents[1] / "live_exec"))
sys.path.insert(0, str(_HERE.parents[1]))
sys.path.insert(0, str(_HERE.parents[1] / "users"))
sys.path.insert(0, str(_HERE.parent))
import trade_sync_common as tsc                      # noqa: E402
import config as cfgmod                              # noqa: E402
import state as st                                   # noqa: E402
import notify                                        # noqa: E402
import store as ustore                               # noqa: E402  (sync/users)
from binance_futures import BinanceFutures, BinanceError   # noqa: E402


def _market_flatten(client, sym, amt):
    side = "SELL" if amt > 0 else "BUY"
    try:
        client.new_order(symbol=sym, side=side, type="MARKET", quantity=abs(amt), reduceOnly="true")
    except BinanceError as e:
        print(f"  ! flatten {sym}: {e}")


def _sweep_account(cfg, live, skew_seen: set) -> int:
    """The original per-account sweep: orphan check on the TALOS symbol for ONE account
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
        notify.alert(f"⚠️ TALOS clock skew {off:+d}ms (> recvWindow risk)", chat_id=cfg.telegram_chat_id)
        print(f"  ! clock skew {off:+d}ms")

    if not (cfg.api_key and cfg.api_secret):
        print(f"  [{label}] no API keys — report-only, nothing to sweep.")
        return 0

    managed = {p["symbol"]: p for p in st.fetch_open(live, [cfg.symbol], user_id=uid,
                                                     network=net if uid else None)}
    breaches = 0

    # (1) ORPHAN — a TALOS-symbol position on Binance with no managed talos_positions row.
    amt = 0.0
    try:
        positions = client.position_risk(cfg.symbol)
    except BinanceError as e:
        print(f"  [{label}] positionRisk: {e}")
        return 0
    for p in positions:
        if p.get("symbol") == cfg.symbol:
            amt = float(p.get("positionAmt", 0) or 0)
    if amt != 0 and managed.get(cfg.symbol) is None:
        breaches += 1
        print(f"  🚨 [{label}] ORPHAN {cfg.symbol} amt={amt} (no talos_positions row)")
        if cfg.armed:
            try:
                client.cancel_all_open_orders(cfg.symbol)
            except BinanceError:
                pass
            _market_flatten(client, cfg.symbol, amt)
        notify.alert(f"🚨 <b>{cfg.symbol}</b> TALOS ORPHAN {'flattened' if cfg.armed else '(report-only)'} ({amt})"
                     + (f" · {label}/{net}" if uid else ""),
                     chat_id=cfg.telegram_chat_id)
        if uid:
            ustore.push_user(live, uid, "Sahipsiz pozisyon kapatıldı",
                             f"{cfg.symbol} ({amt}) hesabınızda yönetilmeyen pozisyondu — kapatıldı.",
                             kind="system")

    print(f"  [{label}/{net}] swept {len(managed)} managed | breaches={breaches}")
    return breaches


def main():
    cfg = cfgmod.load_cfg()
    now = pd.Timestamp.now(tz="UTC")
    print(f"=== TALOS ({cfg.exec_version}) safety sweep @ {now:%Y-%m-%d %H:%M}Z | {cfg.symbol} | "
          f"{'ARMED' if cfg.armed else 'REPORT-ONLY'} | "
          f"{'MULTI-USER' if cfg.multi_user else 'single (env)'} ===", flush=True)

    live = tsc.live_conn()
    skew_seen: set = set()
    total_managed = len(st.fetch_open(live, [cfg.symbol]))

    if cfg.multi_user:
        try:
            users = ustore.load_exec_users(live, "talos")
        except Exception as e:  # noqa: BLE001
            print(f"[fatal] load_exec_users: {e}")
            notify.alert(f"⚠️ TALOS sweep: kullanıcılar yüklenemedi: {e}", chat_id=cfg.telegram_chat_id)
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

    # (2) reconciler-freshness (GLOBAL) — TALOS writes its own XAUUSDT snapshot each run (OPUS never
    # trades gold), so this staleness is INDEPENDENT of the OPUS executor. A dead TALOS cron =
    # unenforced 8h/session exit for EVERY account at once.
    cur = live.cursor()
    cur.execute("SELECT extract(epoch FROM now() - max(updated_at)) FROM ict_trade.live_account_snapshot "
                "WHERE symbol=%s", (cfg.symbol,))
    row = cur.fetchone(); cur.close()
    stale_s = float(row[0]) if row and row[0] is not None else None
    if total_managed and stale_s is not None and stale_s > 360:   # >6 min since TALOS last ran
        print(f"  ⚠️ TALOS reconciler stale {stale_s:.0f}s with {total_managed} open position(s)")
        notify.alert(f"⚠️ TALOS executor {stale_s/60:.0f}dk’dır çalışmıyor, {cfg.symbol} pozisyonu korumasız!",
                     chat_id=cfg.telegram_chat_id)

    live.close()


if __name__ == "__main__":
    main()
