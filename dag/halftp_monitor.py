"""Live ½TP (partial-take-profit + breakeven) position monitor for the MAIN / IMPULSE
streams — paper-traded, NO real Binance orders.

The live DAG (dag/dag.py) only EMITS signals (entry/SL/TP) and writes them to
ict_trade.signals. This monitor sits on top: it tracks each emitted main (mode='live')
and impulse (mode='impulse') signal through the ½TP lifecycle and reports it as a
"Trade Card" at every milestone — exactly the v3/v4 backtest exit model, but live:

    PENDING ──entry fill──▶ OPEN ──TP/2 touch──▶ PARTIAL ──TP1──▶ CLOSED (winner)
                             │   (scale out 50%,        │  └─BE stop─▶ CLOSED (breakeven)
                             │    pull stop to entry)    │
                             └────original SL───────────────────────▶ CLOSED (loser)

It is a faithful live mirror of backtest/backtester.py `simulate_signal` + `_resolve_partial`
(same touch rules, fees via `_net_r`, worst-case SL-first, ict/config.PARTIAL_TP_*), so a
live-tracked trade resolves to the SAME R the v3/v4 backtest would assign it.

Outputs (per the operator's choice):
  • Telegram main chat  — Trade Cards A/B/C; impulse cards carry a ✨ banner to distinguish.
  • Log file / stdout   — the same cards (cron redirects stdout to ~/ict-halftp.log).
  • Dashboard DB         — on entry fill an 'active' row, on close the resolved row, written
                           to ict_trade.trading_signals under version v3 (main) / v4 (impulse),
                           the dashboard's "MAIN ½TP" / "IMPULSE ½TP" streams.

State (which trades are tracked + which cards already fired) persists in a JSON file between
runs, so the monitor is idempotent and survives restarts. On first sight of an already in-flight
trade it ADOPTS it at its current phase silently (no retro-spam); only milestones reached AFTER
adoption fire a card. Designed to run frequently (cron */5) — it re-resolves each open trade
from full 1m history every pass, so a missed run never loses a milestone.

Usage:
  python dag/halftp_monitor.py                 # one pass (cron)
  python dag/halftp_monitor.py --dry-run       # resolve + print cards, NO Telegram / NO DB
  python dag/halftp_monitor.py --discover-days 5
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "sync"))     # trade_sync_common (also adds backtest/ to path)
import trade_sync_common as tsc            # noqa: E402
from ict import config as C                # noqa: E402  (backtest/ict, via tsc)
from backtester import _net_r             # noqa: E402  (exact fee-aware R, shared with v3/v4)

# ---------------------------------------------------------------- config
STATE_PATH = Path(os.getenv("HALFTP_STATE", str(Path.home() / "ict-halftp-state.json")))
LTF_MINUTES = 60                            # main/impulse signal timeframe (signal close = ts + 60m)
EXPIRY_MINUTES = tsc.EXPIRY_MINUTES         # 180 — entry-fill window (shared with the backtest)
MAX_OPEN_DAYS = 12                          # safety: force-expire a trade still open past this
DISCOVER_DAYS_DEFAULT = 2                   # how far back to pick up newly-emitted signals
PRUNE_AFTER_DAYS = 7                        # drop terminal trades older than this (> discover window)

# Each live stream -> its dashboard ½TP backtest version tag.
STREAMS = [
    {"mode": "live",    "version": "v3", "impulse": False},   # MAIN ½TP
    {"mode": "impulse", "version": "v4", "impulse": True},    # IMPULSE ½TP
]

# Telegram (same env as dag.py; ½TP alerts on by default, impulse -> ✨ banner + main chat).
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or tsc._read_env().get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or tsc._read_env().get("TELEGRAM_CHAT_ID", "")
TELEGRAM_IMPULSE_CHAT_ID = os.getenv("TELEGRAM_IMPULSE_CHAT_ID") or tsc._read_env().get("TELEGRAM_IMPULSE_CHAT_ID", "")
HALFTP_ALERTS_ENABLED = os.getenv("HALFTP_ALERTS", "1").strip().lower() not in ("0", "false", "no", "off")


def log(msg: str) -> None:
    """stdout line; cron redirects this to ~/ict-halftp.log (the operator's log channel)."""
    print(msg, flush=True)


def send_telegram(text: str, *, impulse: bool, dry_run: bool) -> None:
    """Post a card to Telegram. Impulse -> dedicated chat if set, else main chat (✨ banner
    is already baked into `text`). Mirrors dag.send_telegram_message error handling."""
    if dry_run or not HALFTP_ALERTS_ENABLED:
        return
    cid = (TELEGRAM_IMPULSE_CHAT_ID or TELEGRAM_CHAT_ID) if impulse else TELEGRAM_CHAT_ID
    if not (TELEGRAM_BOT_TOKEN and cid):
        log("  telegram skipped (TOKEN/CHAT_ID not set)")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": cid, "text": text, "parse_mode": "HTML"}, timeout=15)
        if not r.ok:
            log(f"  Telegram error: {r.text[:200]}")
    except Exception as e:                                   # network / timeout — never crash the run
        log(f"  Telegram exception: {e}")


# ---------------------------------------------------------------- lifecycle resolver
def _norm_long(direction: str) -> bool:
    return (direction or "").lower() in ("long", "buy")


def resolve_lifecycle(direction: str, entry: float, sl: float, tp: float,
                      df1m: pd.DataFrame, close_ts: pd.Timestamp, *,
                      expiry_minutes: int = EXPIRY_MINUTES) -> dict:
    """Replicate backtester.simulate_signal + _resolve_partial on 1m bars, exposing EVERY
    milestone (entry fill, partial scale-out, final close) — not just the terminal outcome.
    Bar timestamps are the 1m bar CLOSE (index + 1m), matching trade_sync_common._resolve."""
    long = _norm_long(direction)
    cdir = "long" if long else "short"
    risk = abs(entry - sl)
    cf = C.PARTIAL_TP_CLOSE_FRAC
    partial_level = entry + C.PARTIAL_TP_TRIGGER_FRAC * (tp - entry)   # long & short
    res = {"phase": "pending", "entry_time": None, "entry_px": None,
           "partial_time": None, "partial_level": float(partial_level),
           "close_time": None, "close_px": None, "close_reason": None,
           "pnl_r": None, "banked_r": 0.0, "be_armed": False, "risk": float(risk)}
    if df1m is None or df1m.empty:
        return res
    idx = df1m.index
    if idx.tz is None:
        df1m = df1m.copy()
        df1m.index = idx = idx.tz_localize("UTC")
    bar = pd.Timedelta(minutes=1)

    def close_at(i):
        return (df1m.index[i] + bar).to_pydatetime()

    n = len(df1m)
    pos = int(idx.searchsorted(close_ts))               # first 1m bar at/after the signal close
    if pos >= n:
        return res                                       # no data past the signal yet -> pending

    # --- entry-fill scan within the expiry window (limit-style: entry must fill first) -----
    expiry_pos = pos + expiry_minutes
    entry_idx = None
    for i in range(pos, min(expiry_pos, n)):
        hi, lo = df1m.iloc[i]["high"], df1m.iloc[i]["low"]
        if long:
            entry_touched, tp_touched, sl_touched = lo <= entry, hi >= tp, lo <= sl
        else:
            entry_touched, tp_touched, sl_touched = hi >= entry, lo <= tp, hi >= sl
        if not entry_touched and (tp_touched or sl_touched):
            res.update(phase="cancelled", close_reason="invalidated", close_time=close_at(i))
            return res                                   # TP/SL hit before fill -> no trade taken
        if entry_touched:
            entry_idx = i
            break
    if entry_idx is None:
        if n >= expiry_pos:                              # window fully elapsed, never filled
            res.update(phase="cancelled", close_reason="expired")
        return res                                       # else still inside the fill window -> pending

    res.update(phase="open", entry_time=close_at(entry_idx), entry_px=float(entry))

    # --- partial-TP + breakeven lifecycle from the entry bar (mirror _resolve_partial) -----
    partial_done = False
    stop = sl
    for j in range(entry_idx, n):
        hi, lo = df1m.iloc[j]["high"], df1m.iloc[j]["low"]
        if long:
            stop_touched, tp_touched, partial_touched = lo <= stop, hi >= tp, hi >= partial_level
        else:
            stop_touched, tp_touched, partial_touched = hi >= stop, lo <= tp, lo <= partial_level

        if not partial_done:
            if stop_touched and not tp_touched:                          # full stop, no partial
                res.update(phase="closed", close_time=close_at(j), close_px=float(stop),
                           close_reason="original_sl", pnl_r=_net_r(entry, stop, risk, cdir))
                return res
            if tp_touched:                                               # gapped through partial + TP1
                if stop_touched:                                         # worst case: stop first
                    res.update(phase="closed", close_time=close_at(j), close_px=float(stop),
                               close_reason="original_sl", pnl_r=_net_r(entry, stop, risk, cdir))
                    return res
                banked = cf * _net_r(entry, partial_level, risk, cdir)
                pnl = banked + (1 - cf) * _net_r(entry, tp, risk, cdir)
                res.update(phase="closed", close_time=close_at(j), close_px=float(tp),
                           close_reason="tp1", partial_time=close_at(j), banked_r=banked,
                           be_armed=True, pnl_r=pnl)
                return res
            if partial_touched:                                          # scale out 50%, arm breakeven
                partial_done = True
                res.update(phase="partial", partial_time=close_at(j),
                           banked_r=cf * _net_r(entry, partial_level, risk, cdir),
                           be_armed=bool(C.PARTIAL_TP_BREAKEVEN))
                if C.PARTIAL_TP_BREAKEVEN:
                    stop = entry
                continue
        else:                                                            # remainder rides to TP1 / stop
            if tp_touched and not stop_touched:
                pnl = res["banked_r"] + (1 - cf) * _net_r(entry, tp, risk, cdir)
                res.update(phase="closed", close_time=close_at(j), close_px=float(tp),
                           close_reason="tp1", pnl_r=pnl)
                return res
            if stop_touched:                                             # both -> worst case stop first
                pnl = res["banked_r"] + (1 - cf) * _net_r(entry, stop, risk, cdir)
                reason = "breakeven_sl" if stop == entry else "original_sl"
                res.update(phase="closed", close_time=close_at(j), close_px=float(stop),
                           close_reason=reason, pnl_r=pnl)
                return res

    return res                                                           # still open / partial


def milestones_passed(res: dict) -> set:
    """Which trade cards a resolved lifecycle has earned: A=opened, B=partial, C=closed."""
    m = set()
    if res.get("entry_time"):
        m.add("A")
    if res.get("partial_time"):
        m.add("B")
    if res.get("phase") == "closed":
        m.add("C")
    return m


# ---------------------------------------------------------------- trade cards
_REASON_TR = {"tp1": "Nihai TP Vuruldu", "breakeven_sl": "Break-Even SL Vuruldu",
              "original_sl": "İlk SL Vuruldu (kısmi kâr öncesi)"}


def _fmt_ts(ts) -> str:
    if ts is None:
        return "-"
    if isinstance(ts, str):
        ts = pd.Timestamp(ts)
    return pd.Timestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _fmt_dur(a, b) -> str:
    if a is None or b is None:
        return "-"
    secs = int(abs((pd.Timestamp(b) - pd.Timestamp(a)).total_seconds()))
    h, m = secs // 3600, (secs % 3600) // 60
    return f"{h}s {m}dk" if h else f"{m}dk"


def _banner(impulse: bool) -> str:
    return "✨ <b>IMPULSE ½TP</b>\n" if impulse else "🎯 <b>MAIN ½TP</b>\n"


def _g(x, prec=6) -> str:
    return f"{x:.{prec}g}" if isinstance(x, (int, float)) else str(x)


def card_open(pos: dict, res: dict) -> str:
    side = "LONG" if _norm_long(pos["direction"]) else "SHORT"
    rr = pos.get("rr") or 0.0
    halftp_max = (C.PARTIAL_TP_CLOSE_FRAC * C.PARTIAL_TP_TRIGGER_FRAC * rr) + (1 - C.PARTIAL_TP_CLOSE_FRAC) * rr
    return (
        f"{_banner(pos['impulse'])}--- [ YENİ İŞLEM AÇILDI ] ---\n"
        f"Zaman: {_fmt_ts(res['entry_time'])}\n"
        f"Yön: {side} | Varlık: {pos['symbol']}\n"
        f"Giriş Fiyatı (Entry): {_g(pos['entry'])}\n"
        f"Stop-Loss (SL): {_g(pos['sl'])}\n"
        f"Hedef (TP): {_g(pos['tp'])}\n"
        f"Kısmi Kâr Hedefi (TP/2): {_g(res['partial_level'])}\n"
        f"Risk/Ödül (R/R): 1:{rr:.2f}   |   ½TP max ≈ +{halftp_max:.1f}R"
    )


def card_partial(pos: dict, res: dict) -> str:
    return (
        f"{_banner(pos['impulse'])}--- [ KISMİ KÂR ALINDI - GÜVENLİ MOD ] ---\n"
        f"Zaman: {_fmt_ts(res['partial_time'])}\n"
        f"Gerçekleşen Fiyat: {_g(res['partial_level'])}\n"
        f"Aksiyon: Pozisyonun %{int(C.PARTIAL_TP_CLOSE_FRAC*100)}'si kapatıldı. "
        f"Kâr cebe kondu (+{res['banked_r']:.2f}R).\n"
        f"Yeni SL Noktası: {_g(pos['entry'])} (Break-Even yapıldı)\n"
        f"Bekleyen Hedef: {_g(pos['tp'])} (Kalan %{int((1-C.PARTIAL_TP_CLOSE_FRAC)*100)} için)"
    )


def card_close(pos: dict, res: dict) -> str:
    entry_t = res.get("entry_time") or pos.get("signal_time")
    return (
        f"{_banner(pos['impulse'])}--- [ İŞLEM KAPANDI ] ---\n"
        f"Kapanış Zamanı: {_fmt_ts(res['close_time'])}\n"
        f"Kapanış Nedeni: {_REASON_TR.get(res['close_reason'], res['close_reason'])}\n"
        f"Kapanış Fiyatı: {_g(res['close_px'])}\n"
        f"Varlık: {pos['symbol']} ({'LONG' if _norm_long(pos['direction']) else 'SHORT'})\n"
        f"Toplam Gerçekleşen R: {res['pnl_r']:+.2f}R\n"
        f"İşlem Süresi: {_fmt_dur(entry_t, res['close_time'])}"
    )


# ---------------------------------------------------------------- DB (dashboard ½TP stream)
def upsert_dashboard_row(bt, pos: dict, res: dict, *, closed: bool, dry_run: bool) -> None:
    """Write the live ½TP trade into ict_trade.trading_signals under v3/v4 (idempotent upsert
    keyed by symbol+signal_time+trade_type+version) so the dashboard's ½TP drill-down sees it."""
    if dry_run:
        return
    if closed:
        status = "closed_tp" if (res["pnl_r"] or 0) > 0 else "closed_sl"
        outcome = {"status": status, "real_entry_time": res["entry_time"],
                   "exit_time": res["close_time"], "exit_price": res["close_px"],
                   "pnl_r": res["pnl_r"]}
    else:                                                   # entry filled, still running
        outcome = {"status": "active", "real_entry_time": res["entry_time"],
                   "exit_time": None, "exit_price": None, "pnl_r": None}
    row = tsc.build_row(pos["symbol"], pd.Timestamp(pos["signal_time"]), pos["direction"],
                        pos["entry"], pos["sl"], pos["tp"], outcome,
                        strategy=pos.get("strategy"), quality=pos.get("quality"),
                        confluence_score=pos.get("confluence_score"))
    row["version"] = pos["version"]
    try:
        tsc.upsert_rows(bt, [row])
    except Exception as e:                                  # DB hiccup must not abort the whole pass
        log(f"  DB upsert failed for {pos['symbol']} {pos['version']}: {e}")


# ---------------------------------------------------------------- state file
def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception as e:
        log(f"  WARN: state file unreadable ({e}); starting fresh")
        return {}


def save_state(state: dict) -> None:
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=0, default=str))
    tmp.replace(STATE_PATH)                                 # atomic: never leave a half-written file


