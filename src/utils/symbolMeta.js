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

export const marketLabel = (symbol) => MARKET_LABEL[marketOf(symbol)];

// Long, human-readable "which cell does this symbol trade under" label.
// karma is per-symbol (from karmaMap); the other modules are uniform.
export const strategyCellLabel = (strategy, symbol, karmaMap) => {
  if (strategy === 'karma') {
    const sel = karmaMap?.[symbol];
    if (!sel) return '—';                       // unmapped → karma doesn't trade it
    return `${sel.set === 'impulse' ? 'Impulse' : 'Main'} · ${sel.half ? '½TP' : 'Tam'}`;
  }
  if (strategy === 'main_half') return 'Main · ½TP';
  if (strategy === 'impulse_half') return 'Impulse · ½TP';
  if (strategy === 'impulse') return 'Impulse';
  return 'Main';
};

// Compact badge for dense lists (the symbol picker).
export const strategyBadge = (strategy, symbol, karmaMap) => {
  if (strategy !== 'karma') return null;        // uniform elsewhere → no per-row badge
  const sel = karmaMap?.[symbol];
  if (!sel) return '—';
  return `${sel.set === 'impulse' ? 'I' : 'M'}${sel.half ? '·½' : ''}`;
};
