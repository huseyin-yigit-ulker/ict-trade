// Shared strategy-stream metadata + the live 2026 backtest result fetch.
// Used by both the intro hub (IntroPage) and the read-only login showcase
// (LoginScreen). Pure module — no React. Pulls the same backtest_summary_metrics
// RPC the dashboard uses, one call per version, cached for the session.

// Stream → RPC version tag (mirror of TradeContext STRATEGY_VERSION) + the axes
// the hub filters on: exit model (full / half / per-symbol mixed) and family.
export const STREAMS = [
  { key: 'main',         version: 'v1',         exit: 'full',  family: 'core' },
  { key: 'impulse',      version: 'v2',         exit: 'full',  family: 'core' },
  { key: 'opus',         version: 'opus',       exit: 'full',  family: 'session' },
  { key: 'karma',        version: 'karma',      exit: 'mixed', family: 'adaptive' },
  { key: 'main_half',    version: 'v3',         exit: 'half',  family: 'core' },
  { key: 'impulse_half', version: 'v4',         exit: 'half',  family: 'core' },
  { key: 'opus_half',    version: 'opus_half',  exit: 'half',  family: 'session' },
  { key: 'karma_half',   version: 'karma_half', exit: 'half',  family: 'adaptive' },
  // CHOP twins — parent + 4h-Efficiency-Ratio regime gate. Short version tags
  // (trading_signals.version is varchar(10)); mirror of backfill_chop.CHOP_TAG.
  { key: 'main_chop',         version: 'v1_chop',   exit: 'full', family: 'core',     chop: true },
  { key: 'impulse_chop',      version: 'v2_chop',   exit: 'full', family: 'core',     chop: true },
  { key: 'opus_chop',         version: 'ops_chop',  exit: 'full', family: 'session',  chop: true },
  { key: 'karma_chop',        version: 'kma_chop',  exit: 'mixed', family: 'adaptive', chop: true },
  { key: 'main_half_chop',    version: 'v3_chop',   exit: 'half', family: 'core',     chop: true },
  { key: 'impulse_half_chop', version: 'v4_chop',   exit: 'half', family: 'core',     chop: true },
  { key: 'opus_half_chop',    version: 'opsh_chop', exit: 'half', family: 'session',  chop: true },
  { key: 'karma_half_chop',   version: 'kmah_chop', exit: 'half', family: 'adaptive', chop: true },
  // LIGHT band-pass twins — keep only signals fired in the light-trend regime
  // (4h ER in [0.20,0.35)), where the 2026 routing audit found our edge lives.
  // Scope = core/½TP/karma (no opus). Short tags; mirror backfill_light.LIGHT_TAG.
  { key: 'main_light',         version: 'v1_light',   exit: 'full', family: 'core',     light: true },
  { key: 'impulse_light',      version: 'v2_light',   exit: 'full', family: 'core',     light: true },
  { key: 'karma_light',        version: 'kma_light',  exit: 'mixed', family: 'adaptive', light: true },
  { key: 'main_half_light',    version: 'v3_light',   exit: 'half', family: 'core',     light: true },
  { key: 'impulse_half_light', version: 'v4_light',   exit: 'half', family: 'core',     light: true },
  { key: 'karma_half_light',   version: 'kmah_light', exit: 'half', family: 'adaptive', light: true },
];

// Session cache, shared across the login showcase and the intro hub.
let STATS_CACHE = null;
export const getCachedStats = () => STATS_CACHE;

export const fetchAllSummaries = async () => {
  if (STATS_CACHE) return STATS_CACHE;
  const url = import.meta.env.BACKTESTING_VITE_SUPABASE_URL;
  const apiKey = import.meta.env.BACKTESTING_VITE_SUPABASE_PUBLISHABLE_DEFAULT_KEY;
  if (!url || !apiKey) throw new Error('config');
  // The analytics functions live in the ict_trade schema; a POST resolves the
  // function schema from Content-Profile (not Accept-Profile) — set both.
  const call = async (version) => {
    const res = await fetch(`${url}/rest/v1/rpc/backtest_summary_metrics`, {
      method: 'POST',
      headers: {
        apikey: apiKey,
        Authorization: `Bearer ${apiKey}`,
        'Accept-Profile': 'ict_trade',
        'Content-Profile': 'ict_trade',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ p_version: version }),
    });
    if (!res.ok) throw new Error(`rpc ${version} ${res.status}`);
    const rows = await res.json();
    return Array.isArray(rows) ? rows[0] || null : null;
  };
  const settled = await Promise.allSettled(STREAMS.map((s) => call(s.version)));
  const out = {};
  settled.forEach((r, i) => { out[STREAMS[i].version] = r.status === 'fulfilled' ? r.value : null; });
  STATS_CACHE = out;
  return out;
};

export const fmtR = (v) => `${v >= 0 ? '+' : ''}${Number(v).toFixed(1)}R`;
export const fmtExp = (v) => `${v >= 0 ? '+' : ''}${Number(v).toFixed(2)}R`;
export const fmtPct = (v) => `${Number(v).toFixed(1)}%`;
export const fmtPf = (v) => (v == null || !Number.isFinite(Number(v)) ? '--' : Number(v).toFixed(2));
