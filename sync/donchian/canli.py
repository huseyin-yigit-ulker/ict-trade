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
try:
    import push_notify                       # noqa: E402  (Web Push sibling of Telegram)
except Exception:                            # never let push imports break the emitter
    push_notify = None

HTF = "4h"                                   # trend-context label written to ict_trade.signals
TF_MINUTES = {"15m": 15, "30m": 30, "1h": 60, "4h": 240}
# history (days) per timeframe to cover the 55-bar channel + ER(24) + buffer
FETCH_DAYS = {"15m": 12, "30m": 22, "1h": 40, "4h": 160}


def _telegram_send(text_msg: str) -> bool:
    """Push a signal alert to the same Telegram bot the DAG uses (token/chat from .env).
    Best-effort: never let a notification failure break the emit. Returns True if Telegram
    accepted the message (so the caller can mark tg_sent and not retry)."""
    env = tsc._read_env()
    token = env.get("TELEGRAM_BOT_TOKEN")
    chat = env.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        print("  telegram skipped (TELEGRAM_BOT_TOKEN/CHAT_ID not set)")
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": text_msg, "parse_mode": "HTML"},
                          timeout=15)
        if not r.ok:
            print(f"  telegram error: {r.text[:150]}")
        return bool(r.ok)
    except Exception as e:  # noqa: BLE001
        print(f"  telegram exception: {e}")
        return False


def _telegram_text(s: "strat.DonSignal", tf: str = "1h", confirm_htf: str | None = None,
                   name: str | None = None) -> str:
    """DONCHIAN-labelled alert so the receiver knows the signal's source strategy, its
    timeframe (1h vs 30m look otherwise identical) AND, for the hybrid stream, that a
    higher-tf trend confirmation gated it."""
    rr = abs(s.take_profit_1 - s.entry) / abs(s.entry - s.stop_loss)
    arrow = "🟢 LONG ▲" if s.direction == "long" else "🔴 SHORT ▼"
    label = f"{tf}+{confirm_htf}" if confirm_htf else tf
    # Signal FIRE time = the bar CLOSE (signal_time is the bar OPEN). This is the canonical
    # signal time the UI shows + the entry reference — include it so the alert matches the UI
    # regardless of WHEN Telegram delivered it (the message's own timestamp = emit time, which
    # can lag the fire time until the directional gate confirms).
    fire = s.timestamp + pd.Timedelta(minutes=TF_MINUTES[tf])
    fire_utc = fire.tz_convert("UTC") if fire.tz is not None else fire.tz_localize("UTC")
    tag = f"🏷️ <b>{name}</b> · " if name else ""          # strategy display name (OPUS/FABLE) prefix
    if confirm_htf:
        head = f"{tag}⛰️ <b>DONCHIAN {tf} + {confirm_htf} ONAY</b> — Hybrid Trend Breakout"
        logic = (f"{tf} 55-bar kırılım + <b>{confirm_htf} trend yönü onayı</b> "
                 f"(fiyat {confirm_htf} Donchian orta çizgisinin {('üstünde' if s.direction=='long' else 'altında')})")
        src = f"DONCHIAN {tf}+{confirm_htf} (hybrid)"
    else:
        head = f"{tag}⛰️ <b>DONCHIAN {tf}</b> — Trend Breakout"
        logic = f"55-bar kırılım ({tf}), güçlü trend"
        src = f"DONCHIAN {tf}"
    return (
        f"{head}\n"
        f"<b>{s.symbol}</b>  {arrow}  <code>{label}</code>\n"
        f"Sinyal saati: <code>{fire_utc:%Y-%m-%d %H:%M} UTC</code> (bar kapanışı)\n"
        f"Giriş: <code>{s.entry:.6g}</code>\n"
        f"SL: <code>{s.stop_loss:.6g}</code>\n"
        f"TP: <code>{s.take_profit_1:.6g}</code>  (RR 1:{rr:.0f})\n"
        f"ER: {s.er:.2f}  |  {logic}\n"
        f"<i>🤖 Sinyal {src} stratejisi tarafından üretildi</i>"
    )

