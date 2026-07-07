"""Web Push fan-out for PUSU (VAPID) — the native-notification sibling of Telegram.

Reads active subscriptions from ict_trade.push_subscriptions (live DB, via the same
psycopg2 connection the emitters already use) and pushes a notification with
pywebpush. Dead endpoints (404/410) are pruned.

Two delivery paths:
  * send_push(...)     — BROADCAST to every subscription (the original signal-emit path);
  * drain_outbox(conn) — PER-USER queue: the multi-user executors insert personal events into
    ict_trade.push_outbox (sync/users/store.push_user) and a cron runs
    `python sync/push_notify.py --drain` every minute to deliver each payload ONLY to that
    user's subscriptions (push_subscriptions.user_id match), marking rows sent_at.

BEST-EFFORT BY DESIGN: never raises, and is a no-op (returns 0) when unconfigured —
if VAPID_PRIVATE_KEY is unset or pywebpush isn't installed, the emit path behaves
exactly as before. So this can ship dark and light up only once the ops steps
(gen_vapid.py + pip install pywebpush + apply the SQL) are done. drain_outbox also
exits quietly while migration 006 (push_outbox) hasn't been applied yet, so the cron
line can be installed first.

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
sys.path.insert(0, str(_HERE.parent / "users"))   # sync/users -> push_flair
import trade_sync_common as tsc          # noqa: E402

try:
    import push_flair                     # mizah katmanı (best-effort, opsiyonel)
except Exception:  # noqa: BLE001
    push_flair = None


def _spice_signal(body: str) -> str:
    """Sinyal push gövdesine espri satırı (PUSH_FLAIR=0 kapatır). Best-effort."""
    if push_flair is None:
        return body
    try:
        return push_flair.spice("signal", body)
    except Exception:  # noqa: BLE001
        return body

_SELECT = "SELECT id, endpoint, p256dh, auth, user_id FROM ict_trade.push_subscriptions"
_DELETE = "DELETE FROM ict_trade.push_subscriptions WHERE id = %s"

# ---- broadcast anonymization (2026-07-04 multi-user privacy) --------------------------
# Signal broadcasts are written with the REAL stream names (OPUS/FABLE/MIDAS...) for the
# owner's Telegram; non-admin push subscribers must instead see the SAME codenames the UI
# shows them (src/utils/streamMask.js) and no strategy vocabulary. Keep this map in sync
# with streamMask.CODENAMES. Longest-first replacement so 'MIDAS-X' wins over 'MIDAS'.
_MASK_MAP = [
    ("MIDAS-X", "SIRIUS-X"),
    ("OPUS", "ATLAS"),
    ("FABLE", "NOVA"),
    ("MIDAS", "SIRIUS"),
    ("DONCHIAN", "TREND"),
    ("Donchian", "TREND"),
    ("VWAP", "T-REF"),
    ("d30so8f3h7", "ATLAS"),
    ("d30so8f3vg", "NOVA"),
    ("dch30_4hvg", "NOVA"),
    ("dch30_4h6", "TREND"),
    ("dch30_4h", "ATLAS"),
]


def _mask_text(text: str) -> str:
    for real, code in _MASK_MAP:
        text = text.replace(real, code)
    return text


def _signal_muted_user_ids(conn) -> set:
    """notify_signals=false diyen kullanıcılar (user_prefs) — sinyal broadcast'i almazlar.
    Tablo henüz yoksa (migration 008 uygulanmadıysa) kimse susturulmaz."""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id::text FROM ict_trade.user_prefs WHERE notify_signals = false")
            return {r[0] for r in cur.fetchall()}
    except Exception:  # noqa: BLE001 — pre-migration-008
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        return set()


def _admin_user_ids(conn) -> set:
    """profiles admins (the owner) get the REAL wording; everyone else the codenames.
    Returns an empty set (mask for all user-stamped subs) if profiles doesn't exist yet."""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id::text FROM ict_trade.profiles WHERE role = 'admin'")
            return {r[0] for r in cur.fetchall()}
    except Exception:  # noqa: BLE001 — pre-migration-001
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        return set()


