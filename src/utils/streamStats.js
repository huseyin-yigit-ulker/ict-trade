// Shared strategy-stream metadata + the live 2026 backtest result fetch.
// Used by both the intro hub (IntroPage) and the read-only login showcase
// (LoginScreen). Pure module — no React. Pulls the same backtest_summary_metrics
// RPC the dashboard uses, one call per version, cached for the session.

// Stream → RPC version tag (mirror of TradeContext STRATEGY_VERSION) + the axes
// the hub filters on: exit model (full / half / per-symbol mixed) and family.
// 2026-06-14: the 6 OOS-negative streams (v1/v2/karma/opus + the two _light twins) were
// removed from UI + DB — all bled out-of-sample in 2025 (−60..−245R), in-sample period-fit.
// Only the OOS-positive "range book" survives, all backtest-only:
//   • range      — Burak RANGE_DEV range-deviation fade, full-TP, ensemble-trend gated (+9.2R OOS).
//   • range_q    — RANGE+ : same gate + RR>=2 + drop ensemble score [0.20,0.30) (+26.2R OOS).
//   • v2_light_r — IMPULSE·Light gated to the ensemble RANGE verdict (+15.5R OOS).
export const STREAMS = [
  // Strategy set = MAIN + RANGE + OPUS. (range_q / v2_light_r / range_1h / range_q_1h
  // DB rows remain but aren't surfaced.)
  // 2026-06-16: pruned to a SINGLE stream — donchian. MAIN/RANGE/OPUS removed (UI + DB);
  // see sync/donchian/RETIRED_STREAMS_REPORT.md.
  { key: 'donchian',     version: 'donchian',     exit: 'full', family: 'trend', tf: '1h' },
  // 2026-06-17: HYBRID — 30m breakout confirmed by 4h trend direction. The MTF-validation
  // winner: best stream overall, +1106R across 2024-26 (every year positive, fewest trades
  // of the 30m family). 2026-06-17: the base donch_30m (dominated by this) and the ½TP twin
  // dch30_4hh (2024-negative OOS) were removed — see sync/donchian/.
  { key: 'dch30_4h',     version: 'dch30_4h',     exit: 'full', family: 'trend', tf: '30m+4h' },
  // 2026-06-17: 6R-target twin — MFE study showed winners run to ~8R median, losers go
  // straight to stop; a 6R target ~doubles R/trade vs 4R in all 3 years (OOS-robust).
  { key: 'dch30_4h6',    version: 'dch30_4h6',    exit: 'full', family: 'trend', tf: '30m+4h·6R' },
  // 2026-06-19: HIGH-WIN-RATE scale-out twin — same 30m+4h entry + −1R stop, but book 60% at
  // +1R; runner (40%) exits at +4R cap / breakeven / 3-day time exit. WR set by the first target
  // (gated 76-80%), OOS-positive every year. version='d30_4h_so'.
  { key: 'd30_4h_so',    version: 'd30_4h_so',    exit: 'scaleout', family: 'trend', tf: '30m+4h·SO' },
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