_GET_CTX = """SELECT context FROM ict_trade.signals
              WHERE symbol=%s AND signal_time=%s AND direction=%s AND mode=%s LIMIT 1"""
_UPDATE_CTX = """UPDATE ict_trade.signals SET context = CAST(%s AS JSONB)
                 WHERE symbol=%s AND signal_time=%s AND direction=%s AND mode=%s"""
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
    return strat.us_hours_gate(fresh, sym, tf)   # US perps: only during US market hours


_VOLD: dict = {}
def _vol_change(sym: str, ts, k: int) -> float | None:
    """Daily volume change at signal time: mean(vol[d-k:d]) / mean(vol[d-2k:d-k]), both windows
    ending strictly BEFORE the signal day (no lookahead). >1 = expanding, <1 = contracting."""
    import numpy as _np
    if sym not in _VOLD:
        d = tsc.fetch_klines(sym, "1d",
                             int((pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=400)).timestamp() * 1000),
                             int(pd.Timestamp.now(tz="UTC").timestamp() * 1000))
        v = None
        if d is not None and not d.empty:
            v = d["volume"].astype(float); v.index = pd.to_datetime(v.index, utc=True).normalize()
        _VOLD[sym] = v
    v = _VOLD[sym]
    if v is None:
        return None
    day = pd.Timestamp(ts)
    day = (day.tz_localize("UTC") if day.tz is None else day.tz_convert("UTC")).normalize()
    prior = v.loc[v.index < day]
    if len(prior) < 2 * k:
        return None
    older = prior.iloc[-2 * k:-k].mean()
    return float(prior.iloc[-k:].mean() / older) if older > 0 else None


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
    ap.add_argument("--name", default=None,
                    help="strategy display name (e.g. OPUS) prefixed to the Telegram alert head")
    ap.add_argument("--telegram-symbols", default=None,
                    help="comma-separated symbols; if set, ONLY these symbols' formations send a "
                         "Telegram alert (all signals still write to the DB). Limits pings to the "
                         "live-traded set, e.g. FETUSDT,SUSDT,SOLUSDT.")
    ap.add_argument("--rr", type=float, default=strat.RR,
                    help=f"reward/risk target (default {strat.RR}); non-4 appends its int to "
                         f"the mode tag, e.g. --rr 6 -> 'dch30_4h6'")
    ap.add_argument("--volume-gate", type=float, default=None,
                    help="VOLUME-CONTRACTION gate: only emit signals whose symbol's daily volume is "
                         "contracting at signal time (vol[d-K:d]/vol[d-2K:d-K] < THR, no lookahead). "
                         "Appends 'vg' to the mode tag, e.g. dch30_4h -> 'dch30_4hvg'. Lower SL-rate "
                         "twin of d30so8f3h7 (version='d30so8f3vg').")
    ap.add_argument("--volume-gate-k", type=int, default=10, help="vol-change window in days (default 10)")
    args = ap.parse_args()
    tg_syms = ({s.strip().upper() for s in args.telegram_symbols.split(",") if s.strip()}
               if args.telegram_symbols else None)

    tf = args.tf
    confirm_htf = args.confirm_htf
    mode = strat.hybrid_tag(tf, confirm_htf) if confirm_htf else strat.mode_for(tf)
    if int(args.rr) != int(strat.RR):
        mode += str(int(args.rr))
    if args.volume_gate is not None:
        mode += "vg"
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

    # Emit IMMEDIATELY at the bar close (no confirmation gate) so the signal appears on the
    # dashboard right away (entry = breakout close = the price at that moment). The directional
    # confirmation (favourable buf*risk before adverse buf*risk = "price didn't reverse into the
    # entry→SL zone toward the stop") is then tracked LIVE by the UI (Sinyal Bekliyor → Aktif /
    # İptal Ters Yön), re-checked by the nightly prune (deletes reversed/expired rows), and the
    # daily resolve writes ONLY confirmed breakouts to the backtest version. The TELEGRAM alert is
    # sent AT FORMATION (bar close) too — NOT gated on the +0.5R confirmation — so every setup is
    # alerted the moment its 30m+4h / 1h bar closes; the 0.5R direction check is the UI/live module's
    # job. tg_sent guards against duplicate alerts on re-scan (a failed send retries next run).
    if args.volume_gate is not None:
        kept = []
        for s in found:
            vc = _vol_change(s.symbol, s.timestamp, args.volume_gate_k)
            if vc is not None and vc < args.volume_gate:
                kept.append(s)
        print(f"  volume-gate <{args.volume_gate:g} (K={args.volume_gate_k}d): "
              f"kept {len(kept)}/{len(found)}", flush=True)
        found = kept

    print(f"\n{len(found)} fresh signal(s).")
    # (Removed) the per-run "⚙️ <stream> çalıştı · HH:MM UTC · N sinyal" Telegram ping that fired on
    # EVERY emit run (signal or not, ~120 msgs/day) — pure run-status noise. Only the actual
    # new-signal alert below (a real setup at bar close) is sent now.
    if args.dry_run or not found:
        if args.dry_run:
            print("[dry-run] no DB write.")
        return

    conn = tsc.live_conn()
    cur = conn.cursor()
    inserted = alerted = 0
    for s in found:
        d = s.direction.upper()
        st = s.timestamp.to_pydatetime()
        cur.execute(_GET_CTX, (s.symbol, st, d, mode))
        existing = cur.fetchone()
        if existing is None:                               # new -> write NOW (appears on dashboard)
            ctx = {**(s.context or {}), "tg_sent": False}
            cur.execute(_INSERT, (s.symbol, d, float(s.entry), float(s.stop_loss),
                                  float(s.take_profit_1), st, mode, tf, confirm_htf or HTF,
                                  s.strategy, s.quality, int(s.confluence_score), json.dumps(ctx)))
            conn.commit()
            inserted += 1
            print(f"  + {s.symbol:<10} {d:<5} @ {st:%m-%d %H:%M} yazıldı", flush=True)
            # Kişisel sinyal-izleme push'u — TÜM taranan evren için (owner Telegram
            # gate'inden bağımsız); yalnız bu (strateji,sembol)'ü listesine ekleyen
            # kullanıcılara kuyruğa yazar, --drain dağıtır. No-op until push configured.
            if push_notify is not None:
                push_notify.push_signal_watchers(
                    mode, s.symbol,
                    title=f"PUSU · {(args.name or mode)} {s.symbol} {d}",
                    body=f"Formasyon @ {float(s.entry):g} · SL {float(s.stop_loss):g} · TP {float(s.take_profit_1):g}",
                    url="/", tag=f"{mode}:{s.symbol}",
                )
        else:
            raw = existing[0]
            ctx = raw if isinstance(raw, dict) else (json.loads(raw) if raw else {})
        # Telegram alert at FORMATION (bar close) — no +0.5R gate (the UI/live module does that).
        # tg_sent prevents duplicate alerts on re-scan; a failed send stays False to retry next run.
        if not ctx.get("tg_sent"):
            # gated symbols (not in --telegram-symbols) are marked sent WITHOUT pinging, so they
            # don't spam and don't retry every run — only the live-traded set actually alerts.
            gated = args.no_telegram or (tg_syms is not None and s.symbol.upper() not in tg_syms)
            ok = True if gated else _telegram_send(_telegram_text(s, tf, confirm_htf, name=args.name))
            if ok:
                ctx["tg_sent"] = True
                cur.execute(_UPDATE_CTX, (json.dumps(ctx), s.symbol, st, d, mode))
                conn.commit()
                if not gated:
                    alerted += 1
                    print(f"  📣 {s.symbol:<10} {d:<5} → Telegram", flush=True)
                    # Native phone push alongside Telegram (no-op until push is configured).
                    if push_notify is not None:
                        push_notify.send_push(
                            title=f"PUSU · {(args.name or mode)} {s.symbol} {d}",
                            body=f"Formasyon @ {float(s.entry):g} · SL {float(s.stop_loss):g} · TP {float(s.take_profit_1):g}",
                            url="/", tag=f"{mode}:{s.symbol}",
                        )
    cur.close()
    conn.close()
    print(f"  {inserted} new row(s), {alerted} Telegram alert(s) (mode='{mode}')")


if __name__ == "__main__":
    main()
