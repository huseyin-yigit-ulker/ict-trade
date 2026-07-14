/* eslint-env serviceworker */
/* global self, caches, fetch, URL */
//
// PUSU service worker (vite-plugin-pwa `injectManifest`).
//
// Design constraints specific to a LIVE trading dashboard:
//  - Precache the app SHELL only (hashed JS/CSS/HTML/icons/fonts).
//  - NEVER cache trading data. Supabase / Binance / CoinGecko / TradingView are
//    all cross-origin, so we simply do not intercept them — the browser fetches
//    them from the network every time. No stale signals, ever.
//  - Cache name is derived from the precache revision, so every deploy activates
//    a fresh cache and fully evicts the old shell (protects against a stale
//    bundle pinning a rotated anon key).
//
// Vanilla (no workbox-runtime imports) on purpose: keeps the dependency surface
// to just the build-time vite-plugin-pwa, and our caching needs are simple.

// Injected at build by vite-plugin-pwa: [{ url, revision }, ...]
const MANIFEST = self.__WB_MANIFEST || []
const PRECACHE_URLS = MANIFEST.map((e) => e.url)

// Derive a cache name from the manifest so it changes on every content change.
const REV = MANIFEST.map((e) => (e.revision || '') + e.url).join('|')
let _h = 0
for (let i = 0; i < REV.length; i++) _h = (Math.imul(_h, 31) + REV.charCodeAt(i)) >>> 0
const CACHE = 'pusu-shell-' + _h.toString(36)

self.addEventListener('install', (event) => {
  self.skipWaiting()
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(PRECACHE_URLS)).catch(() => {}),
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  const req = event.request
  if (req.method !== 'GET') return
  const url = new URL(req.url)

  // Cross-origin (Supabase/Binance/CoinGecko/TradingView) -> untouched network.
  if (url.origin !== self.location.origin) return

  // SPA navigations -> serve the cached app shell (offline-capable deep links).
  if (req.mode === 'navigate') {
    event.respondWith(
      caches.match('/index.html').then((cached) => cached || fetch(req)),
    )
    return
  }

  // Precached static assets -> cache-first; anything else -> network.
  event.respondWith(caches.match(req).then((cached) => cached || fetch(req)))
})

// ---------------------------------------------------------------------------
// Web Push (Phase 3). Inert until a subscription is created in Settings and the
// VM sender starts posting. Payload shape (JSON): { title, body, url, tag }.
// ---------------------------------------------------------------------------
self.addEventListener('push', (event) => {
  let data = {}
  try {
    data = event.data ? event.data.json() : {}
  } catch {
    data = { body: event.data ? event.data.text() : '' }
  }
  const title = data.title || 'PUSU'
  const options = {
    body: data.body || '',
    icon: '/icons/icon-192.png',
    badge: '/icons/icon-192.png',
    // null/undefined tag "null" string'ine dönüşüp bildirimleri YANLIŞLIKLA birleştirmesin;
    // boş/eksik tag = coalesce yok (her olay ayrı kart).
    tag: data.tag || undefined,
    data: { url: data.url || '/' },
  }
  event.waitUntil(self.registration.showNotification(title, options))
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const target = (event.notification.data && event.notification.data.url) || '/'
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
      for (const c of list) {
        if ('focus' in c) {
          if ('navigate' in c) c.navigate(target)
          return c.focus()
        }
      }
      if (self.clients.openWindow) return self.clients.openWindow(target)
    }),
  )
})