def trade_key(mode: str, r: dict) -> str:
    st = pd.Timestamp(r["signal_time"]).tz_convert("UTC") if pd.Timestamp(r["signal_time"]).tz \
        else pd.Timestamp(r["signal_time"]).tz_localize("UTC")
    return f"{mode}|{r['symbol']}|{st.isoformat()}|{str(r['direction']).lower()}"


# ---------------------------------------------------------------- discovery
def fetch_recent_signals(live, mode: str, since: pd.Timestamp, until: pd.Timestamp) -> list[dict]:
    cur = live.cursor()
    cur.execute("""
        SELECT symbol, signal_time, direction, entry, sl, tp, strategy, quality, confluence_score
        FROM ict_trade.signals
        WHERE mode = %s AND signal_time >= %s AND signal_time < %s
        ORDER BY signal_time
    """, (mode, since.to_pydatetime(), until.to_pydatetime()))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return rows


def fetch_klines_safe(symbol: str, start: pd.Timestamp, end: pd.Timestamp, attempts: int = 3):
    """1m klines with a couple of retries — Binance 429/5xx/timeouts shouldn't kill the pass."""
    last = None
    for k in range(attempts):
        try:
            return tsc.fetch_1m(symbol, start, end)
        except Exception as e:
            last = e
            log(f"  kline fetch retry {k+1}/{attempts} for {symbol}: {e}")
    log(f"  kline fetch FAILED for {symbol}: {last}")
    return None


