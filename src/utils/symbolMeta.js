// Symbol metadata: market (asset-class) grouping + per-symbol strategy labels.
// Pure module — no React, no context import (so it can't create an import cycle).
//
// Market buckets used by the dashboard filters:
//   metal  — gold/silver perps
//   stock  — tokenized US equities / ETFs (Binance TRADIFI perps)
//   crypto — everything else (fallback)

export const METAL_SYMBOLS = new Set(['XAUUSDT', 'XAGUSDT']);

// US equity / ETF tokenized perps (the 2026-06-12 expansion + the original stock perps).
export const STOCK_SYMBOLS = new Set([
  'NVDAUSDT', 'METAUSDT', 'AMZNUSDT', 'COINUSDT', 'MSTRUSDT',
  'CRCLUSDT', 'PLTRUSDT', 'TSLAUSDT', 'INTCUSDT', 'HOODUSDT',
  'MSFTUSDT', 'AVGOUSDT', 'BABAUSDT', 'BXUSDT', 'HPEUSDT',
  'AMATUSDT', 'CRWDUSDT', 'CRDOUSDT', 'AAOIUSDT', 'IWMUSDT',
]);

// key -> { label, test } ; order = chip display order. 'all' is handled by callers.
export const MARKETS = [
  { key: 'crypto', label: 'Kripto', test: (s) => !METAL_SYMBOLS.has(s) && !STOCK_SYMBOLS.has(s) },
  { key: 'metal', label: 'Metal', test: (s) => METAL_SYMBOLS.has(s) },
  { key: 'stock', label: 'ABD Hisse', test: (s) => STOCK_SYMBOLS.has(s) },
];

const MARKET_LABEL = { crypto: 'Kripto', metal: 'Metal', stock: 'ABD Hisse' };

export const marketOf = (symbol) =>
  METAL_SYMBOLS.has(symbol) ? 'metal' : STOCK_SYMBOLS.has(symbol) ? 'stock' : 'crypto';

// ---- OPUS: per-symbol NY-session allowlist (mirror of sync/opus_map.py) ----
// Each symbol is traded only in the NY session(s) where its 2026 signals had an
// edge. 'am' = 09:00–12:00 ET, 'pm' = 12:00–16:00 ET. Symbols absent → not traded.
export const OPUS_MAP = {
  BTCUSDT: ['am'], ETHUSDT: ['am'], BNBUSDT: ['am'], SUSDT: ['am'],
  CRCLUSDT: ['am'], ONDOUSDT: ['am'], XAGUSDT: ['am'], SUIUSDT: ['am'], INTCUSDT: ['am'],
  MSTRUSDT: ['am', 'pm'], ARBUSDT: ['am', 'pm'], FETUSDT: ['am', 'pm'],
  WIFUSDT: ['pm'], '1000PEPEUSDT': ['pm'], COINUSDT: ['pm'], HOODUSDT: ['pm'],
  // 2026-06-13 crypto re-add: only edge sessions (LINK NY-PM +8.3R; DOGE NY-PM +1.0R marginal).
  LINKUSDT: ['pm'], DOGEUSDT: ['pm'],
};

// Hour-of-day in America/New_York for a UTC timestamp (DST handled by Intl).
const _etHourFmt = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York', hour: '2-digit', hour12: false,
});
const _etWeekdayFmt = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York', weekday: 'short',
});
export const etHour = (utc) => {
  const h = parseInt(_etHourFmt.format(new Date(utc)), 10);
  return h === 24 ? 0 : h;        // some engines render midnight as '24'
};
export const isWeekendET = (utc) => {
  const d = _etWeekdayFmt.format(new Date(utc));
  return d === 'Sat' || d === 'Sun';    // US market closed
};
export const opusSession = (utc) => {
  if (isWeekendET(utc)) return null;     // weekend = no US session
  const h = etHour(utc);
  if (h >= 9 && h < 12) return 'am';
  if (h >= 12 && h < 16) return 'pm';
  return null;
};
// signal_time = bar OPEN (UTC); keep iff the symbol trades that session.
export const opusAllows = (symbol, signalTimeUtc) => {
  const sess = OPUS_MAP[symbol];
  if (!sess) return false;
  const s = opusSession(signalTimeUtc);
  return s !== null && sess.includes(s);
};

export const marketLabel = (symbol) => MARKET_LABEL[marketOf(symbol)];

// Long, human-readable "which cell does this symbol trade under" label.
// karma/karma_half are per-symbol (from karmaMap); the other modules are uniform.
// karma_half forces the ½TP exit; karma uses each symbol's chosen exit.
// A '_chop' suffix = same as the parent + a 4h-ER regime gate; label gets "· Chop".
export const strategyCellLabel = (strategy, symbol, karmaMap) => {
  if (strategy === 'choponly') return 'Main · Choppy (test)';
  if (strategy.endsWith('_chop')) {
    const base = strategyCellLabel(strategy.slice(0, -5), symbol, karmaMap);
    return base === '—' ? base : `${base} · Chop`;
  }
  if (strategy === 'karma' || strategy === 'karma_half') {
    const sel = karmaMap?.[symbol];
    if (!sel) return '—';                       // unmapped → karma doesn't trade it
    const exit = strategy === 'karma_half' ? '½TP' : (sel.half ? '½TP' : 'Tam');
    return `${sel.set === 'impulse' ? 'Impulse' : 'Main'} · ${exit}`;
  }
  if (strategy === 'opus' || strategy === 'opus_half') {
    const sess = OPUS_MAP[symbol];
    if (!sess) return '—';
    const w = `NY-${sess.map((s) => s.toUpperCase()).join('/')}`;   // e.g. "NY-AM", "NY-AM/PM"
    return strategy === 'opus_half' ? `${w} · ½TP` : w;
  }
  if (strategy === 'main_half') return 'Main · ½TP';
  if (strategy === 'impulse_half') return 'Impulse · ½TP';
  if (strategy === 'impulse') return 'Impulse';
  return 'Main';
};

// Compact badge for dense lists (the symbol picker).
export const strategyBadge = (strategy, symbol, karmaMap) => {
  if (strategy === 'choponly') return 'choppy';
  if (strategy.endsWith('_chop')) {
    const base = strategyBadge(strategy.slice(0, -5), symbol, karmaMap);
    return base ? `${base}·ch` : 'ch';
  }
  if (strategy === 'opus' || strategy === 'opus_half') {
    const sess = OPUS_MAP[symbol];
    if (!sess) return '—';
    return strategy === 'opus_half' ? `${sess.join('/')}·½` : sess.join('/');
  }
  if (strategy !== 'karma' && strategy !== 'karma_half') return null;  // uniform elsewhere
  const sel = karmaMap?.[symbol];
  if (!sel) return '—';
  const half = strategy === 'karma_half' ? true : sel.half;
  return `${sel.set === 'impulse' ? 'I' : 'M'}${half ? '·½' : ''}`;
};
