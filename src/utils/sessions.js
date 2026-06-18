// Market-session status (crypto / US equities / metals) for the dashboard's "Seanslar"
// info window. Mirrors the backend signal gate in sync/donchian/strategy.py:
//   • US stock-perps fire ONLY during pre-market+regular hours (Mon-Fri 04:00-16:00 ET,
//     ex-NYSE holidays) — outside that the underlying doesn't trade, so signals are noise.
//   • Metals (XAU/XAG) trade ~24/5 with real global liquidity, so they are NOT gated
//     (backtest showed gating doesn't help) — shown for information only.
//   • Crypto is 24/7.
// All times resolved in America/New_York (DST-correct) via Intl.

// NYSE full-day closures 2024-2026 (ET dates) — mirror strategy.US_HOLIDAYS.
export const US_HOLIDAYS = new Set([
  '2024-01-01', '2024-01-15', '2024-02-19', '2024-03-29', '2024-05-27', '2024-06-19',
  '2024-07-04', '2024-09-02', '2024-11-28', '2024-12-25',
  '2025-01-01', '2025-01-20', '2025-02-17', '2025-04-18', '2025-05-26', '2025-06-19',
  '2025-07-04', '2025-09-01', '2025-11-27', '2025-12-25',
  '2026-01-01', '2026-01-19', '2026-02-16', '2026-04-03', '2026-05-25', '2026-06-19',
  '2026-07-03', '2026-09-07', '2026-11-26', '2026-12-25',
]);

const WD = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
const ET_FMT = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York', weekday: 'short', hour12: false,
  hour: '2-digit', minute: '2-digit', year: 'numeric', month: '2-digit', day: '2-digit',
});

// New-York wall-clock parts for an instant: weekday 0-6, minutes-of-day, ISO date.
export const etParts = (d = new Date()) => {
  const p = ET_FMT.formatToParts(d).reduce((a, x) => { a[x.type] = x.value; return a; }, {});
  const hour = parseInt(p.hour === '24' ? '0' : p.hour, 10);
  const minute = parseInt(p.minute, 10);
  return { weekday: WD[p.weekday], hour, minute, mod: hour * 60 + minute,
           date: `${p.year}-${p.month}-${p.day}`, hhmm: `${p.hour}:${p.minute}` };
};

const isHoliday = (date) => US_HOLIDAYS.has(date);

// state: 'open' | 'premarket' | 'closed' | 'break'
export const cryptoStatus = () => ({ state: 'open', label: '7/24 Açık', note: 'Her zaman aktif' });

export const usStatus = (d = new Date()) => {
  const { weekday, mod, date } = etParts(d);
  if (weekday === 0 || weekday === 6) return { state: 'closed', label: 'Kapalı', note: 'Hafta sonu' };
  if (isHoliday(date)) return { state: 'closed', label: 'Kapalı', note: 'Resmi tatil (NYSE)' };
  if (mod >= 4 * 60 && mod < 9 * 60 + 30) return { state: 'premarket', label: 'Pre-market', note: '04:00–09:30 ET' };
  if (mod >= 9 * 60 + 30 && mod < 16 * 60) return { state: 'open', label: 'Açık (Regular)', note: '09:30–16:00 ET' };
  return { state: 'closed', label: 'Kapalı', note: 'Seans dışı' };
};

export const metalStatus = (d = new Date()) => {
  const { weekday, mod } = etParts(d);
  if (weekday === 6) return { state: 'closed', label: 'Kapalı', note: 'Hafta sonu' };
  if (weekday === 5 && mod >= 17 * 60) return { state: 'closed', label: 'Kapalı', note: 'Hafta sonu (Cuma 17:00 ET kapanış)' };
  if (weekday === 0 && mod < 18 * 60) return { state: 'closed', label: 'Kapalı', note: 'Hafta sonu (Pazar 18:00 ET açılış)' };
  if (mod >= 17 * 60 && mod < 18 * 60) return { state: 'break', label: 'Mola', note: 'Günlük bakım 17:00–18:00 ET' };
  return { state: 'open', label: 'Açık', note: 'Paz 18:00 → Cum 17:00 ET' };
};

// Whether US stock-perp SIGNALS are active right now (matches the backend gate: pre-market
// or regular). Metals/crypto are never gated.
export const usSignalsActive = (d = new Date()) => ['premarket', 'open'].includes(usStatus(d).state);

// The full board for the info window.
export const marketSessions = (d = new Date()) => [
  { key: 'crypto', name: 'Kripto', symbols: 'BTC, ETH, SOL, …', gated: false, ...cryptoStatus() },
  { key: 'us',     name: 'ABD Hisse', symbols: 'NVDA, TSLA, MSFT, …', gated: true,  ...usStatus(d) },
  { key: 'metal',  name: 'Metaller', symbols: 'XAU, XAG', gated: false, ...metalStatus(d) },
];