# signals.mode (scanner discriminator) -> anonim akış KEY'i (user_signal_watch.strategy).
_MODE_TO_STREAM = {
    "dch30_4h": "d30so8f3h7",    # OPUS
    # "dch30_4hvg" (FABLE) emekli 2026-07-07 — canli emit'i kaldirildi, backtest-only.
    "midas": "midas",            # MIDAS / SIRIUS
}


def _watchlist_user_ids(conn) -> set:
    """Bir sinyal izleme listesi (>=1 sembol) kuran kullanıcılar. Bunlar hedefli push'u
    push_signal_watchers üzerinden alır, bu yüzden BROADCAST onları ATLAR (çift bildirim
    olmaz). Tablo yoksa (migration 011 uygulanmadı) boş küme -> herkes broadcast alır."""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT user_id::text FROM ict_trade.user_signal_watch "
                        "WHERE cardinality(symbols) > 0")
            return {r[0] for r in cur.fetchall()}
    except Exception:  # noqa: BLE001 — pre-migration-011
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        return set()


def send_push(title: str, body: str, url: str = "/", tag: str | None = None) -> int:
    """Fan a notification out to every stored subscription. Returns the count sent.
    Swallows all errors — a push problem must never break signal emission.
    Non-admin subscribers receive the ANONYMIZED text (codenames, no strategy terms)."""
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

        body = _spice_signal(body)   # espri strateji-nötr — maskeden etkilenmez
        payload = json.dumps({"title": title, "body": body, "url": url, "tag": tag})
        payload_masked = json.dumps({"title": _mask_text(title), "body": _mask_text(body),
                                     "url": url, "tag": tag})
        claims = {"sub": subject}
        sent = 0
        dead: list[int] = []

        conn = tsc.live_conn()
        try:
            admins = _admin_user_ids(conn)
            muted = _signal_muted_user_ids(conn)
            watched = _watchlist_user_ids(conn)
            with conn.cursor() as cur:
                cur.execute(_SELECT)
                subs = cur.fetchall()
            for sub_id, endpoint, p256dh, auth, user_id in subs:
                # kullanıcı tercihi: sinyal yayınları kapalıysa bu aboneliği atla
                # (user-less legacy satırlar owner'ın cihazlarıdır — her zaman alır)
                if user_id is not None and str(user_id) in muted:
                    continue
                # izleme listesi kuran kullanıcı broadcast almaz — hedefli push
                # (push_signal_watchers) üzerinden yalnız seçtiği (strateji,sembol)'ü alır
                if user_id is not None and str(user_id) in watched:
                    continue
                info = {"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}}
                # legacy user-less subscriptions belong to the owner's devices (pre-multi-user)
                data = payload if (user_id is None or str(user_id) in admins) else payload_masked
                try:
                    webpush(subscription_info=info, data=data,
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


def push_signal_watchers(mode: str, symbol: str, title: str, body: str,
                         url: str = "/", tag: str | None = None) -> int:
    """Queue a PERSONAL signal push for every user whose watchlist (ict_trade.user_signal_watch)
    includes (stream_of(mode), symbol). Honors notify_signals. Text is masked to codenames
    per-user (the --drain path doesn't mask). Fires for the FULL scanned universe (independent
    of the owner's Telegram gate) so a user can watch any symbol. Rows are delivered by the
    existing `--drain` cron. Best-effort; silent no-op pre-migration-011. Returns rows queued."""
    try:
        conn = tsc.live_conn()
        try:
            stream = _MODE_TO_STREAM.get(mode, mode)
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT user_id::text FROM ict_trade.user_signal_watch "
                                "WHERE strategy = %s AND %s = ANY(symbols)", (stream, symbol))
                    watchers = [r[0] for r in cur.fetchall()]
            except Exception:  # noqa: BLE001 — pre-migration-011 (table absent)
                conn.rollback()
                return 0
            if not watchers:
                return 0
            muted = _signal_muted_user_ids(conn)
            admins = _admin_user_ids(conn)
            body = _spice_signal(body)   # espri strateji-nötr — maskeden etkilenmez
            queued = 0
            for uid in watchers:
                if uid in muted:                    # sinyal yayınları kapalı -> atla
                    continue
                t_ = title if uid in admins else _mask_text(title)
                b_ = body if uid in admins else _mask_text(body)
                payload = json.dumps({"title": t_, "body": b_, "url": url, "tag": tag})
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO ict_trade.push_outbox (user_id, payload) "
                                "VALUES (%s, %s::jsonb)", (uid, payload))
                queued += 1
            conn.commit()
            return queued
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
    except Exception as e:  # noqa: BLE001
        print(f"  watcher enqueue skipped: {str(e)[:150]}")
        return 0


