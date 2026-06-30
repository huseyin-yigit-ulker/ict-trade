"""MIDAS — CANLI (live) submodule. Gold-only (XAUUSDT) VWAP-trend setups -> ict_trade.signals
mode='midas', so the dashboard shows them live (PAPER feed). Fires only on FULLY-CLOSED 1m bars
during real FX-gold market hours. Idempotent on (symbol, signal_time, direction, mode).

This is a PAPER signal feed: it surfaces the entry + initial 1.5*ATR stop + a nominal trail-distance
target. The AUTHORITATIVE outcome (3.5*ATR trailing / 8h / session exit) is the nightly backtest
(version='midas', sync/midas/backfill.py) — a 1m trailing stop can't be tracked by the signal-and-
fixed-TP live model. The real-money executor is NOT touched.

    python sync/midas/canli.py --dry-run
    python sync/midas/canli.py --emit
    python sync/midas/canli.py --emit --lookback-min 10 --no-telegram
"""
from __future__ import annotations
import sys
import json
import math
import argparse
from pathlib import Path

import pandas as pd
import requests

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent))                 # sync/midas -> strategy
sys.path.insert(0, str(_HERE.parents[1]))             # sync/      -> trade_sync_common
import strategy as M                                  # noqa: E402
import trade_sync_common as tsc                       # noqa: E402

MODE = "midas"
LTF = "1m"
HTF = "1m"
NAME = "MIDAS"

_GET_CTX = """SELECT context FROM ict_trade.signals
              WHERE symbol=%s AND signal_time=%s AND direction=%s AND mode=%s LIMIT 1"""
_UPDATE_CTX = """UPDATE ict_trade.signals SET context = CAST(%s AS JSONB)
                 WHERE symbol=%s AND signal_time=%s AND direction=%s AND mode=%s"""
_INSERT = """INSERT INTO ict_trade.signals
    (symbol, direction, entry, sl, tp, signal_time, mode, ltf_timeframe, htf_timeframe,
     strategy, quality, confluence_score, context)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, CAST(%s AS JSONB))"""


def _telegram_send(text_msg: str) -> bool:
    env = tsc._read_env()
    token = env.get("TELEGRAM_BOT_TOKEN"); chat = env.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        print("  telegram skipped (token/chat not set)"); return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": text_msg, "parse_mode": "HTML"}, timeout=15)
        if not r.ok:
            print(f"  telegram error: {r.text[:150]}")
        return bool(r.ok)
    except Exception as e:  # noqa: BLE001
        print(f"  telegram exception: {e}"); return False


def _telegram_text(s: dict, fire_utc: pd.Timestamp) -> str:
    arrow = "🟢 LONG ▲" if s["direction"] == "long" else "🔴 SHORT ▼"
    return (
        f"🏷️ <b>{NAME}</b> · 🥇 <b>ALTIN VWAP-TREND</b> — Pullback Continuation\n"
        f"<b>XAUUSDT</b>  {arrow}  <code>1m</code>\n"
        f"Sinyal saati: <code>{fire_utc:%Y-%m-%d %H:%M} UTC</code> (bar kapanışı)\n"
        f"Giriş: <code>{s['entry']:.2f}</code>\n"
        f"SL (1R · 1.5·ATR): <code>{s['sl']:.2f}</code>\n"
        f"Çıkış: 3.5·ATR iz-süren stop · 8s · seans-sonu — <b>sabit hedef YOK</b>\n"
        f"<i>🤖 MIDAS · trend yönünde VWAP'a geri çekilme; gün-içi kapanır (PAPER)</i>"
    )


