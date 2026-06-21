"""Telegram CRON HEALTH-CHECK — proves the live emit cron is running even when no signal fires.

A quiet stream (no breakouts for hours) is normal, but it looks identical to a dead cron. This
sends a periodic "I'm alive" Telegram message with, per strategy, the last signal + a 24h count,
plus how long ago the emit cron last scanned (from the log mtime). Scheduled by dag/crontab.

    python sync/donchian/heartbeat.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import trade_sync_common as tsc  # noqa: E402

# Live emit streams (mode -> human label) — mirrors dag/crontab's three canli.py --emit lines.
STREAMS = [
    ("donchian", "DONCHIAN 1h"),
    ("dch30_4h", "DONCHIAN 30m+4h"),
    ("dch30_4h6", "DONCHIAN 30m+4h·6R"),
]
EMIT_LOG = Path(os.path.expanduser("~/ict-donchian.log"))
EMIT_STALE_MIN = 40   # emit runs on bar close (30m streams every :00/:30) — >40 min idle = a problem


def _telegram(text: str) -> bool:
    env = tsc._read_env()
    token, chat = env.get("TELEGRAM_BOT_TOKEN"), env.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        print("  telegram skipped (TELEGRAM_BOT_TOKEN/CHAT_ID not set)")
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": text, "parse_mode": "HTML"}, timeout=15)
        if not r.ok:
            print(f"  telegram error: {r.text[:200]}")
        return bool(r.ok)
    except Exception as e:  # noqa: BLE001
        print(f"  telegram exception: {e}")
        return False


def main() -> None:
    now = pd.Timestamp.now(tz="UTC")
    # Emit freshness from the log's last-write time (each */10 run appends to it).
    emit_line = "Canlı emit (her 10 dk): durum bilinmiyor (log yok)"
    if EMIT_LOG.exists():
        age_min = (time.time() - EMIT_LOG.stat().st_mtime) / 60
        mark = "✅" if age_min <= EMIT_STALE_MIN else "⚠️ GECİKME"
        emit_line = f"Canlı emit (her 10 dk): son tarama {age_min:.0f} dk önce {mark}"

    lines = [f"🟢 <b>PUSU cron çalışıyor</b> — {now:%Y-%m-%d %H:%M} UTC", "", emit_line, ""]
    try:
        conn = tsc.live_conn()
        cur = conn.cursor()
        for mode, label in STREAMS:
            cur.execute(
                """select max(signal_time),
                          count(*) filter (where signal_time >= %s)
                   from ict_trade.signals where mode = %s""",
                (now - pd.Timedelta(hours=24), mode),
            )
            last, cnt24 = cur.fetchone()
            last_s = pd.Timestamp(last).strftime("%m-%d %H:%M") if last else "—"
            lines.append(f"  • {label}: son sinyal {last_s} · 24s {cnt24} sinyal")
        cur.close()
        conn.close()
    except Exception as e:  # noqa: BLE001
        lines.append(f"  ⚠️ live DB okunamadı: {e}")

    lines += ["", "Sinyal gelmemesi sistemin durduğu anlamına gelmez ✅"]
    ok = _telegram("\n".join(lines))
    print(f"heartbeat sent = {ok}")


if __name__ == "__main__":
    main()