def drain_outbox(conn) -> int:
    """Deliver queued per-user pushes from ict_trade.push_outbox (oldest first, ≤200/run).

    Each unsent row's payload {title, body, tag?, url?} goes ONLY to that user's
    push_subscriptions rows. Rows are marked sent_at even when the user has no
    subscriptions (so the queue can never grow unbounded); dead endpoints (404/410)
    are pruned like the broadcast path. Returns the number of pushes sent.

    Quiet no-op when: VAPID/pywebpush unconfigured, the outbox is empty, or the
    push_outbox table doesn't exist yet (migration 006 not applied — the cron line
    may land first)."""
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

        with conn.cursor() as cur:
            cur.execute("SELECT id, user_id::text, payload FROM ict_trade.push_outbox "
                        "WHERE sent_at IS NULL ORDER BY id LIMIT 200")
            rows = cur.fetchall()
        if not rows:
            return 0

        # one subscriptions read, grouped per user (only user-stamped rows can be targeted)
        with conn.cursor() as cur:
            cur.execute(_SELECT + " WHERE user_id IS NOT NULL")
            subs = cur.fetchall()
        by_user: dict = {}
        for sub_id, endpoint, p256dh, auth, user_id in subs:
            by_user.setdefault(str(user_id), []).append((sub_id, endpoint, p256dh, auth))

        claims = {"sub": subject}
        sent = 0
        dead: set = set()
        done_ids: list = []
        for row_id, user_id, payload in rows:
            data = payload if isinstance(payload, str) else json.dumps(payload)
            for sub_id, endpoint, p256dh, auth in by_user.get(user_id, []):
                if sub_id in dead:
                    continue
                info = {"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}}
                try:
                    webpush(subscription_info=info, data=data,
                            vapid_private_key=priv, vapid_claims=dict(claims))
                    sent += 1
                except WebPushException as e:  # noqa: PERF203
                    status = getattr(getattr(e, "response", None), "status_code", None)
                    if status in (404, 410):
                        dead.add(sub_id)
                    else:
                        print(f"  outbox push error ({status}): {str(e)[:120]}")
                except Exception as e:  # noqa: BLE001
                    print(f"  outbox push exception: {str(e)[:120]}")
            done_ids.append(row_id)   # sent OR no subscriptions: consume either way

        with conn.cursor() as cur:
            cur.execute("UPDATE ict_trade.push_outbox SET sent_at = now() WHERE id = ANY(%s)",
                        (done_ids,))
            for sub_id in dead:
                cur.execute(_DELETE, (sub_id,))
        conn.commit()
        if dead:
            print(f"  outbox pruned {len(dead)} dead subscription(s)")
        print(f"  outbox drained: {len(done_ids)} row(s) -> {sent} push(es)")
        return sent
    except Exception as e:  # noqa: BLE001 — incl. psycopg2 UndefinedTable pre-migration-006
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        print(f"  outbox drain skipped: {str(e)[:150]}")
        return 0


def main():
    import argparse
    ap = argparse.ArgumentParser(description="PUSU Web Push utility")
    ap.add_argument("--drain", action="store_true",
                    help="drain ict_trade.push_outbox (per-user executor pushes) — cron: every minute")
    args = ap.parse_args()
    if args.drain:
        conn = tsc.live_conn()
        try:
            drain_outbox(conn)
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


if __name__ == "__main__":
    main()
