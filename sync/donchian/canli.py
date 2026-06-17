"""Donchian strategy — CANLI (live) submodule.

Generates today's Donchian(55) breakout signals from fresh 1h klines and writes them to
the LIVE dashboard table ict_trade.signals with mode='donchian'. The nightly ETL
(sync/sync_daily.py) later resolves mode='donchian' rows into backtest version='donchian'
— same path every other live stream takes.

Only fires on FULLY CLOSED 1h bars (the still-forming candle Binance returns last is
dropped). Idempotent: dedup on (symbol, signal_time, direction, mode) mirrors dag.py's
save_signal_to_db, so re-running within the lookback window never duplicates.

    python sync/donchian/canli.py --dry-run                    # print fresh signals, no write
    python sync/donchian/canli.py --emit                       # insert into ict_trade.signals
    python sync/donchian/canli.py --emit --lookback-hours 6    # also (re)emit recent closed bars
    python sync/donchian/canli.py --emit --symbols BTCUSDT XAUUSDT
"""
from __future__ import annotations

import sys
import json
import argparse
from pathlib import Path

import pandas as pd
import requests

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))   # sync/        -> trade_sync_common
sys.path.insert(0, str(_HERE.parent))        # sync/donchian -> strategy
import trade_sync_common as tsc              # noqa: E402
import strategy as strat                     # noqa: E402

HTF = "4h"                                   # trend-context label written to ict_trade.signals
TF_MINUTES = {"15m": 15, "30m": 30, "1h": 60, "4h": 240}
# history (days) per timeframe to cover the 55-bar channel + ER(24) + buffer
FETCH_DAYS = {"15m": 12, "30m": 22, "1h": 40, "4h": 160}


def _telegram_send(text_msg: str) -> None:
    """Push a signal alert to the same Telegram bot the DAG uses (token/chat from .env).
    Best-effort: never let a notification failure break the emit."""
    env = tsc._read_env()
    token = env.get("TELEGRAM_BOT_TOKEN")
    chat = env.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        print("  telegram skipped (TELEGRAM_BOT_TOKEN/CHAT_ID not set)")
        return
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": text_msg, "parse_mode": "HTML"},
                          timeout=15)
        if not r.ok:
            print(f"  telegram error: {r.text[:150]}")
    except Exception as e:  # noqa: BLE001
        print(f"  telegram exception: {e}")


def _telegram_text(s: "strat.DonSignal", tf: str = "1h", confirm_htf: str | None = None) -> str:
    """DONCHIAN-labelled alert so the receiver knows the signal's source strategy, its
    timeframe (1h vs 30m look otherwise identical) AND, for the hybrid stream, that a
    higher-tf trend confirmation gated it."""
    rr = abs(s.take_profit_1 - s.entry) / abs(s.entry - s.stop_loss)
    arrow = "🟢 LONG ▲" if s.direction == "long" else "🔴 SHORT ▼"
    label = f"{tf}+{confirm_htf}" if confirm_htf else tf
    if confirm_htf:
        head = f"⛰️ <b>DONCHIAN {tf} + {confirm_htf} ONAY</b> — Hybrid Trend Breakout"
        logic = (f"{tf} 55-bar kırılım + <b>{confirm_htf} trend yönü onayı</b> "
                 f"(fiyat {confirm_htf} Donchian orta çizgisinin {('üstünde' if s.direction=='long' else 'altında')})")
        src = f"DONCHIAN {tf}+{confirm_htf} (hybrid)"
    else:
        head = f"⛰️ <b>DONCHIAN {tf}</b> — Trend Breakout"
        logic = f"55-bar kırılım ({tf}), güçlü trend"
        src = f"DONCHIAN {tf}"
    return (
        f"{head}\n"
        f"<b>{s.symbol}</b>  {arrow}  <code>{label}</code>\n"
        f"Giriş: <code>{s.entry:.6g}</code>\n"
        f"SL: <code>{s.stop_loss:.6g}</code>\n"
        f"TP: <code>{s.take_profit_1:.6g}</code>  (RR 1:{rr:.0f})\n"
        f"ER: {s.er:.2f}  |  {logic}\n"
        f"<i>🤖 Sinyal {src} stratejisi tarafından üretildi</i>"
    )

_EXISTS = """SELECT 1 FROM ict_trade.signals
             WHERE symbol=%s AND signal_time=%s AND direction=%s AND mode=%s LIMIT 1"""
_INSERT = """INSERT INTO ict_trade.signals
    (symbol, direction, entry, sl, tp, signal_time, mode, ltf_timeframe, htf_timeframe,
     strategy, quality, confluence_score, context)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, CAST(%s AS JSONB))"""


