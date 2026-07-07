"""Mizah katmanı — telefon (Web Push) bildirimlerinin SONUNA kısa, strateji-nötr
bir espri satırı ekler (2026-07-07, kullanıcı isteği).

Kurallar:
  * YALNIZ push gövdesi süslenir — Telegram/owner kanalı ve bildirim başlığı aynen kalır.
  * kind='system' (acil durdur, anahtar geçersiz...) ASLA espri almaz — ciddiyet korunur.
  * Espriler strateji-nötr: mekanik/parametre/kural imâsı yok (anonimleştirme sınırı).
  * .env `PUSH_FLAIR=0|false|off` tüm katmanı kapatır (varsayılan: açık).
  * Best-effort: her hata sessizce yutulur, metin süssüz devam eder.
"""
from __future__ import annotations

import random
import re

# İşaretli R değeri ("+8.00R", "−1R", "-0.3R") — çıkış mesajından kazanç/kayıp sezgisi.
_R_SIGNED = re.compile(r"([+\-−])\s*\d+(?:[.,]\d+)?\s*R\b")

ENTRY = [
    "Pusu kuruldu — şimdi bekleme sanatı. 🎯",
    "Tetik çekildi, gerisi piyasada. 🏹",
    "Av sahada. Sessizlik lütfen. 🤫",
    "Girdik. Kahveni al, grafiği bırak. ☕",
    "Pozisyon açık — heyecan yok, disiplin var. 🧘",
]
SKIP = [
    "Bu el pas — her pusu kurulmaz. 🃏",
    "Kapı açılmadı; sabır da bir pozisyondur. 🚪",
    "Sistem 'bugün değil' dedi. Sistemi dinliyoruz. 🤖",
]
WIN = [
    "Av çantada. 🎉",
    "Kasa gülümsüyor. 😎",
    "Piyasa hesabı ödedi — bahşiş de bıraktı. 🧾",
    "Yeşil sana yakışıyor. 💚",
    "Güzel avdı. Sıradaki pusuya. 🏹",
]
LOSS = [
    "Av bu sefer kaçtı — stop dostumuzdur. 🛡️",
    "Küçük kayıp, büyük disiplin. Devam. ✊",
    "Piyasa 1 – PUSU 0. Rövanş sahada. 🥊",
    "Bugün balık yok; ağlar sağlam. 🎣",
    "Stop yedik, plan yerinde. Sistem işliyor. ⚙️",
]
FLAT = [
    "Berabere bitti — kimse üzülmedi. 🤝",
    "Süre doldu, düdük çaldı. ⏱️",
]
MILESTONE = [
    "Kâr kilitlendi — geri dönüşü yok. 🔒",
    "İlk hedef tamam, runner sahnede. 🏃",
    "Stop artık kale; gerisi bedava koşu. 🏰",
    "Bal cebe süzülüyor. 🍯",
]
SIGNAL = [
    "Radar öttü — göz ucuyla bakın. 📡",
    "Pusu bölgesi görüldü. 👀",
    "Formasyon sahnede, ışıklar piyasada. 🎬",
    "Sinyal geldi; heyecan yok, plan var. 🗺️",
]

_SKIP_WORDS = ("ATLANDI", "İPTAL", "IPTAL", "AÇILMADI")


def _enabled() -> bool:
    try:
        import trade_sync_common as tsc
        v = str(tsc._read_env().get("PUSH_FLAIR", "1")).strip().lower()
        return v not in ("0", "false", "off", "no")
    except Exception:  # noqa: BLE001 — env okunamazsa varsayılan: açık
        return True


def _exit_pool(text: str) -> list:
    """Çıkış bildirimi kazanç mı kayıp mı? İşaretli R değerlerinden, yoksa anahtar
    kelimelerden sez; karışıksa nötr kal."""
    up = text.upper()
    signs = {m.group(1) for m in _R_SIGNED.finditer(text)}
    neg = bool(signs & {"-", "−"})
    pos = "+" in signs
    if neg and not pos:
        return LOSS
    if pos and not neg:
        return WIN
    if "STOP" in up and "BREAKEVEN" not in up:
        return LOSS
    if "BREAKEVEN" in up or "CAP" in up or "TP" in up:
        return WIN
    return FLAT


def quip(kind: str, text: str = "") -> str | None:
    """kind için uygun espri satırı; espri yoksa/kapalıysa None.
    'system' ve bilinmeyen kind'lar bilinçli olarak None döner."""
    try:
        if not _enabled():
            return None
        up = (text or "").upper()
        if kind == "entry":
            pool = SKIP if any(w in up for w in _SKIP_WORDS) else ENTRY
        elif kind == "exit":
            pool = _exit_pool(text or "")
        elif kind == "milestone":
            pool = MILESTONE
        elif kind == "signal":
            pool = SIGNAL
        else:
            return None
        return random.choice(pool)
    except Exception:  # noqa: BLE001
        return None


def spice(kind: str, body: str) -> str:
    """Gövdenin sonuna espri satırını ekler (varsa); aksi halde gövde aynen döner."""
    q = quip(kind, body)
    return f"{body}\n{q}" if q else body
