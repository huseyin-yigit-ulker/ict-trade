"""AÇIK İŞLEM ÖZETİ — her 5 dakikada TEK Telegram mesajı, tüm canlı pozisyonların anlık durumu.

Kaynaklar:
  * Binance (tek `positionRisk` çağrısı)  — ANLIK mark / uPnL / liq / isolatedMargin / kaldıraç
  * ict_trade.live_positions              — OPUS (Donchian scale-out, kripto): state, risk0, eff_*
  * ict_trade.talos_ichi_positions        — TALOS-ICHI-X (altın trailing): cur_sl, locked_r, risk0

Tarayıcı/executor gibi emir GÖNDERMEZ; salt-okunur bir raporcudur. Açık pozisyon yoksa sessiz kalır
(spam yok) — `--always` ile boşken de mesaj atar, `--dry-run` ile Telegram'a göndermeden basar.

    python sync/positions_digest.py            # cron: sessiz-if-boş, tek mesaj
    python sync/positions_digest.py --dry-run  # ekrana bas, gönderme
"""
from __future__ import annotations

import sys
import argparse
from pathlib import Path

import requests

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent))                    # sync/          -> trade_sync_common
sys.path.insert(0, str(_HERE.parent / "live_exec"))      # sync/live_exec -> binance_futures
import trade_sync_common as tsc                          # noqa: E402
from binance_futures import BinanceFutures, BinanceError  # noqa: E402

MAINNET_BASE = "https://fapi.binance.com"
TESTNET_BASE = "https://testnet.binancefuture.com"

# (tablo, akış adı, açık-durumlar) — her executor kendi tablosunu yazar; ikisi AYNI Binance hesabında.
SOURCES = (
    ("ict_trade.live_positions", "OPUS",
     ("PENDING_ENTRY", "ENTRY_WORKING", "OPEN_FULL", "RUNNER", "CLOSING")),
    ("ict_trade.talos_ichi_positions", "TALOS-ICHI-X",
     ("PENDING_ENTRY", "ENTRY_WORKING", "OPEN")),
)


def _f(v, d=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _telegram(text: str, env: dict) -> bool:
    token = env.get("TELEGRAM_BOT_TOKEN")
    chat = env.get("TELEGRAM_EXEC_CHAT_ID") or env.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        print("  telegram atlandı (token/chat yok)")
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": text, "parse_mode": "HTML",
                                "disable_web_page_preview": True}, timeout=15)
        if not r.ok:
            print(f"  telegram hata: {r.text[:160]}")
        return bool(r.ok)
    except Exception as e:                                # noqa: BLE001
        print(f"  telegram exception: {e}")
        return False


def _db_rows(conn) -> dict:
    """symbol -> {stream, state, direction, eff_entry, risk0, cur_sl, locked_r, entry_fill_time, ...}"""
    out: dict[str, dict] = {}
    cur = conn.cursor()
    for table, stream, states in SOURCES:
        try:
            cur.execute(f"SELECT * FROM {table} WHERE state = ANY(%s)", (list(states),))
        except Exception:                                 # noqa: BLE001  (tablo yoksa raporu kırma)
            conn.rollback()
            continue
        cols = [d[0] for d in cur.description]
        for r in cur.fetchall():
            row = dict(zip(cols, r))
            row["stream"] = stream
            out[row["symbol"]] = row
    cur.close()
    return out


def _dur(td) -> str:
    if td is None:
        return "—"
    s = int(td.total_seconds())
    if s < 3600:
        return f"{s // 60}dk"
    return f"{s // 3600}sa {(s % 3600) // 60}dk"


