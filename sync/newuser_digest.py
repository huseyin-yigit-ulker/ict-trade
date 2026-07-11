"""YENİ KULLANICI GÜNLÜK ÖZETİ — ilk haftasındaki kullanıcılara günde 1 push.

Kurulumunu yeni yapan kullanıcı (ilk API anahtarı ≤7 gün önce) sistemin çalıştığını
görmek ister; bu cron her akşam kısa bir durum push'u kuyruklar:

    "Bugün: 2 işlem, +$3.40 · Açık: 1 pozisyon · Toplam: +$5.12"

Kaynaklar (hepsi salt-okunur):
  * ict_trade.user_api_keys        — onboarding başlangıcı = kullanıcının İLK anahtarı
  * ict_trade.push_subscriptions   — aboneliği olmayan kullanıcıya kuyruk yazılmaz
  * live_positions / talos_ichi_positions / midas_positions — kullanıcı-bazlı (user_id)
    kapalı işlemler (bugün + toplam) ve açık pozisyon sayısı

Teslimat: store.push_user → ict_trade.push_outbox (kind='system' — user_prefs
notify_system tercihiyle elenebilir); dakikalık `push_notify.py --drain` gönderir.
BEST-EFFORT: hata durumunda sessizce çıkar, hiçbir emir/exec yolunu ETKİLEMEZ.
Bayrak: app_flags 'newuser_digest' (admin_set_flag ile kapatılabilir; satır yoksa AÇIK).

    python sync/newuser_digest.py            # cron (günde 1, 18:05 UTC)
    python sync/newuser_digest.py --dry-run  # push kuyruklamadan ekrana bas
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent))             # sync/       -> trade_sync_common
sys.path.insert(0, str(_HERE.parent / "users"))   # sync/users  -> store
import trade_sync_common as tsc                   # noqa: E402
import store                                      # noqa: E402

NEW_USER_DAYS = 7

# (tablo, açık-durumlar) — kapalılar her tabloda state='CLOSED' + realized_usd.
SOURCES = (
    ("ict_trade.live_positions", ("PENDING_ENTRY", "ENTRY_WORKING", "OPEN_FULL", "RUNNER", "CLOSING")),
    ("ict_trade.talos_ichi_positions", ("PENDING_ENTRY", "ENTRY_WORKING", "OPEN")),
    ("ict_trade.midas_positions", ("PENDING_ENTRY", "ENTRY_WORKING", "OPEN")),
)


def _fmt_usd(v: float) -> str:
    return f"{'+' if v >= 0 else '−'}${abs(v):.2f}"


def _new_users(conn) -> list[tuple[str, int]]:
    """[(user_id, kaçıncı_gün)] — ilk anahtarı ≤NEW_USER_DAYS gün önce olan,
    push aboneliği bulunan kullanıcılar."""
    with conn.cursor() as cur:
        cur.execute(
            """
            select k.user_id::text,
                   greatest(1, (current_date - min(k.created_at)::date) + 1) as day_no
            from ict_trade.user_api_keys k
            where k.user_id is not null
              and exists (select 1 from ict_trade.push_subscriptions s where s.user_id = k.user_id)
            group by k.user_id
            having min(k.created_at) >= now() - make_interval(days => %s)
            """,
            (NEW_USER_DAYS,),
        )
        return [(r[0], int(r[1])) for r in cur.fetchall()]


def _stats(conn, user_id: str) -> dict:
    today_n = today_usd = total_usd = open_n = 0
    with conn.cursor() as cur:
        for table, open_states in SOURCES:
            cur.execute(
                f"""
                select
                  count(*) filter (where state = 'CLOSED' and exit_time::date = current_date),
                  coalesce(sum(realized_usd) filter (where state = 'CLOSED' and exit_time::date = current_date), 0),
                  coalesce(sum(realized_usd) filter (where state = 'CLOSED'), 0),
                  count(*) filter (where state in %s)
                from {table} where user_id = %s::uuid
                """,
                (open_states, user_id),
            )
            n, tu, au, op = cur.fetchone()
            today_n += int(n or 0)
            today_usd += float(tu or 0)
            total_usd += float(au or 0)
            open_n += int(op or 0)
    return {"today_n": today_n, "today_usd": today_usd, "total_usd": total_usd, "open_n": open_n}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    try:
        conn = tsc.live_conn()
    except Exception as e:  # noqa: BLE001
        print(f"[newuser-digest] db yok, atlandı: {e}")
        return

    try:
        if not tsc.flag_enabled(conn, "newuser_digest", default=True):
            print("[newuser-digest] bayrak kapalı, atlandı")
            return
        users = _new_users(conn)
        if not users:
            print("[newuser-digest] ilk haftasında (push abonelikli) kullanıcı yok")
            return
        for uid, day_no in users:
            st = _stats(conn, uid)
            # Hiç aktivite yoksa (0 işlem, 0 açık) 3. günden sonra susulur — spam olmasın;
            # ilk 2 gün "sistem canlı" güveni için yine gönderilir.
            if st["today_n"] == 0 and st["open_n"] == 0 and st["total_usd"] == 0 and day_no > 2:
                print(f"[newuser-digest] {uid[:8]} gün{day_no}: aktivite yok, atlandı")
                continue
            body = (
                f"Bugün: {st['today_n']} işlem, {_fmt_usd(st['today_usd'])}"
                f" · Açık: {st['open_n']} pozisyon"
                f" · Toplam: {_fmt_usd(st['total_usd'])}"
            )
            title = f"PUSU — Günlük Özet ({day_no}. gün)"
            if args.dry_run:
                print(f"[dry] {uid[:8]} :: {title} :: {body}")
                continue
            store.push_user(conn, uid, title, body,
                            tag="newuser-digest", url="/portfoy", kind="system")
            print(f"[newuser-digest] kuyruklandı {uid[:8]} gün{day_no}: {body}")
    except Exception as e:  # noqa: BLE001 — raporcu asla cron'u kırmaz
        print(f"[newuser-digest] hata (yut): {e}")
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    main()
