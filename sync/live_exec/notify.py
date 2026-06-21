"""Telegram alerts for the live executor — reuses the bot token the DAG/canli already use.

Best-effort: a notification failure must never break order management. Routes to
TELEGRAM_EXEC_CHAT_ID when set, else falls back to TELEGRAM_CHAT_ID (canli._telegram_send shape).
"""
from __future__ import annotations

import sys
from pathlib import Path

import requests

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))   # sync/ -> trade_sync_common
import trade_sync_common as tsc              # noqa: E402


def alert(text: str, *, chat_id: str = "") -> None:
    env = tsc._read_env()
    token = env.get("TELEGRAM_BOT_TOKEN")
    chat = chat_id or env.get("TELEGRAM_EXEC_CHAT_ID") or env.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        print(f"  [notify] telegram skipped: {text[:80]}")
        return
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": text, "parse_mode": "HTML"}, timeout=15)
        if not r.ok:
            print(f"  [notify] telegram error: {r.text[:150]}")
    except Exception as e:  # noqa: BLE001
        print(f"  [notify] telegram exception: {e}")
