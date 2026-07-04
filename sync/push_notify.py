"""Web Push fan-out for PUSU (VAPID) — the native-notification sibling of Telegram.

Reads active subscriptions from ict_trade.push_subscriptions (live DB, via the same
psycopg2 connection the emitters already use) and pushes a notification with
pywebpush. Dead endpoints (404/410) are pruned.

BEST-EFFORT BY DESIGN: never raises, and is a no-op (returns 0) when unconfigured —
if VAPID_PRIVATE_KEY is unset or pywebpush isn't installed, the emit path behaves
exactly as before. So this can ship dark and light up only once the ops steps
(gen_vapid.py + pip install pywebpush + apply the SQL) are done.

VM .env:
  VAPID_PRIVATE_KEY   base64url EC P-256 raw scalar (scripts/gen_vapid.py)
  VAPID_SUBJECT       contact URI, e.g. mailto:you@example.com
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent))   # sync/
import trade_sync_common as tsc          # noqa: E402

_SELECT = "SELECT id, endpoint, p256dh, auth FROM ict_trade.push_subscriptions"
_DELETE = "DELETE FROM ict_trade.push_subscriptions WHERE id = %s"


def send_push(title: str, body: str, url: str = "/", tag: str | None = None) -> int:
    """Fan a notification out to every stored subscription. Returns the count sent.
    Swallows all errors — a push problem must never break signal emission."""
    try:
        env = tsc._read_env()
        priv = env.get("VAPID_PRIVATE_KEY")
        subject = env.get("VAPID_SUBJECT", "mailto:ops@pusu.app")
        if not priv:
            return 0  # push not configured — silent no-op
        try:
            from pywebpush import webpush, WebPushException
        except Exception:
            return 0  # pywebpush not installed yet — silent no-op

        payload = json.dumps({"title": title, "body": body, "url": url, "tag": tag})
        claims = {"sub": subject}
        sent = 0
        dead: list[int] = []

        conn = tsc.live_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(_SELECT)
                subs = cur.fetchall()
            for sub_id, endpoint, p256dh, auth in subs:
                info = {"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}}
                try:
                    webpush(subscription_info=info, data=payload,
                            vapid_private_key=priv, vapid_claims=dict(claims))
                    sent += 1
                except WebPushException as e:  # noqa: PERF203
                    status = getattr(getattr(e, "response", None), "status_code", None)
                    if status in (404, 410):
                        dead.append(sub_id)
                    else:
                        print(f"  push error ({status}): {str(e)[:120]}")
                except Exception as e:  # noqa: BLE001
                    print(f"  push exception: {str(e)[:120]}")
            if dead:
                with conn.cursor() as cur:
                    for sub_id in dead:
                        cur.execute(_DELETE, (sub_id,))
                conn.commit()
                print(f"  push pruned {len(dead)} dead subscription(s)")
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return sent
    except Exception as e:  # noqa: BLE001
        print(f"  push fan-out failed: {e}")
        return 0
