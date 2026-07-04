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
try:
    import push_notify                                # noqa: E402  (Web Push sibling of Telegram)
except Exception:                                     # never let push imports break the emitter
    push_notify = None

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
        # still open -> store the trailing-stop path (live chart) + alert. step<=0: on EVERY trailing-stop
        # change; step>0: on each locked-R milestone. Message carries trade + trailing-stop detail.
        locked = res["locked_r"]
        prev_sl = ctx.get("cur_sl")                    # last stored stop (None on the very first run)
        new_sl = res["cur_sl"]
        ctx.update({"cur_sl": new_sl, "best": res["best"], "locked_r": round(locked, 2),
                    "pos": "open", "trail": res["trail"], "init_sl": res["init_sl"]})
        changed = False
        if step <= 0:
            base = ctx.get("notif_sl", float(sl))      # last NOTIFIED stop level
            moved = (new_sl - base) if side > 0 else (base - new_sl)
            if moved > 1e-6:                           # the stop ratcheted favourably -> alert
                changed = True; ctx["notif_sl"] = new_sl
        else:
            m = math.floor(locked / step)
            if locked >= 0 and m > ctx.get("sl_milestone", -999):
                changed = True; ctx["sl_milestone"] = m
        if changed:
            if not no_telegram:
                arrow = "🟢 LONG ▲" if side > 0 else "🔴 SHORT ▼"
                mins = int(res.get("minutes_open", 0)); dur = f"{mins // 60}sa {mins % 60}dk"
                state = "breakeven üstü ✅" if locked >= 0 else "breakeven altı ⏳"
                delta = "" if prev_sl is None else f"  (önceki <code>{prev_sl:.2f}</code>, +{abs(new_sl - prev_sl):.2f})"
                _telegram_send(
                    f"🔁 <b>{NAME}</b> · XAUUSDT {arrow} · <b>iz-süren stop güncellendi</b>\n"
                    f"Giriş <code>{float(entry):.2f}</code> → Anlık <code>{res['last_price']:.2f}</code>\n"
                    f"Yeni stop: <code>{new_sl:.2f}</code>{delta}\n"
                    f"Kilitli: <b>{'+' if locked >= 0 else ''}{locked:.2f}R</b> · {state} · Süre {dur}")
            sl_msgs += 1
            print(f"  🔁 {sym} {d} SL→{new_sl:.2f} · {locked:+.2f}R", flush=True)
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
    # SINGLE-POSITION rule, DB-AUTHORITATIVE. The live table is the source of truth for "are we in a
    # position": if an OPEN midas row already exists (pos != closed, within the 8h max-hold window),
    # emit NOTHING — _track_open_positions manages it to its trailing-stop / 8h / session exit (same
    # OR opposite setups are IGNORED; MIDAS does not reverse). Previously this leaned on current_open
    # (a re-derivation from a sliding 10h walk) which returns None in chop even while positions are
    # open, so latest_setup fired a NEW setup every few minutes and piled up conflicting long+short
    # phantom positions. Only look for a fresh setup when the book is actually FLAT.
    conn = None if args.dry_run else tsc.live_conn()
    has_open = False
    if conn is not None:
        gcur = conn.cursor()
        gcur.execute("""SELECT 1 FROM ict_trade.signals WHERE mode=%s
                        AND COALESCE(context->>'pos','open') <> 'closed'
                        AND signal_time >= %s LIMIT 1""",
                     (MODE, (now - pd.Timedelta(minutes=M.MAX_HOLD_MIN + 60)).to_pydatetime()))
        has_open = gcur.fetchone() is not None
        gcur.close()
    if has_open:
        sigs = []
    else:
        op = M.current_open(now)        # self-heal: surface an open trade whose formation alert we missed
        sigs = [op] if op is not None else M.latest_setup(now, lookback_min=int(args.lookback_min))
    print(f"=== MIDAS CANLI @ {now:%Y-%m-%d %H:%M}Z | XAUUSDT 1m | lookback={args.lookback_min:g}m | "
          f"mode='{MODE}'{' · IN POSITION (no new emit)' if has_open else ''} ===", flush=True)
    for s in sigs:
        fire = s["signal_time"] + pd.Timedelta(minutes=1)
        print(f"  XAUUSDT {s['direction'].upper():<5} @ {fire:%m-%d %H:%M} "
              f"entry={s['entry']:.2f} sl={s['sl']:.2f} tp~={s['tp']:.2f}", flush=True)
    print(f"\n{len(sigs)} fresh setup(s).")
    if args.dry_run:
        print("[dry-run] no DB write / no tracking.")
        return

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
                        # Native phone push alongside Telegram (no-op until push is configured).
                        if push_notify is not None:
                            push_notify.send_push(
                                title=f"PUSU · {NAME} XAUUSDT {d}",
                                body=f"Formasyon @ {float(s['entry']):g} · SL {float(s['sl']):g} · TP {float(s['tp']):g}",
                                url="/binance-altin", tag=f"{MODE}:XAUUSDT",
                            )
        cur.close()

    # Track OPEN positions -> SL-ratchet + exit alerts (runs every invocation, even with no new setup)
    sl_msgs, exits = _track_open_positions(conn, now, args.no_telegram, step=args.sl_step)
    conn.close()
    print(f"  {inserted} new · {alerted} formation-alert · {sl_msgs} SL-update · {exits} exit (mode='{MODE}')")


if __name__ == "__main__":
    main()