# ---------------------------------------------------------------- main pass
def run_once(*, discover_days: int, dry_run: bool) -> None:
    now = pd.Timestamp.now(tz="UTC")
    state = load_state()
    live = tsc.live_conn()
    bt = tsc.backtest_conn()

    # 1) discover newly-emitted signals and register them (adopt in-flight ones silently).
    discovered = 0
    for s in STREAMS:
        try:
            rows = fetch_recent_signals(live, s["mode"], now - pd.Timedelta(days=discover_days), now)
        except Exception as e:
            log(f"  discovery failed for mode={s['mode']}: {e}")
            continue
        for r in rows:
            key = trade_key(s["mode"], r)
            if key in state:
                continue
            sig_ts = pd.Timestamp(r["signal_time"])
            sig_ts = sig_ts.tz_localize("UTC") if sig_ts.tz is None else sig_ts.tz_convert("UTC")
            rr = abs(r["tp"] - r["entry"]) / abs(r["entry"] - r["sl"]) if (r["entry"] - r["sl"]) else 0.0
            state[key] = {
                "mode": s["mode"], "version": s["version"], "impulse": s["impulse"],
                "symbol": r["symbol"], "direction": str(r["direction"]).lower(),
                "signal_time": sig_ts.isoformat(),
                "entry": float(r["entry"]), "sl": float(r["sl"]), "tp": float(r["tp"]),
                "rr": float(rr), "strategy": r.get("strategy"), "quality": r.get("quality"),
                "confluence_score": r.get("confluence_score"),
                "phase": "pending", "cards_sent": [], "adopted": False,
            }
            discovered += 1

    # 2) advance every non-terminal tracked trade; fire cards on freshly-reached milestones.
    open_n = cards_n = closed_n = 0
    for key, pos in list(state.items()):
        if pos["phase"] in ("closed", "cancelled"):
            continue
        open_n += 1
        sig_ts = pd.Timestamp(pos["signal_time"])
        close_ts = sig_ts + pd.Timedelta(minutes=LTF_MINUTES)
        horizon_end = min(now, close_ts + pd.Timedelta(days=MAX_OPEN_DAYS))
        df1m = fetch_klines_safe(pos["symbol"], close_ts - pd.Timedelta(minutes=2), horizon_end)
        if df1m is None:
            continue                                        # transient fetch failure -> retry next run
        try:
            res = resolve_lifecycle(pos["direction"], pos["entry"], pos["sl"], pos["tp"],
                                    df1m, close_ts)
        except Exception as e:
            log(f"  resolve error {pos['symbol']} {pos['version']}: {e}")
            continue

        passed = milestones_passed(res)
        sent = set(pos["cards_sent"])

        # First sighting of an already-in-flight trade: adopt at current phase, no retro cards.
        if not pos["adopted"]:
            pos["adopted"] = True
            if passed:
                sent |= passed
                pos["cards_sent"] = sorted(sent)
                if "A" in passed and "C" not in passed:     # adopted mid-flight & still live -> show in DB
                    upsert_dashboard_row(bt, pos, res, closed=False, dry_run=dry_run)

        new = [m for m in ("A", "B", "C") if m in passed and m not in sent]
        for m in new:
            if m == "A":
                text = card_open(pos, res)
                upsert_dashboard_row(bt, pos, res, closed=False, dry_run=dry_run)
            elif m == "B":
                text = card_partial(pos, res)
            else:
                text = card_close(pos, res)
                upsert_dashboard_row(bt, pos, res, closed=True, dry_run=dry_run)
            log("\n" + text + "\n")
            send_telegram(text, impulse=pos["impulse"], dry_run=dry_run)
            sent.add(m)
            cards_n += 1

        pos["cards_sent"] = sorted(sent)
        pos["phase"] = res["phase"]
        pos["last_checked"] = now.isoformat()
        if res["phase"] in ("closed", "cancelled"):
            pos["close_reason"] = res.get("close_reason")
            pos["pnl_r"] = res.get("pnl_r")
            closed_n += 1

    # prune long-settled trades so the state file stays bounded (kept well past the
    # discover window so a pruned trade is never re-discovered and re-adopted).
    cutoff = now - pd.Timedelta(days=PRUNE_AFTER_DAYS)
    for k in [k for k, p in state.items()
              if p["phase"] in ("closed", "cancelled")
              and pd.Timestamp(p["signal_time"]) < cutoff]:
        del state[k]

    if not dry_run:
        save_state(state)
    try:
        live.close(); bt.close()
    except Exception:
        pass

    tracked_open = sum(1 for p in state.values() if p["phase"] not in ("closed", "cancelled"))
    log(f"\n[½TP monitor] {now:%Y-%m-%d %H:%M UTC} | discovered={discovered} "
        f"advanced={open_n} cards={cards_n} closed={closed_n} | still-open={tracked_open}"
        f"{' (dry-run)' if dry_run else ''}")


# RETIRED 2026-06-13: the standalone MAIN ½TP / IMPULSE ½TP (v3/v4) streams this
# monitor fed were removed from the dashboard + DB during the strategy prune, so it no
# longer has a destination. Disabled by default; set HALFTP_MONITOR_ENABLED=1 to force a
# run (e.g. if the ½TP streams are ever reinstated). ACTION: remove its `*/5 * * * *`
# line from the VM crontab — with this guard a stray cron fire is a harmless no-op.
def main() -> None:
    if os.getenv("HALFTP_MONITOR_ENABLED", "0") != "1":
        log("½TP monitor RETIRED (2026-06-13): v3/v4 streams removed in the strategy prune. "
            "No-op. Set HALFTP_MONITOR_ENABLED=1 to override; remove its cron line on the VM.")
        return
    ap = argparse.ArgumentParser(description="Live ½TP partial-TP + breakeven trade monitor")
    ap.add_argument("--dry-run", action="store_true", help="resolve + print cards, no Telegram / no DB")
    ap.add_argument("--discover-days", type=int, default=DISCOVER_DAYS_DEFAULT,
                    help="how far back to pick up newly-emitted signals")
    args = ap.parse_args()
    run_once(discover_days=args.discover_days, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
