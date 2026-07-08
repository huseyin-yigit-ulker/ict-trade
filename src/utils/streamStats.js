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
// 2026-07-04 PRIVACY: PUSU is multi-user — the descriptive labels moved to
// utils/adminStreamInfo.js (admin-only lazy chunk). This registry keeps ONLY the
// version keys + filter axes; `label` is the anonymized codename so nothing in
// the shared bundle reveals the mechanics. Render names via useStreamDisplay().
import { codenameFor } from './streamMask';

const S = (key, exit) => ({ key, version: key, exit, family: 'trend', tf: '', realistic: true, label: codenameFor(key) });

export const STREAMS = [
  // ── 1h family ──
  S('donchianc', 'full'),
  S('d1h_so4c', 'scaleout'), S('d1h_so6c', 'scaleout'), S('d1h_so8c', 'scaleout'),
  S('d1hso4cm', 'scaleout'), S('d1hso6cm', 'scaleout'), S('d1hso8cm', 'scaleout'),
  // ── 30m + 4h family ──
  S('dch30_4hc', 'full'), S('dch30_4h6c', 'full'),
  S('d30_4h_soc', 'scaleout'), S('d30so6c', 'scaleout'), S('d30so8c', 'scaleout'),
  S('d30so4cm', 'scaleout'), S('d30so6cm', 'scaleout'), S('d30so8cm', 'scaleout'),
  S('d30so4f3', 'scaleout'), S('d30so6f3', 'scaleout'), S('d30so8f3', 'scaleout'),
  S('d30so8f3h7', 'scaleout'),   // canlı gerçek-para akışı (OPUS)
  S('d30so8f3vg', 'scaleout'),   // 2026-07-07: backtest-only'ye indirildi (canlı emit emekli)
  // ── altın akışları ──
  S('midas', 'full'),
  S('talos', 'full'),
  S('talos_ichi', 'full'),   // araştırma/paper: TALOS + Ichimoku Kumo yön filtresi
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
