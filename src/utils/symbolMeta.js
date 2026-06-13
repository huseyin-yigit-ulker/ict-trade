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

// ---- Price-regime classification (4h Efficiency Ratio) for the TREND map ----
// Bands match the regime study table: chop < 0.20, light 0.20-0.35, mid 0.35-0.50,
// strong >= 0.50. Pure price-data classification (no signals/backtest).
export const REGIME_BANDS = [
  { key: 'strong', min: 0.50, label: 'Güçlü Trend', color: '#0ECB81' },
  { key: 'mid',    min: 0.35, label: 'Orta Trend',  color: '#5C93FF' },
  { key: 'light',  min: 0.20, label: 'Hafif Trend', color: '#F5B942' },
  { key: 'chop',   min: 0,    label: 'Choppy',      color: '#F6465D' },
];
export const regimeOf = (er) =>
  REGIME_BANDS.find((b) => er >= b.min) || REGIME_BANDS[REGIME_BANDS.length - 1];

// Kaufman Efficiency Ratio series from a closes array (NaN for the first n).
export const efficiencyRatio = (closes, n = 10) => {
  const out = new Array(closes.length).fill(NaN);
  for (let i = n; i < closes.length; i += 1) {
    const change = Math.abs(closes[i] - closes[i - n]);
    let vol = 0;
    for (let j = i - n + 1; j <= i; j += 1) vol += Math.abs(closes[j] - closes[j - 1]);
    out[i] = vol > 0 ? change / vol : 0;
  }
  return out;
};

// Trend/chop boundary used by both the regime map and the strategies' chop gate.
export const REGIME_ER_MIN = 0.25;

// ---- How ACCURATE is the regime label as a PREDICTOR? -----------------------
// The trailing ER label is exact for the window it measures (it IS that window).
// The honest test is whether it predicts the NEXT window: the trailing label at
// bar i is series[i] (closes[i-n..i]); the realized forward label is series[i+n]
// (closes[i..i+n]) — disjoint windows sharing only closes[i], so no overlap
// tautology. Mirrors sync/regime_accuracy.py.
//   overall  P(forward class == trailing class)          — is the label right
//   contP    P(price keeps its direction | labelled trend)— does a "trend" hold
//   base     realized forward trend rate ; baseline = max(base, 1-base)
//   lift     overall - baseline  (skill ABOVE guessing the majority class)
// Returns null when there aren't enough evaluable bars (new listings).
export const regimeAccuracy = (closes, n = 10, erMin = REGIME_ER_MIN, minN = 120) => {
  if (!Array.isArray(closes) || closes.length < 2 * n + minN) return null;
  const er = efficiencyRatio(closes, n);
  const sgn = (x) => (x > 0 ? 1 : x < 0 ? -1 : 0);
  let agree = 0, total = 0, trendT = 0, trendHit = 0, cont = 0, rt = 0;
  for (let i = n; i < closes.length - n; i += 1) {
    const a = er[i], b = er[i + n];                   // trailing label vs forward label
    if (!Number.isFinite(a) || !Number.isFinite(b)) continue;
    const pTr = a >= erMin, rTr = b >= erMin;
    total += 1; if (rTr) rt += 1;
    if (pTr === rTr) agree += 1;
    if (pTr) {
      trendT += 1;
      if (rTr) trendHit += 1;
      if (sgn(closes[i] - closes[i - n]) === sgn(closes[i + n] - closes[i])) cont += 1;
    }
  }
  if (total < minN) return null;
  const base = rt / total;
  const baseline = Math.max(base, 1 - base);
  const overall = agree / total;
  return {
    n: total, overall, baseline, lift: overall - baseline, base,
    contP: trendT ? cont / trendT : null,
    trendP: trendT ? trendHit / trendT : null,
  };
};

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
// karma is per-symbol (from karmaMap, with its own ½TP/Tam exit); the other modules
// are uniform. A '_light' suffix = same as the parent + a 4h-ER light-band gate; the
// label gets "· Light".
export const strategyCellLabel = (strategy, symbol, karmaMap) => {
  if (strategy.endsWith('_light')) {
    const base = strategyCellLabel(strategy.slice(0, -6), symbol, karmaMap);
    return base === '—' ? base : `${base} · Light`;
  }
  if (strategy === 'karma') {
    const sel = karmaMap?.[symbol];
    if (!sel) return '—';                       // unmapped → karma doesn't trade it
    return `${sel.set === 'impulse' ? 'Impulse' : 'Main'} · ${sel.half ? '½TP' : 'Tam'}`;
  }
  if (strategy === 'opus') {
    const sess = OPUS_MAP[symbol];
    if (!sess) return '—';
    return `NY-${sess.map((s) => s.toUpperCase()).join('/')}`;   // e.g. "NY-AM", "NY-AM/PM"
  }
  if (strategy === 'range') return 'Range-Dev · Tam';     // RANGE_DEV fade, full-TP, ER>=0.20
  if (strategy === 'impulse') return 'Impulse';
  return 'Main';
};

// Compact badge for dense lists (the symbol picker).
export const strategyBadge = (strategy, symbol, karmaMap) => {
  if (strategy.endsWith('_light')) {
    const base = strategyBadge(strategy.slice(0, -6), symbol, karmaMap);
    return base ? `${base}·lt` : 'lt';
  }
  if (strategy === 'opus') {
    const sess = OPUS_MAP[symbol];
    if (!sess) return '—';
    return sess.join('/');
  }
  if (strategy !== 'karma') return null;  // uniform elsewhere
  const sel = karmaMap?.[symbol];
  if (!sel) return '—';
  return `${sel.set === 'impulse' ? 'I' : 'M'}${sel.half ? '·½' : ''}`;
};
