// TOTAL / TOTAL2 / TOTAL3 market-cap breadth — browser mirror of sync/marketcap.py.
// Two data layers, exactly like the Python module:
//   1. LIVE (exact): CoinGecko /global → TOTAL + BTC/ETH dominance → TOTAL2/3.
//   2. PROXY (history): Σ Binance 4h close × circulating supply over the top
//      non-stable coins (stablecoins excluded = a risk-asset cap). The breadth
//      REGIME (risk_on/off/neutral) is read off the TOTAL3 EMA slope.
// No backtest/signals here — pure market data, same as the regime map.

import { fetchRegimeKlines } from './symbolMeta';

// Effective circulating supplies (snapshot 2026-06-16 from CoinGecko, cached in
// sync/out/marketcap_supplies.json). 1000PEPE is stored ÷1000 because Binance
// quotes 1000PEPEUSDT per 1000 tokens — so close × supply stays in single-token USD.
export const PROXY_SUPPLIES = {
  BTCUSDT: 20043446,
  ETHUSDT: 120684109,
  BNBUSDT: 134783632.7,
  XRPUSDT: 62053900985,
  SOLUSDT: 580059029,
  DOGEUSDT: 154680576383,
  ADAUSDT: 37206017184,
  TRXUSDT: 94831560057,
  LINKUSDT: 727099970,
  AVAXUSDT: 431771961,
  SUIUSDT: 4029196852,
  NEARUSDT: 1298363137,
  LTCUSDT: 77282783,
  DOTUSDT: 1688922443,
  ARBUSDT: 6255821492,
  ONDOUSDT: 4869330647,
  '1000PEPEUSDT': 420690000000, // 4.2069e14 PEPE ÷ 1000
};

const EMA_SPAN = 10;      // 4h EMA of TOTAL3 (~1.7 days)
const SLOPE_N = 6;        // bars back for the slope read (~1 day)
const SLOPE_EPS = 0.005;  // |Δ| below this = neutral (0.5% over SLOPE_N bars)

export const BREADTH_REGIMES = {
  risk_on: { key: 'risk_on', label: 'Risk-On', color: '#0ECB81' },
  neutral: { key: 'neutral', label: 'Nötr', color: '#848E9C' },
  risk_off: { key: 'risk_off', label: 'Risk-Off', color: '#F6465D' },
  unknown: { key: 'unknown', label: 'Bilinmiyor', color: '#848E9C' },
};

export const regimeFromSlope = (slope) => {
  if (slope == null || !Number.isFinite(slope)) return BREADTH_REGIMES.unknown;
  if (slope > SLOPE_EPS) return BREADTH_REGIMES.risk_on;
  if (slope < -SLOPE_EPS) return BREADTH_REGIMES.risk_off;
  return BREADTH_REGIMES.neutral;
};

// Exact live TOTAL/2/3 from CoinGecko /global (CORS-enabled). null on failure.
export const fetchGlobal = async () => {
  try {
    const res = await fetch('https://api.coingecko.com/api/v3/global');
    const d = (await res.json())?.data;
    if (!d) return null;
    const total = Number(d.total_market_cap?.usd);
    const btcD = Number(d.market_cap_percentage?.btc ?? 0) / 100;
    const ethD = Number(d.market_cap_percentage?.eth ?? 0) / 100;
    if (!Number.isFinite(total)) return null;
    return {
      total,
      total2: total * (1 - btcD),
      total3: total * (1 - btcD - ethD),
      btcD,
      ethD,
    };
  } catch { return null; }
};

const ema = (arr, span) => {
  const k = 2 / (span + 1);
  const out = [];
  let prev;
  for (const v of arr) {
    prev = prev === undefined ? v : v * k + prev * (1 - k);
    out.push(prev);
  }
  return out;
};

// Build the proxy TOTAL3 series + current breadth regime from Binance 4h klines.
// Returns { points:[{t, total3}], btcD, regime, slope } or null. `days` bounds the
// fetch window (keeps it light — we only need the recent slope + a sparkline).
export const buildBreadth = async (days = 90) => {
  const startMs = Date.now() - days * 24 * 60 * 60 * 1000;
  const syms = Object.keys(PROXY_SUPPLIES);
  const series = await Promise.all(syms.map(async (s) => {
    try {
      const k = await fetchRegimeKlines(s, '4h', startMs);
      return [s, Array.isArray(k) ? k : []];
    } catch { return [s, []]; }
  }));

  // close maps keyed by bar-open time, per coin
  const caps = {};
  for (const [s, k] of series) {
    const sup = PROXY_SUPPLIES[s];
    const m = new Map();
    for (const row of k) {
      const c = Number(row[4]);
      if (Number.isFinite(c)) m.set(Number(row[0]), c * sup);
    }
    caps[s] = m;
  }
  const btc = caps.BTCUSDT;
  if (!btc || btc.size < EMA_SPAN + SLOPE_N + 2) return null;

  // anchor on BTC's timestamps; sum the coins present at each bar
  const times = [...btc.keys()].sort((a, b) => a - b);
  const total = [], total2 = [], total3 = [], btcShare = [];
  for (const t of times) {
    let sum = 0;
    for (const s of syms) { const v = caps[s].get(t); if (v) sum += v; }
    const b = btc.get(t) || 0;
    const e = caps.ETHUSDT?.get(t) || 0;
    total.push(sum);
    total2.push(sum - b);
    total3.push(sum - b - e);
    btcShare.push(sum > 0 ? b / sum : NaN);
  }

  const t3ema = ema(total3, EMA_SPAN);
  const i = t3ema.length - 1;
  const past = t3ema[i - SLOPE_N];
  const slope = past ? (t3ema[i] - past) / past : null;

  return {
    times, total, total2, total3, btcDSeries: btcShare,
    points: times.map((t, j) => ({ t, total3: total3[j] })),
    btcD: btcShare[btcShare.length - 1],
    regime: regimeFromSlope(slope),
    slope,
  };
};

export const fmtUsd = (x) => {
  if (!Number.isFinite(x)) return '—';
  if (Math.abs(x) >= 1e12) return `$${(x / 1e12).toFixed(2)}T`;
  if (Math.abs(x) >= 1e9) return `$${(x / 1e9).toFixed(0)}B`;
  if (Math.abs(x) >= 1e6) return `$${(x / 1e6).toFixed(0)}M`;
  return `$${x.toFixed(0)}`;
};
