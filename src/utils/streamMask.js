// Stream anonymization — the PRIVACY boundary for non-admin users (2026-07-04).
//
// PUSU is multi-user now: outsiders must get NO idea what the strategies are.
// Every stream renders under a neutral CODENAME; the descriptive labels/cards
// (Donchian/VWAP/breakout/R-multiples...) render ONLY for the admin (owner),
// whose UI loads them via a dynamic import of adminStreamInfo.js — so the real
// strings live in a separate lazy chunk, NOT in the main bundle everyone gets.
//
// URLs use the codename slug too (…/atlas/backtest), because raw version keys
// like 'donchianc' or 'dch30_4hc' leak the mechanic on their own. slugToKey()
// still accepts the legacy raw keys so old bookmarks keep working.
//
// Codenames are deliberately meaning-free (no numbers that would hint at
// R-multiples or timeframes) and STABLE — never reassign an existing one.

export const CODENAMES = {
  // canlı modül
  d30so8f3h7: 'ATLAS',
  d30so8f3vg: 'NOVA',
  midas: 'SIRIUS',
  talos: 'ANTARES',
  // 1h ailesi (backtest-only)
  donchianc: 'VEGA',
  d1h_so4c: 'LYRA',
  d1h_so6c: 'CYGNI',
  d1h_so8c: 'ALTAIR',
  d1hso4cm: 'MIRA',
  d1hso6cm: 'DENEB',
  d1hso8cm: 'POLLUX',
  // 30m+4h ailesi (backtest-only)
  dch30_4hc: 'ORION',
  dch30_4h6c: 'RIGEL',
  d30_4h_soc: 'CASTOR',
  d30so6c: 'PERSEUS',
  d30so8c: 'AQUILA',
  d30so4cm: 'CEPHEUS',
  d30so6cm: 'PAVO',
  d30so8cm: 'CETUS',
  d30so4f3: 'HYDRA',
  d30so6f3: 'CORVUS',
  d30so8f3: 'DRACO',
};

// ── ürün sınırı: CANLI (işlem açılabilir) akışlar vs backtest-only araştırma varyantları ──
// Bu 2 akış canlı sinyal + kendi track record'unu taşır ve HERKESE görünür; CODENAMES'teki
// diğer HER kod, shipe edilmemiş bir backtest-only araştırma varyantıdır ve yalnız admin'e
// (ya da admin'in user_features.backtest=true ile açıkça yetki verdiği kullanıcıya) görünür.
// 2026-07-07: NOVA (d30so8f3vg) canlıdan çıkarıldı — backtest-only araştırma varyantı artık
// (canlı emit'i de emekli; nightly volgate_backfill backtest'ini tazelemeye devam eder).
// 2026-07-07: TALOS (talos/ANTARES) eklendi — 3. canlı akış, PAPER-only (executor'u yok).
export const LIVE_STREAM_KEYS = ['d30so8f3h7', 'midas', 'talos'];

/** True = backtest-only araştırma varyantı (canlı olmayan herhangi bir codename). */
export const isResearchStream = (key) => !!CODENAMES[key] && !LIVE_STREAM_KEYS.includes(key);

const SLUG_TO_KEY = Object.fromEntries(
  Object.entries(CODENAMES).map(([key, code]) => [code.toLowerCase(), key]),
);

/** Public display name for a stream — codename for everyone; admin UI may override. */
export const codenameFor = (key) => CODENAMES[key] || String(key || '').toUpperCase();

/** Generic non-revealing sublabel (used where the technical label used to render). */
export const genericLabel = (t) => t('Otonom işlem akışı · detaylar gizli');

/** URL slug for a stream (codename, lowercase). */
export const slugFor = (key) => (CODENAMES[key] ? CODENAMES[key].toLowerCase() : key);

/** Resolve a route slug back to the real stream key. Accepts legacy raw keys too. */
export const slugToKey = (slug) => SLUG_TO_KEY[String(slug || '').toLowerCase()] || slug;

// The XAU chart's anchor line ("o çizgi") renders under this neutral tag for
// everyone; the admin overlay may relabel it from adminStreamInfo.
export const REFLINE_LABEL = 'T-REF';

// ---- admin-only real names/labels/cards (lazy chunk; never in the main bundle) ----
let adminInfoPromise = null;

/** Load the admin-only stream info module. Call ONLY when profile.role==='admin'. */
export const loadAdminStreamInfo = () => {
  if (!adminInfoPromise) adminInfoPromise = import('./adminStreamInfo.js');
  return adminInfoPromise;
};