def build_message(positions: list[dict], acct: dict, now) -> str:
    lines = [f"📊 <b>AÇIK İŞLEMLER</b> · {len(positions)} · <code>{now:%H:%M} UTC</code>"]
    for p in positions:
        side = 1 if p["amt"] > 0 else -1
        arrow = "🟢 LONG" if side > 0 else "🔴 SHORT"
        mark, entry = p["mark"], p["entry"]
        chg = (mark - entry) / entry * 100 * side if entry else 0.0   # + = pozisyonun LEHİNE
        r_txt = f" · <b>{p['r']:+.2f}R</b>" if p["r"] is not None else ""
        # OPUS scale-out RUNNER = ilk hedef (+1R) çoktan kısmen alındı; ekrandaki R kalan bacağındır.
        state = p.get("state")
        state_txt = f" <i>({state}{' · TP1 alındı' if state == 'RUNNER' else ''})</i>" if state else ""
        lines.append("")
        lines.append(f"{arrow} <b>{p['symbol']}</b> · {p['stream']}{state_txt}")
        lines.append(f"   giriş <code>{entry:g}</code> → <code>{mark:g}</code> "
                     f"({'lehte' if chg >= 0 else 'aleyhte'} {abs(chg):.2f}%)")
        lines.append(f"   uPnL <b>{'+' if p['upnl'] >= 0 else ''}${p['upnl']:.2f}</b>{r_txt}")
        sl = p.get("sl")
        sl_txt = f"SL <code>{sl:g}</code>" if sl else "SL —"
        if p.get("locked_r") is not None:
            sl_txt += f" (kilitli {p['locked_r']:+.2f}R)"
        lines.append(f"   {sl_txt} · {p['dur']} · {p['lev']}x · marj ${p['margin']:.1f}")
        if p.get("liq"):
            lines.append(f"   liq <code>{p['liq']:g}</code>")
    lines.append("")
    lines.append(f"💰 cüzdan <b>${acct['wallet']:.2f}</b> · serbest <b>${acct['avail']:.2f}</b>"
                 f" · uPnL <b>{'+' if acct['upnl'] >= 0 else ''}${acct['upnl']:.2f}</b>")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="ekrana bas, Telegram'a gönderme")
    ap.add_argument("--always", action="store_true", help="açık pozisyon yokken de mesaj at")
    ap.add_argument("--testnet", action="store_true", help="testnet hesabını raporla")
    args = ap.parse_args()

    env = {**tsc._read_env()}
    import pandas as pd
    now = pd.Timestamp.now(tz="UTC")

    key = env.get("BINANCE_TESTNET_API_KEY" if args.testnet else "BINANCE_API_KEY", "").strip()
    sec = env.get("BINANCE_TESTNET_API_SECRET" if args.testnet else "BINANCE_API_SECRET", "").strip()
    if not (key and sec):
        raise SystemExit("Binance API anahtarı yok — rapor üretilemiyor.")
    client = BinanceFutures(api_key=key, api_secret=sec,
                            base_url=TESTNET_BASE if args.testnet else MAINNET_BASE,
                            proxy=str(env.get("BINANCE_PROXY", "")).strip())

    conn = tsc.live_conn()
    rows = _db_rows(conn)
    conn.close()

    try:
        risk = client.position_risk()
        acct_raw = client.account()
    except BinanceError as e:
        raise SystemExit(f"Binance okunamadı: {e}")

    positions = []
    for p in risk:
        amt = _f(p.get("positionAmt"))
        if amt == 0:
            continue
        sym = p.get("symbol")
        db = rows.get(sym, {})
        entry = _f(p.get("entryPrice"))
        mark = _f(p.get("markPrice"))
        side = 1 if amt > 0 else -1
        risk0 = _f(db.get("risk0"))                       # birim başına 1R (|giriş − SL|)
        r = ((mark - entry) * side / risk0) if risk0 > 0 else None
        # SL: trailing akışta cur_sl, scale-out'ta eff_sl; yoksa sinyal SL'i
        sl = _f(db.get("cur_sl")) or _f(db.get("eff_sl")) or _f(db.get("signal_sl")) or None
        fill = db.get("entry_fill_time")
        positions.append({
            "symbol": sym, "amt": amt, "entry": entry, "mark": mark,
            "upnl": _f(p.get("unRealizedProfit")),
            "liq": _f(p.get("liquidationPrice")) or None,
            "lev": int(_f(p.get("leverage"), 1)),
            "margin": _f(p.get("isolatedMargin")),
            "stream": db.get("stream", "?"), "state": db.get("state"),
            "r": r, "sl": sl,
            "locked_r": (float(db["locked_r"]) if db.get("locked_r") is not None else None),
            "dur": _dur(now - pd.Timestamp(fill)) if fill else "—",
        })
    positions.sort(key=lambda x: x["symbol"])

    acct = {"wallet": _f(acct_raw.get("totalWalletBalance")),
            "avail": _f(acct_raw.get("availableBalance")),
            "upnl": _f(acct_raw.get("totalUnrealizedProfit"))}

    if not positions and not args.always:
        print(f"=== açık pozisyon yok @ {now:%H:%M}Z — sessiz (spam yok) ===")
        return

    msg = build_message(positions, acct, now) if positions else (
        f"📊 <b>AÇIK İŞLEM YOK</b> · <code>{now:%H:%M} UTC</code>\n"
        f"💰 cüzdan <b>${acct['wallet']:.2f}</b> · serbest <b>${acct['avail']:.2f}</b>")
    print(msg.replace("<b>", "").replace("</b>", "").replace("<code>", "")
             .replace("</code>", "").replace("<i>", "").replace("</i>", ""))
    if args.dry_run:
        print("\n[dry-run] Telegram'a gönderilmedi.")
        return
    ok = _telegram(msg, env)
    print(f"\n{'✓ gönderildi' if ok else '✗ gönderilemedi'} ({len(positions)} pozisyon)")


if __name__ == "__main__":
    main()