def _track_open_positions(conn, now, no_telegram, step=0.5):
    """For each OPEN MIDAS position, replay its trailing stop to `now` and alert on each new locked-R
    milestone (breakeven, +step, +2·step, …) and on exit. State lives in the row's context jsonb.
    step<=0 -> alert on ANY trailing-stop change (once it locks profit)."""
    cur = conn.cursor()
    cur.execute("""SELECT symbol, direction, entry, sl, signal_time, context
                   FROM ict_trade.signals WHERE mode=%s AND signal_time >= %s
                   AND COALESCE(context->>'pos','open') <> 'closed' ORDER BY signal_time""",
                (MODE, (now - pd.Timedelta(days=2)).to_pydatetime()))
    rows = cur.fetchall()
    sl_msgs = exits = 0
    for sym, d, entry, sl, st, ctx in rows:
        ctx = ctx if isinstance(ctx, dict) else (json.loads(ctx) if ctx else {})
        side = 1 if str(d).upper() == "LONG" else -1
        fill = pd.Timestamp(st) + pd.Timedelta(minutes=1)        # next-open fill
        res = M.track_open(fill, side, float(entry), float(sl), now)
        if res is None:
            continue
        if res["status"] == "closed":
            r = res["pnl_r"]; emoji = "✅" if r >= 0 else "❌"
            reason = {"trail/stop": "iz-süren stop", "time": "8s süre",
                      "session": "seans sonu"}.get(res["reason"], res["reason"])
            if not no_telegram:
                _telegram_send(f"{emoji} <b>{NAME}</b> · XAUUSDT {d} KAPANDI\n"
                               f"Çıkış: <code>{res['exit_px']:.2f}</code> ({reason})\n"
                               f"Sonuç: <b>{'+' if r >= 0 else ''}{r:.2f}R</b>")
            ctx.update({"pos": "closed", "exit_px": res["exit_px"], "pnl_r": round(r, 2)})
            cur.execute(_UPDATE_CTX, (json.dumps(ctx), sym, st, d, MODE)); conn.commit()
            exits += 1
            print(f"  ✓ {sym} {d} KAPANDI {r:+.2f}R ({res['reason']})", flush=True)
            continue
        # still open -> store the trailing-stop path (for the live chart) + alert on a new locked-R milestone
        locked = res["locked_r"]
        ctx.update({"cur_sl": res["cur_sl"], "best": res["best"], "locked_r": round(locked, 2),
                    "pos": "open", "trail": res["trail"], "init_sl": res["init_sl"]})
        changed = False; lab = ""
        if step <= 0:
            if locked >= 0 and abs(res["cur_sl"] - ctx.get("notif_sl", float(sl))) > 1e-6:
                changed = True; lab = f"kilitli +{locked:.2f}R"; ctx["notif_sl"] = res["cur_sl"]
        else:
            m = math.floor(locked / step)
            if locked >= 0 and m > ctx.get("sl_milestone", -999):
                changed = True
                lab = "breakeven (risk sıfır)" if m == 0 else f"kilitli +{m*step:.1f}R"
                ctx["sl_milestone"] = m
        if changed:
            if not no_telegram:
                _telegram_send(f"🔁 <b>{NAME}</b> · XAUUSDT {d} · SL güncellendi\n"
                               f"Yeni iz-süren stop: <code>{res['cur_sl']:.2f}</code>\n"
                               f"Durum: <b>{lab}</b>  (anlık {res['last_price']:.2f})")
            sl_msgs += 1
            print(f"  🔁 {sym} {d} SL→{res['cur_sl']:.2f} · {lab}", flush=True)
        cur.execute(_UPDATE_CTX, (json.dumps(ctx), sym, st, d, MODE)); conn.commit()
    cur.close()
    return sl_msgs, exits


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--emit", action="store_true")
    ap.add_argument("--lookback-min", type=float, default=10,
                    help="emit setups whose 1m bar closed within this many minutes (default 10)")
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--sl-step", type=float, default=0.5,
                    help="alert on each +N R locked-profit milestone as the trailing stop ratchets "
                         "(default 0.5R; use 0 to alert on EVERY stop change once in profit)")
    args = ap.parse_args()

    now = pd.Timestamp.now(tz="UTC")
    op = M.current_open(now)
    if op is not None:
        # SINGLE-POSITION rule — matches the backtest EXACTLY: while a position is OPEN, IGNORE all
        # new setups (same OR opposite direction). MIDAS does NOT reverse on an opposite signal (tested:
        # reversing hurts — the trailing stop manages the exit). Only the open position is emitted/tracked.
        sigs = [op]
    else:
        sigs = M.latest_setup(now, lookback_min=int(args.lookback_min))
    print(f"=== MIDAS CANLI @ {now:%Y-%m-%d %H:%M}Z | XAUUSDT 1m | "
          f"lookback={args.lookback_min:g}m | mode='{MODE}' ===", flush=True)
    for s in sigs:
        fire = s["signal_time"] + pd.Timedelta(minutes=1)
        print(f"  XAUUSDT {s['direction'].upper():<5} @ {fire:%m-%d %H:%M} "
              f"entry={s['entry']:.2f} sl={s['sl']:.2f} tp~={s['tp']:.2f}", flush=True)
    print(f"\n{len(sigs)} fresh setup(s).")
    if args.dry_run:
        print("[dry-run] no DB write / no tracking.")
        return

    conn = tsc.live_conn()
    inserted = alerted = 0
    if sigs:
        cur = conn.cursor()
        for s in sigs:
            d = s["direction"].upper()
            st = s["signal_time"].to_pydatetime()
            fire = s["signal_time"] + pd.Timedelta(minutes=1)
            cur.execute(_GET_CTX, (M.SYMBOL, st, d, MODE))
            existing = cur.fetchone()
            if existing is None:
                ctx = {"tg_sent": False, "strategy": "MIDAS VWAP-Trend", "paper": True, "pos": "open"}
                cur.execute(_INSERT, (M.SYMBOL, d, float(s["entry"]), float(s["sl"]), float(s["tp"]),
                                      st, MODE, LTF, HTF, "MIDAS VWAP-Trend", "TREND", 0, json.dumps(ctx)))
                conn.commit(); inserted += 1
                print(f"  + XAUUSDT {d:<5} @ {fire:%m-%d %H:%M} yazıldı", flush=True)
            else:
                raw = existing[0]
                ctx = raw if isinstance(raw, dict) else (json.loads(raw) if raw else {})
            if not ctx.get("tg_sent"):
                ok = True if args.no_telegram else _telegram_send(_telegram_text(s, fire))
                if ok:
                    ctx["tg_sent"] = True
                    cur.execute(_UPDATE_CTX, (json.dumps(ctx), M.SYMBOL, st, d, MODE)); conn.commit()
                    if not args.no_telegram:
                        alerted += 1
                        print(f"  📣 XAUUSDT {d:<5} → Telegram", flush=True)
        cur.close()

    # Track OPEN positions -> SL-ratchet + exit alerts (runs every invocation, even with no new setup)
    sl_msgs, exits = _track_open_positions(conn, now, args.no_telegram, step=args.sl_step)
    conn.close()
    print(f"  {inserted} new · {alerted} formation-alert · {sl_msgs} SL-update · {exits} exit (mode='{MODE}')")


if __name__ == "__main__":
    main()
