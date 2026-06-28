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
  // 2026-06-20: ONLY the realistic-entry (·0.5R) versions remain. The optimistic entry@close
  // twins (donchian/dch30_4h/dch30_4h6/d30_4h_so) were removed from UI + DB — their entry was
  // unrealistic (you can't fill at the breakout close when the trade only confirms +0.5R later).
  // These enter at the +0.5R confirmation level; R is against the real (1.5×) risk (RR 4→2.33).
  //
  // ORDER = by timeframe family, each family's full-TP base first, then its scale-out caps:
  //   1h family   : donchianc (full-TP) -> d1h_so4c / d1h_so6c / d1h_so8c (scale-out 4/6/8R)
  //   30m+4h family: dch30_4hc / dch30_4h6c (full-TP) -> d30_4h_soc / d30so6c / d30so8c (scale-out)
  // 2026-06-23: added the 1h scale-out family (d1h_so{4,6,8}c) — the 1h base entry (ER-gated, no
  // 4h confirm) resolved under the same +1R-then-runner-cap exit as the 30m+4h scale-out trio.
  // Names are deliberately explicit (d1h_so… vs d30so…) so the two families never collide.

  // ── 1h family ──
  { key: 'donchianc',    version: 'donchianc',    exit: 'full', family: 'trend', tf: '1h ·0.5R',      realistic: true, label: 'DONCHIAN 1h ·0.5R' },
  { key: 'd1h_so4c',     version: 'd1h_so4c',     exit: 'scaleout', family: 'trend', tf: '1h·WR 4R ·0.5R', realistic: true, label: 'DONCHIAN 1h·WR 4R ·0.5R' },
  { key: 'd1h_so6c',     version: 'd1h_so6c',     exit: 'scaleout', family: 'trend', tf: '1h·WR 6R ·0.5R', realistic: true, label: 'DONCHIAN 1h·WR 6R ·0.5R' },
  { key: 'd1h_so8c',     version: 'd1h_so8c',     exit: 'scaleout', family: 'trend', tf: '1h·WR 8R ·0.5R', realistic: true, label: 'DONCHIAN 1h·WR 8R ·0.5R' },
  { key: 'd1hso4cm',     version: 'd1hso4cm',     exit: 'scaleout', family: 'trend', tf: '1h·WR 4R ·M0.25', realistic: true, label: 'DONCHIAN 1h·WR 4R ·M0.25' },
  { key: 'd1hso6cm',     version: 'd1hso6cm',     exit: 'scaleout', family: 'trend', tf: '1h·WR 6R ·M0.25', realistic: true, label: 'DONCHIAN 1h·WR 6R ·M0.25' },
  { key: 'd1hso8cm',     version: 'd1hso8cm',     exit: 'scaleout', family: 'trend', tf: '1h·WR 8R ·M0.25', realistic: true, label: 'DONCHIAN 1h·WR 8R ·M0.25' },

  // ── 30m + 4h family ──
  { key: 'dch30_4hc',    version: 'dch30_4hc',    exit: 'full', family: 'trend', tf: '30m+4h ·0.5R',  realistic: true, label: 'DONCHIAN 30m+4h ·0.5R' },
  { key: 'dch30_4h6c',   version: 'dch30_4h6c',   exit: 'full', family: 'trend', tf: '30m+4h·6R ·0.5R', realistic: true, label: 'DONCHIAN 30m+4h 6R ·0.5R' },
  { key: 'd30_4h_soc',   version: 'd30_4h_soc',   exit: 'scaleout', family: 'trend', tf: '30m+4h·WR 4R ·0.5R', realistic: true, label: 'DONCHIAN 30m+4h·WR 4R ·0.5R' },
  { key: 'd30so6c',      version: 'd30so6c',      exit: 'scaleout', family: 'trend', tf: '30m+4h·WR 6R ·0.5R', realistic: true, label: 'DONCHIAN 30m+4h·WR 6R ·0.5R' },
  { key: 'd30so8c',      version: 'd30so8c',      exit: 'scaleout', family: 'trend', tf: '30m+4h·WR 8R ·0.5R', realistic: true, label: 'DONCHIAN 30m+4h·WR 8R ·0.5R' },
  { key: 'd30so4cm',     version: 'd30so4cm',     exit: 'scaleout', family: 'trend', tf: '30m+4h·WR 4R ·M0.25', realistic: true, label: 'DONCHIAN 30m+4h·WR 4R ·M0.25' },
  { key: 'd30so6cm',     version: 'd30so6cm',     exit: 'scaleout', family: 'trend', tf: '30m+4h·WR 6R ·M0.25', realistic: true, label: 'DONCHIAN 30m+4h·WR 6R ·M0.25' },
  { key: 'd30so8cm',     version: 'd30so8cm',     exit: 'scaleout', family: 'trend', tf: '30m+4h·WR 8R ·M0.25', realistic: true, label: 'DONCHIAN 30m+4h·WR 8R ·M0.25' },
  { key: 'd30so4f3',     version: 'd30so4f3',     exit: 'scaleout', family: 'trend', tf: '30m+4h·WR 4R ·b30', realistic: true, label: 'DONCHIAN 30m+4h·WR 4R ·b30' },
  { key: 'd30so6f3',     version: 'd30so6f3',     exit: 'scaleout', family: 'trend', tf: '30m+4h·WR 6R ·b30', realistic: true, label: 'DONCHIAN 30m+4h·WR 6R ·b30' },
  { key: 'd30so8f3',     version: 'd30so8f3',     exit: 'scaleout', family: 'trend', tf: '30m+4h·WR 8R ·b30', realistic: true, label: 'DONCHIAN 30m+4h·WR 8R ·b30' },
  { key: 'd30so8f3h7',   version: 'd30so8f3h7',   exit: 'scaleout', family: 'trend', tf: '30m+4h·WR 8R ·b30·7g', realistic: true, label: 'DONCHIAN 30m+4h·WR 8R ·b30·7g' },
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