def fresh_signals(sym: str, now: pd.Timestamp, lookback: pd.Timedelta,
                  tf: str = "1h", confirm_htf: str | None = None,
                  rr: float = strat.RR) -> list[strat.DonSignal]:
    """Donchian signals on `tf` bars that CLOSED within [now-lookback, now].

    If confirm_htf is set ('4h'), only breakouts whose direction agrees with that higher
    timeframe's trend are emitted (strat.htf_confirm) — the hybrid stream. rr sets the
    reward/risk target (TP distance)."""
    bar = pd.Timedelta(minutes=TF_MINUTES[tf])
    df = tsc.fetch_klines(sym, tf, int((now - pd.Timedelta(days=FETCH_DAYS[tf])).timestamp() * 1000),
                          int(now.timestamp() * 1000))
    if df is None or df.empty:
        return []
    # drop the still-forming candle: keep bars whose close (open + bar) is in the past
    closed = df[df.index + bar <= now]
    if closed.empty:
        return []
    sigs = strat.generate_signals(closed, sym, rr=rr)
    floor = now - lookback
    # bar CLOSE = timestamp + bar must fall inside the lookback window
    fresh = [s for s in sigs if floor <= s.timestamp + bar <= now]
    if confirm_htf and fresh:
        hdf = tsc.fetch_klines(sym, confirm_htf,
                               int((now - pd.Timedelta(days=FETCH_DAYS[confirm_htf])).timestamp() * 1000),
                               int(now.timestamp() * 1000))
        fresh = strat.htf_confirm(fresh, tf, hdf, confirm_htf)
    return fresh


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--emit", action="store_true")
    ap.add_argument("--symbols", nargs="*", default=strat.SYMBOLS)
    ap.add_argument("--tf", default="1h", choices=sorted(TF_MINUTES),
                    help="signal timeframe (default 1h)")
    ap.add_argument("--confirm-htf", default=None, choices=["1h", "4h"],
                    help="HYBRID: emit only breakouts aligned with this higher tf's trend "
                         "direction (e.g. 4h) -> mode='dch<base>_<htf>'")
    ap.add_argument("--lookback-hours", type=float, default=1.5,
                    help="emit signals whose bar closed within this many hours (default 1.5)")
    ap.add_argument("--no-telegram", action="store_true",
                    help="skip Telegram alerts (for back-filling past signals into the live table)")
    ap.add_argument("--rr", type=float, default=strat.RR,
                    help=f"reward/risk target (default {strat.RR}); non-4 appends its int to "
                         f"the mode tag, e.g. --rr 6 -> 'dch30_4h6'")
    args = ap.parse_args()

    tf = args.tf
    confirm_htf = args.confirm_htf
    mode = strat.hybrid_tag(tf, confirm_htf) if confirm_htf else strat.mode_for(tf)
    if int(args.rr) != int(strat.RR):
        mode += str(int(args.rr))
    now = pd.Timestamp.now(tz="UTC")
    lookback = pd.Timedelta(hours=args.lookback_hours)
    htf_note = f" +{confirm_htf}-dir" if confirm_htf else ""
    print(f"=== Donchian CANLI @ {now:%Y-%m-%d %H:%M}Z | tf={tf}{htf_note} RR={args.rr:g} | "
          f"{len(args.symbols)} symbols | lookback={args.lookback_hours}h | mode='{mode}' ===", flush=True)

    found: list[strat.DonSignal] = []
    for sym in args.symbols:
        try:
            sigs = fresh_signals(sym, now, lookback, tf, confirm_htf, args.rr)
            for s in sigs:
                rr_disp = abs(s.take_profit_1 - s.entry) / abs(s.entry - s.stop_loss)
                print(f"  {sym:<10} {s.direction.upper():<5} @ {s.timestamp:%m-%d %H:%M} "
                      f"entry={s.entry:.6g} sl={s.stop_loss:.6g} tp={s.take_profit_1:.6g} "
                      f"RR={rr_disp:.1f} ER={s.er:.2f}", flush=True)
            found += sigs
        except Exception as e:  # noqa: BLE001
            print(f"  ! {sym}: {e}", flush=True)

    print(f"\n{len(found)} fresh signal(s).")
    if args.dry_run or not found:
        if args.dry_run:
            print("[dry-run] no DB write.")
        return

    conn = tsc.live_conn()
    cur = conn.cursor()
    inserted = 0
    for s in found:
        d = s.direction.upper()
        st = s.timestamp.to_pydatetime()
        cur.execute(_EXISTS, (s.symbol, st, d, mode))
        if cur.fetchone():
            print(f"  dup {s.symbol} {d} @ {st} (skipped)")
            continue
        cur.execute(_INSERT, (s.symbol, d, float(s.entry), float(s.stop_loss),
                              float(s.take_profit_1), st, mode, tf, confirm_htf or HTF,
                              s.strategy, s.quality, int(s.confluence_score),
                              json.dumps(s.context or {})))
        conn.commit()                         # commit before notifying (DB is source of truth)
        inserted += 1
        if not args.no_telegram:
            _telegram_send(_telegram_text(s, tf, confirm_htf))  # alert incl. tf + HTF-confirm note
    cur.close()
    conn.close()
    print(f"  inserted {inserted} new row(s) into ict_trade.signals (mode='{mode}')")


if __name__ == "__main__":
    main()
