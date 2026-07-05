// Kullanıcı tercihleri (ict_trade.user_prefs) — tema/dil/açılış sayfası + bildirim
// tercihleri, kullanıcı-başına Supabase'te kalıcı. localStorage her zaman anlık
// fallback olarak kalır (contexts zaten oraya yazıyor); bu modül sadece oturum
// varken DB'ye senkronlar, oturum yokken sessiz no-op'tur.
//
// savePrefs BEST-EFFORT'tur: tema değiştirmek gibi bir UI aksiyonu, DB yazımı
// başarısız oldu diye asla bozulmamalı.

import { getJSON, authedFetch } from './supa';
import { loadSession } from './gotrue';

// Açılış sayfası seçenekleri (SettingsPage select'i + LoginScreen yönlendirmesi).
export const PAGE_CHOICES = [
  { path: '/', label: 'Genel Bakış' },
  { path: '/binance', label: 'Binance Pozisyonlar' },
  { path: '/trading', label: 'İşlem Merkezi' },
  { path: '/intelligence', label: 'İstihbarat' },
];

export const isValidPage = (p) => PAGE_CHOICES.some((c) => c.path === p);

/** Oturumdaki kullanıcının prefs satırı (yoksa null). */
export async function fetchPrefs() {
  const uid = loadSession()?.user?.id;
  if (!uid) return null;
  try {
    const rows = await getJSON(`user_prefs?select=*&user_id=eq.${uid}`);
    return rows?.[0] || null;
  } catch {
    return null;   // tablo henüz yok / geçici hata — varsayılanlarla devam
  }
}

/** Kısmi upsert — fire-and-forget. Oturum yoksa no-op. */
export async function savePrefs(partial) {
  const uid = loadSession()?.user?.id;
  if (!uid) return;
  try {
    await authedFetch('user_prefs?on_conflict=user_id', {
      method: 'POST',
      headers: { Prefer: 'resolution=merge-duplicates,return=minimal' },
      body: JSON.stringify({ user_id: uid, ...partial }),
    });
  } catch { /* best-effort */ }
}
