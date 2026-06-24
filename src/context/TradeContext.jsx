import { createContext, useState, useEffect, useContext, useRef, useCallback, useMemo } from 'react';
import { opusAllows } from '../utils/symbolMeta';

const TradeContext = createContext();

//const BACKTEST_ALLOWED_HOURS = new Set([5, 7, 8, 9, 12, 13, 14,15, 16, 20, 21]);
// All 24 UTC hours. getUTCHours() returns 0-23 — the old set listed 1..24,
// which silently dropped every 00:xx UTC signal (and '24' never matched).
const BACKTEST_ALLOWED_HOURS = new Set(Array.from({ length: 24 }, (_, h) => h));
// Production set — XRP, TON, 1000SHIB, LINK, OP excluded after negative
// 2025+2026 backtest performance; DOGE/GOOGL cut 2026-06-10 after the Jan-Jun
// audit (PLTR/TSLA were cut too but re-added 2026-06-12 by user decision with
// the tokenized-equity expansion). Old rows for hidden symbols stay in the
// database but the dashboard hides them. Mirrors dag/dag.py SYMBOLS.
export const BACKTEST_ALLOWED_SYMBOLS = [
  'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT',
  '1000PEPEUSDT', 'WIFUSDT', 'SUIUSDT',
  'NEARUSDT', 'FETUSDT', 'ADAUSDT', 'SUSDT',
  'ARBUSDT', 'ORDIUSDT', 'ONDOUSDT',
  // 2026-06-13: crypto re-add by user decision (XRP/LINK/DOGE re-added, AVAX new).
  'XRPUSDT', 'DOGEUSDT', 'LINKUSDT', 'AVAXUSDT',
  'XAUUSDT', 'XAGUSDT',
  // Stock-backed perps (underlying equities)
  'NVDAUSDT', 'METAUSDT',
  'AMZNUSDT', 'COINUSDT', 'MSTRUSDT',
  // 2026-06-12 tokenized-equity expansion (listings 2026-01-28 .. 2026-06-08)
  'CRCLUSDT', 'PLTRUSDT', 'TSLAUSDT', 'INTCUSDT', 'HOODUSDT',
  'MSFTUSDT', 'AVGOUSDT', 'BABAUSDT', 'BXUSDT', 'HPEUSDT',
  'AMATUSDT', 'CRWDUSDT', 'CRDOUSDT', 'AAOIUSDT', 'IWMUSDT'
];

// Entry-fill timeout — mirrors the backtest engine (ict/config.py EXPIRY_MINUTES = 180):
// a signal's limit must be touched within 3h of the signal, else it's cancelled.
const ENTRY_EXPIRY_MINUTES = 180;
const STRATEGY_EXPIRY_MINUTES = { donchianc: 180, dch30_4hc: 180, dch30_4h6c: 180, d30_4h_soc: 180, d30so6c: 180, d30so8c: 180, d1h_so4c: 180, d1h_so6c: 180, d1h_so8c: 180 };

// Directional entry confirmation — MIRROR of backtest ict/config.ENTRY_CONFIRM_BUF. A trade is
// only opened if, within the fill window, price extends favourably (toward TP) by BUF*risk
// before moving adversely (toward SL) by BUF*risk; a reversal toward the stop -> not opened.
// Keep this in sync with the Python config so live and backtest agree.
const ENTRY_CONFIRM_BUF = 0.5;

// Strategy module -> backtest version tag. 'main' = original B/C/D/E set (v1);
// 'impulse' = refined v2 set (drop E + D disabled on ADA/XAU/ETH — see
// sync/backfill_v2_year.py). 'karma' = per-symbol best cell of {main,impulse} ×
// {tam,½TP} (sync/karma_map.py; the ½TP exit survives only here, per symbol).
// 'opus' = MAIN signals kept only in each symbol's edge NY-session (sync/opus_map.py).
// The two '_light' twins (added below) keep only signals fired in the 4h-ER light
// band. 2026-06-13 prune removed the standalone ½TP streams (v3/v4, karma_half,
// opus_half), the 8 Chop twins and the redundant Light cells (UI + DB).
// 'range' = Burak's RANGE_DEV range-deviation fade, full-TP, gated to ER>=0.20 (skip
// deep chop). Backtest-only stream (no live scanner yet) — sync/backfill_range.py.
// 'range_q' = the high-conviction RANGE variant ("Range+"): a strict subset of 'range'
// keeping the same ensemble-trend gate PLUS reward/risk>=2 and dropping ONLY the loser
// band — ensemble score in [0.20,0.30). The SL-pattern study found that mild-trend band
// + RR<2 is the loser cluster; excluding it (rather than a plain score>=0.30 floor) keeps
// the profitable score<0.20 tail, lifting 2025 OOS +9.2R->+26.2R vs the floor's +15.8R.
// Backtest-only. Built by sync/promote_range_q.py (subset of the resolved 'range' rows);
// equivalently backfill_range.py --version range_q --min-rr 2 --drop-score-band 0.20 0.30.
// 'v2_light_r' = IMPULSE·Light gated to the ensemble RANGE verdict (score<=-0.15) — the
// stream_rescue lead: the only non-RANGE_DEV subset that stays OOS-positive (2026 +30R,
// 2025 +15.5R), ICT structure in genuine chop. Strict subset of v2_light, backtest-only
// (no live scanner). Built by sync/promote_light_range.py.
// 2026-06-14: v1/v2/karma/opus + the v2_light/kma_light twins removed (UI + DB) — all
// OOS-negative in 2025 (period-fit). Only the OOS-positive backtest-only range book remains.
// range_1h / range_q_1h = experiment: same RANGE_DEV signals gated by the 6-detector
// ensemble computed on 1h bars instead of 4h (full universe 2026; sync/backfill_range_1h.py).
// 2026: 1h underperforms 4h — range_1h +42.0R vs range +60.7R; rangeq_1h +33.5R vs range_q +49.6R.
// Strategy set: MAIN + RANGE + OPUS. RANGE runs live every session (mode='range', dag.py
// scanner); OPUS live = MAIN 'live' emission gated per-symbol to its NY session; MAIN live =
// the same 'live' emission, ungated, all symbols. (range_q / v2_light_r / range_1h /
// range_q_1h DB rows kept but not surfaced.)
// 'donchian' = Donchian(55) breakout trend stream, the momentum complement to the
// RANGE/main book — gated to the strong-trend regime (Kaufman ER>=0.35) where main is
// weak, so it harvests exactly the regime RANGE leaves on the table (sync/donchian/).
// Live scanner: sync/donchian/canli.py (mode='donchian', hourly). 2026 +117.5R.
// 2026-06-16: pruned to a SINGLE stream — donchian. v1(MAIN)/opus/opus_half/range were
// removed from UI + DB (RETIRED_STREAMS_REPORT.md): v1 net −223R, opus OOS-negative
// (2026-overfit), range positive but dropped for focus. donchian is the only multi-year
// OOS-validated stream (2025 +662R, 2024 +179R, 2026 +288R).
// 'dch30_4h' = HYBRID: a 30m Donchian breakout TAKEN ONLY when the 4h trend agrees (4h
// close on the trade's side of its 55-bar Donchian midline). The 2026 MTF-validation
// winner: +349R vs the base 30m +240R, R/trade DOUBLED (~0.06 -> ~0.12) on ~30% fewer
// trades (less fee/slippage drag). 4h-direction confirm beats a 4h-ER gate (ER hurts).
// Live: canli.py --tf 30m --confirm-htf 4h (mode='dch30_4h', every :01/:31). The filter
// is applied at emit time, so only confirmed signals ever reach the live table.
// 2026-06-17: pruned to donchian (1h) + dch30_4h (hybrid). The base donch_30m was dominated
// by the hybrid (which beats it every OOS year with ~30% fewer trades); the ½TP twin
// dch30_4hh was 2024-negative OOS. Both removed from UI + DB + live.
// 'dch30_4h6' = the 6R-target twin of the hybrid (same 30m breakout + 4h confirm, same -1R
// stop, wider TP at 6R). The MFE study found winners run to ~8R median while losers go
// straight to stop, so a wider target ~doubles R/trade vs 4R in ALL THREE years (OOS-robust)
// — the only robust improvement found. Trade-off: WR ~15% (vs 23%), lumpier curve; resolves
// fast (TP median ~1.4d, SL ~6h). Live: canli.py --tf 30m --confirm-htf 4h --rr 6.
// 'd30_4h_so' = the HIGH-WIN-RATE scale-out twin (the opposite end of the same edge). SAME
// 30m+4h entry + −1R stop as dch30_4h, but the exit scales out: book 60% at +1R (this sets
// the WR), pull the runner's stop to breakeven; the runner (40%) then exits at the FIRST of
// +4R cap (== the signal's own TP), breakeven, or a 3-day time-exit (2026-06-19 user decision —
// caps runner duration ≤3d and per-trade R ≤2.2R). ~76-80% WR (gated), OOS-positive every year.
// No own emitter: it RESOLVES the dch30_4h live signals under the scale-out model
// (sync/donchian/scaleout.py), exactly as karma/½TP reuse their parent's live signals.
// d1h_so{4,6,8}c = the 1h scale-out family (backtest-only): the 1h donchian base entry
// (ER-gated, no 4h confirm) resolved under the SAME +1R-then-runner-cap exit as d30so*.
const STRATEGY_VERSION = { donchianc: 'donchianc', dch30_4hc: 'dch30_4hc', dch30_4h6c: 'dch30_4h6c', d30_4h_soc: 'd30_4h_soc', d30so6c: 'd30so6c', d30so8c: 'd30so8c', d1h_so4c: 'd1h_so4c', d1h_so6c: 'd1h_so6c', d1h_so8c: 'd1h_so8c' };
// Live signals table (ict_trade.signals) tag per module: main -> mode='live',
// impulse -> mode='impulse' (dag.py emits each hourly). The *_half streams read the
// SAME live signals as their parent (the ½TP exit model only changes what happens
// AFTER entry) — live status is then tracked under partial-TP + breakeven rules.
// 'karma' reads BOTH modes and keeps, per symbol, only the side KARMA_MAP picked.
// OPUS reads mode='live' (the MAIN hourly emission) + the per-symbol NY-session gate.
// RANGE reads mode='range' (a dedicated RANGE_DEV scanner, all sessions/symbols).
// d30_4h_so reuses the dch30_4h live signals (only the exit model differs), so its live
// mode is 'dch30_4h' — same as the parent hybrid.
const STRATEGY_LIVE_MODE = { donchianc: 'donchian', dch30_4hc: 'dch30_4h', dch30_4h6c: 'dch30_4h6', d30_4h_soc: 'dch30_4h', d30so6c: 'dch30_4h', d30so8c: 'dch30_4h', d1h_so4c: 'donchian', d1h_so6c: 'donchian', d1h_so8c: 'donchian' };
// Backtest rows don't store the signal timeframe; tag it per strategy so the chart shifts
// signal_time (bar OPEN) to the real fire/fill moment (bar CLOSE) by the CORRECT LTF.
// donchian = 1h; the hybrids (dch30_4h / dch30_4h6 / d30_4h_so) fire on 30m bars + 4h confirm.
// (Bug fix 2026-06-19: was hardcoded '1h' for all, so 30m streams' entry-fill scan started
// 30 min late and missed the fill — the chart looked like "entry never came".)
const STRATEGY_LTF = { donchianc: '1h', dch30_4hc: '30m', dch30_4h6c: '30m', d30_4h_soc: '30m', d30so6c: '30m', d30so8c: '30m', d1h_so4c: '1h', d1h_so6c: '1h', d1h_so8c: '1h' };
const STRATEGY_HTF = { donchian: null, dch30_4h: '4h', dch30_4h6: '4h', d30_4h_so: '4h' };
// No standalone ½TP stream remains (dch30_4hh removed — 2024-negative OOS).
const HALF_STRATEGIES = new Set();
// karma reads BOTH live modes and filters per-symbol via KARMA_MAP.
const KARMA_STRATEGIES = new Set(['karma']);
// opus reads mode='live' and filters per-symbol+session (OPUS_MAP).
const OPUS_STRATEGIES = new Set(['opus']);

// LIGHT band-pass twin: same stream, but keep ONLY signals fired while the
// symbol's 4h ER was in the light-trend band [0.20, 0.35) — where the 2026
// regime-routing audit found our edge actually lives (strong/mid trend is
// break-even-to-negative). Kept only on the two streams it helps most (IMPULSE,
// KARMA). Tags <=10 chars; mirror sync/backfill_light.py LIGHT_TAG.
const LIGHT_ER_LO = 0.20;
const LIGHT_ER_HI = 0.35;
// LIGHT twin auto-registration (impulse_light / karma_light) removed 2026-06-14 with the
// v2_light / kma_light streams (OOS-negative). LIGHT_ER_LO/HI above are retained only for
// applyLightGate below — dead while no _light stream is selectable, kept to avoid dangling refs.
const VALID_STRATEGIES = new Set(Object.keys(STRATEGY_VERSION));

// KARMA selection map — mirror of sync/karma_map.py (generated from the 2026
// selection run karma_selection_2026.csv; regenerate both together).
//   set: which live parent feeds the symbol; half: ½TP+BE exit (true) or full TP.
export const KARMA_MAP = {
  '1000PEPEUSDT': { set: 'main', half: true },
  AAOIUSDT: { set: 'main', half: false },
  ADAUSDT: { set: 'impulse', half: true },
  AMATUSDT: { set: 'main', half: false },
  AMZNUSDT: { set: 'main', half: false },
  ARBUSDT: { set: 'main', half: false },
  AVGOUSDT: { set: 'main', half: false },
  BABAUSDT: { set: 'main', half: true },
  BNBUSDT: { set: 'main', half: false },
  BTCUSDT: { set: 'main', half: false },
  BXUSDT: { set: 'main', half: false },
  COINUSDT: { set: 'main', half: false },
  CRCLUSDT: { set: 'main', half: false },
  CRDOUSDT: { set: 'main', half: false },
  CRWDUSDT: { set: 'main', half: false },
  ETHUSDT: { set: 'impulse', half: false },
  FETUSDT: { set: 'main', half: true },
  HOODUSDT: { set: 'main', half: false },
  HPEUSDT: { set: 'main', half: false },
  INTCUSDT: { set: 'main', half: false },
  IWMUSDT: { set: 'main', half: false },
  METAUSDT: { set: 'main', half: false },
  MSFTUSDT: { set: 'main', half: false },
  MSTRUSDT: { set: 'main', half: false },
  NEARUSDT: { set: 'main', half: false },
  NVDAUSDT: { set: 'main', half: false },
  ONDOUSDT: { set: 'main', half: false },
  ORDIUSDT: { set: 'main', half: false },
  PLTRUSDT: { set: 'main', half: true },
  SOLUSDT: { set: 'main', half: true },
  SUIUSDT: { set: 'main', half: false },
  SUSDT: { set: 'main', half: false },
  TSLAUSDT: { set: 'main', half: false },
  WIFUSDT: { set: 'main', half: false },
  XAGUSDT: { set: 'main', half: false },
  XAUUSDT: { set: 'impulse', half: false },
  // 2026-06-13 crypto re-add (net-negative in 2026 except LINK; universe consistency).
  XRPUSDT: { set: 'main', half: false },
  DOGEUSDT: { set: 'main', half: false },
  LINKUSDT: { set: 'main', half: false },
  AVAXUSDT: { set: 'main', half: true },
};

// ½TP lifecycle applies to this signal? karma / karma_light: per symbol (KARMA_MAP).
// (No standalone ½TP stream remains, so HALF_STRATEGIES is empty.)
export const isHalfFor = (strat, symbol) => {
  if (HALF_STRATEGIES.has(strat)) return true;
  const base = strat.replace(/_light$/, '');
  return base === 'karma' && !!KARMA_MAP[symbol]?.half;
};

// Is this a known strategy module (incl. the _light twins)? Used by route guarding.
export const isValidStrategy = (s) => VALID_STRATEGIES.has(s);

// LIGHT gate (live): keep ONLY signals whose symbol's 4h Efficiency Ratio at the
// last completed 4h bar before the signal is in [LIGHT_ER_LO, LIGHT_ER_HI) — the
// light-trend band where our edge lives. Mirror of sync/regime.light_ok: an
// INCLUSION gate, so a missing/failed ER drops the signal.
const ER_N_4H = 10;
const applyLightGate = async (signals) => {
  const syms = [...new Set(signals.map((s) => s.symbol))];
  const er = {};
  await Promise.all(syms.map(async (sym) => {
    try {
      const b = sym.replace(/[^A-Za-z0-9]/g, '');
      const res = await fetch(`https://fapi.binance.com/fapi/v1/klines?symbol=${b}&interval=4h&limit=150`);
      const d = await res.json();
      if (Array.isArray(d) && d.length) {
        er[sym] = { ct: d.map((k) => Number(k[6])), c: d.map((k) => Number(k[4])) };
      }
    } catch { /* keep on failure */ }
  }));
  const erAt = (s) => {
    const e = er[s.symbol];
    if (!e) return null;
    const tsMs = new Date(s.signal_time).getTime();
    let pos = -1;
    for (let i = 0; i < e.ct.length; i += 1) { if (e.ct[i] <= tsMs) pos = i; else break; }
    if (pos < ER_N_4H) return null;
    const change = Math.abs(e.c[pos] - e.c[pos - ER_N_4H]);
    let vol = 0;
    for (let j = pos - ER_N_4H + 1; j <= pos; j += 1) vol += Math.abs(e.c[j] - e.c[j - 1]);
    return vol > 0 ? change / vol : 0;
  };
  return signals.filter((s) => {
    const v = erAt(s);
    return v !== null && v >= LIGHT_ER_LO && v < LIGHT_ER_HI;   // keep only the light band
  });
};

// LTF bar duration in ms ('1h' -> 3600000). The signal fires at its bar CLOSE,
// so live entry-fill scanning starts at signal_time + this (backtest parity).
const ltfIntervalMs = (tf) => {
  const m = String(tf || '1h').match(/^(\d+)([smhd])$/i);
  const u = { s: 1000, m: 60000, h: 3600000, d: 86400000 };
  return m ? Number(m[1]) * (u[m[2].toLowerCase()] || 3600000) : 3600000;
};

const parseLocalDate = (value) => {
  if (!value || typeof value !== 'string') return null;
  const [y, m, d] = value.split('-').map(Number);
  if (!y || !m || !d) return null;
  const date = new Date(y, m - 1, d);
  return Number.isNaN(date.getTime()) ? null : date;
};

const getBoundaryTimestamp = (value, side) => {
  const date = parseLocalDate(value);
  if (!date) return side === 'start' ? -Infinity : Infinity;
  if (side === 'start') {
    date.setHours(0, 0, 0, 0);
  } else {
    date.setHours(23, 59, 59, 999);
  }
  return date.getTime();
};

export const useTradeContext = () => useContext(TradeContext);

export const TradeProvider = ({ children }) => {
  const [allSignals, setAllSignals] = useState([]);
  const [filteredSignals, setFilteredSignals] = useState([]);
  const [selectedSymbols, setSelectedSymbols] = useState(new Set());
  const [pendingSymbols, setPendingSymbols] = useState(new Set());
  const [isLoaded, setIsLoaded] = useState(false);
  const [activeSignal, setActiveSignal] = useState(null);
  const [showStats, setShowStats] = useState(false);
  const [chartView, setChartView] = useState('tv');
  const [showSummary, setShowSummary] = useState(false);
  const [dateStart, setDateStart] = useState('');
  const [dateEnd, setDateEnd] = useState('');
  const [pendingDateStart, setPendingDateStart] = useState('');
  const [pendingDateEnd, setPendingDateEnd] = useState('');

  // --- View axes: strategy {main|impulse} × mode {live|backtest}. The URL is
  // the source of truth (CommandCenterPage syncs route params -> setView). strategyRef
  // mirrors state so the data-load effect + loadBacktest read it synchronously.
  // (stale localStorage values outside VALID_STRATEGIES fall back to main.)
  const [strategy, setStrategyState] = useState(() => {
    try { const s = localStorage.getItem('pusu.strategy'); return VALID_STRATEGIES.has(s) ? s : 'donchianc'; } catch { return 'donchianc'; }
  });
  const strategyRef = useRef(strategy);
  const [mode, setModeState] = useState(() => {
    // Kept streams are all backtest-only; default to backtest (live mode has no streams now).
    try { const m = localStorage.getItem('pusu.mode'); return (m === 'backtest' || m === 'live') ? m : 'backtest'; } catch { return 'backtest'; }
  });
  const setStrategy = useCallback((s) => {
    strategyRef.current = s;
    setStrategyState(s);
    try { localStorage.setItem('pusu.strategy', s); } catch { /* ignore */ }
  }, []);
  const setMode = useCallback((m) => {
    setModeState(m);
    try { localStorage.setItem('pusu.mode', m); } catch { /* ignore */ }
  }, []);
  const setView = useCallback((s, m) => { setStrategy(s); setMode(m); }, [setStrategy, setMode]);
  // Status filter (all/tp/sl/active/cancelled) — lifted to context so the Topbar renders
  // the chips while Dashboard filters by it. 'active' is live-only.
  const [statusFilter, setStatusFilter] = useState('all');
  // Sidebar visibility — persisted so a hidden sidebar stays hidden across reloads.
  const [sidebarHidden, setSidebarHiddenState] = useState(() => {
    try { return localStorage.getItem('pusu.sidebar') === 'hidden'; } catch { return false; }
  });
  const toggleSidebar = useCallback(() => {
    setSidebarHiddenState((h) => {
      const next = !h;
      try { localStorage.setItem('pusu.sidebar', next ? 'hidden' : 'shown'); } catch { /* ignore */ }
      return next;
    });
  }, []);
  const [liveError, setLiveError] = useState('');
  // Wall-clock of the last successful data load — surfaced in the Topbar so the
  // operator can tell at a glance how fresh the board is.
  const [lastUpdated, setLastUpdated] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [dbStatus, setDbStatus] = useState('idle'); // idle | testing | ok | fail
  const [dbMessage, setDbMessage] = useState('');
  const [liveStatuses, setLiveStatuses] = useState({});
  const [backtestInsights, setBacktestInsights] = useState({
    summary: null,
    symbols: [],
    weekdays: [],
    sessions: []
  });

  const liveStatusesRef = useRef({});
  // Session cache for backtest data — historical rows + analytics are immutable
  // for a given query, so we fetch once and reuse on every mode toggle back to
  // BACKTEST instead of re-hitting Supabase. Multi-slot Map keyed by cacheKey
  // (table|version|...): switching A→B→A no longer refetches A. { rows, insights } per key.
  const backtestCacheRef = useRef(new Map());

  const toNumber = useCallback((value) => {
    const parsed = parseFloat(value);
    return Number.isFinite(parsed) ? parsed : null;
  }, []);

  const normalizeDirection = useCallback((item) => {
    const raw = (item.trade_type || item.direction || '').toString().toUpperCase();
    if (raw === 'BUY' || raw === 'LONG') return 'LONG';
    if (raw === 'SELL' || raw === 'SHORT') return 'SHORT';
    return null;
  }, []);

  const normalizeStatus = useCallback((item) => {
    const raw = (item.status || '').toString().toLowerCase();
    if (raw.includes('cancel')) return 'NOFILL';   // entry never filled -> 0R, no trade taken
    if (raw.includes('tp') || raw.includes('take profit')) return 'TP';
    if (raw.includes('sl') || raw.includes('stop loss')) return 'SL';
    return 'WAITING';
  }, []);

  const cleanEnvValue = useCallback((value) => {
    if (typeof value !== 'string') return value;
    return value.trim().replace(/^["']|["']$/g, '');
  }, []);

  const resolveSchemaAndTable = useCallback((rawTable, defaultSchema = 'ict_trade', defaultTable = 'backtesting_trades') => {
    const cleaned = cleanEnvValue(rawTable);
    if (!cleaned) return { schema: defaultSchema, table: defaultTable };
    const parts = cleaned.split('.');
    if (parts.length >= 2) {
      const schema = parts[0]?.trim() || defaultSchema;
      const table = parts[parts.length - 1]?.trim() || defaultTable;
      return { schema, table };
    }
    return { schema: defaultSchema, table: cleaned };
  }, [cleanEnvValue]);

  const isAllowedBacktestHour = useCallback((signalTime) => {
    if (!signalTime) return false;
    const dt = new Date(signalTime);
    if (Number.isNaN(dt.getTime())) return false;
    return BACKTEST_ALLOWED_HOURS.has(dt.getUTCHours());
  }, []);

  const buildProcessedSignals = useCallback((data) => {
    const raw = Array.isArray(data)
      ? data
      : Array.isArray(data?.ict_signal)
        ? data.ict_signal
        : [];

    return raw
      .map((item, index) => {
        const status = normalizeStatus(item);
        const entry = toNumber(item.entry_price ?? item.entry);
        const tp = toNumber(item.tp_price ?? item.tp);
        const sl = toNumber(item.sl_price ?? item.sl);
        const pnlR = toNumber(item.pnl_r);
        const signalDate = item.signal_time ? new Date(item.signal_time) : new Date(item.created_at);

        if (Number.isNaN(signalDate.getTime())) return null;

        let exitPrice = toNumber(item.exit_price ?? item.current_price ?? item.real_exit_price);
        if (exitPrice === null) {
          if (status === 'TP') exitPrice = tp;
          else if (status === 'SL') exitPrice = sl;
          else exitPrice = entry;
        }

        const signalTs = signalDate.getTime();
        const exitTs = item.exit_time
          ? new Date(item.exit_time).getTime()
          : signalTs + (2 * 60 * 60 * 1000);

        return {
          id: item.id ?? index,
          symbol: item.symbol,
          dir: normalizeDirection(item) || 'SHORT',
          entry,
          tp,
          sl,
          pnlR,
          dateObj: signalDate,
          exitTs,
          status,
          exitPrice,
          strategy: item.strategy ?? null,
          quality: item.quality ?? null,
          confluenceScore: Number.isFinite(Number(item.confluence_score)) ? Number(item.confluence_score) : null,
          ltfTimeframe: item.ltf_timeframe ?? null,
          htfTimeframe: item.htf_timeframe ?? null,
          geometry: (item.context && item.context.geometry) || item.geometry || null,
        };
      })
      .filter(Boolean)
      .sort((a, b) => b.dateObj - a.dateObj);
  }, [normalizeDirection, normalizeStatus, toNumber]);

  const processData = useCallback((data) => {
    const processed = buildProcessedSignals(data);

    if (processed.length === 0) {
      setAllSignals([]);
      setFilteredSignals([]);
      setSelectedSymbols(new Set());
      setPendingSymbols(new Set());
      setIsLoaded(true);
      return;
    }

    setAllSignals(processed);
    const symbols = new Set(processed.map((s) => s.symbol));
    setSelectedSymbols(symbols);
    setPendingSymbols(symbols);
    setIsLoaded(true);
  }, [buildProcessedSignals]);

  const loadLive = useCallback(async () => {
    const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
    const supabaseKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_DEFAULT_KEY;

    if (!supabaseUrl || !supabaseKey) {
      setLiveError('Supabase ayarları eksik.');
      setIsLoaded(true);
      return;
    }

    try {
      setLiveError('');
      const now = new Date();
      const start = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() - 1, 0, 0, 0));
      const end = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1, 0, 0, 0));

      const params = new URLSearchParams({
        select: 'id,symbol,direction,entry,sl,tp,signal_time,created_at,mode,ltf_timeframe,htf_timeframe,strategy,quality,confluence_score,context',
        order: 'signal_time.desc'
      });
      params.append('signal_time', `gte.${start.toISOString()}`);
      params.append('signal_time', `lt.${end.toISOString()}`);
      params.append('symbol', `in.(${BACKTEST_ALLOWED_SYMBOLS.join(',')})`);
      // Module -> its own live mode tag: MAIN='live' (hourly B/C/D/E), IMPULSE='impulse'
      // (hourly v2 set). Excludes pulse (15m), dynamic (radar) and legacy rows.
      // KARMA reads both modes; per symbol only the KARMA_MAP-selected side is kept below.
      // OPUS reads 'live' (MAIN signals) and is filtered to per-symbol NY sessions below.
      const isKarma = KARMA_STRATEGIES.has(strategyRef.current);
      const isOpus = OPUS_STRATEGIES.has(strategyRef.current);
      const isLight = strategyRef.current.endsWith('_light');  // 4h-ER gate: keep light band only
      if (isKarma) {
        params.append('mode', 'in.(live,impulse)');
      } else {
        const liveMode = STRATEGY_LIVE_MODE[strategyRef.current] || 'live';
        params.append('mode', `eq.${liveMode}`);
      }

      const url = `${supabaseUrl}/rest/v1/signals?${params.toString()}`;
      const res = await fetch(url, {
        headers: {
          apikey: supabaseKey,
          Authorization: `Bearer ${supabaseKey}`,
          'Accept-Profile': 'ict_trade'
        }
      });

      if (!res.ok) throw new Error('Live veri alınamadı');

      const rows = await res.json();
      const filteredRows = rows.filter((r) => {
        if (!isAllowedBacktestHour(r.signal_time)) return false;
        if (isKarma) {
          // karma: keep only the per-symbol selected source (unmapped symbols don't trade)
          const sel = KARMA_MAP[r.symbol];
          if (!sel) return false;
          return r.mode === (sel.set === 'impulse' ? 'impulse' : 'live');
        }
        // opus: keep only symbols+sessions in the per-symbol NY-session allowlist
        if (isOpus) return opusAllows(r.symbol, r.signal_time);
        return true;
      });
      const mapped = filteredRows.map((r) => ({
        id: r.id,
        symbol: r.symbol,
        trade_type: r.direction === 'LONG' ? 'BUY' : 'SELL',
        entry_price: r.entry,
        tp_price: r.tp,
        sl_price: r.sl,
        signal_time: r.signal_time,
        // LTF carried from the DB (fallback to the strategy's KNOWN ltf, never the generic 1h) so
        // the live entry-fill scan starts at signal_time + the CORRECT bar length. Dropping this
        // made ltfIntervalMs(undefined) fall back to 1h → every 30m signal's entryTs landed 30 min
        // late → a short that dropped favourably (or a long that ran up) never saw high≥entry /
        // low≤entry → false 'İptal (Süre Doldu)' on the cleanest winners.
        ltf_timeframe: r.ltf_timeframe ?? STRATEGY_LTF[strategyRef.current] ?? '1h',
        status: 'WAITING',
        strategy: r.strategy,
        quality: r.quality,
        confluence_score: r.confluence_score,
        context: r.context,
      }));

      // LIGHT modules: keep ONLY signals fired in the light band [0.20,0.35) (the
      // regime where our edge lives). Mirrors sync/regime.light_ok — an inclusion
      // gate, so a failed/absent ER drops the signal.
      const finalMapped = isLight ? await applyLightGate(mapped) : mapped;

      processData(finalMapped);
      setLastUpdated(new Date());
    } catch (err) {
      setLiveError('Live veri alınamadı.');
      setIsLoaded(true);
      console.error(err);
    }
  }, [processData, isAllowedBacktestHour]);

  const loadBacktest = useCallback(async ({ force = false } = {}) => {
    const supabaseUrl = import.meta.env.BACKTESTING_VITE_SUPABASE_URL;
    const supabaseKey = import.meta.env.BACKTESTING_VITE_SUPABASE_PUBLISHABLE_DEFAULT_KEY;
    const backtestTableRaw = import.meta.env.BACKTESTING_DB_TABLE;
    const { schema: backtestSchema, table: backtestTable } = resolveSchemaAndTable(backtestTableRaw);

    if (!supabaseUrl || !supabaseKey) {
      setLiveError('Backtest Supabase ayarları eksik.');
      setIsLoaded(true);
      return;
    }

    // Cache key = everything that defines the result set. If unchanged and not
    // forced, restore from the in-memory session cache (no network round-trip).
    // Version is keyed off the active strategy module: main -> v1, impulse -> v2.
    const btVersion = STRATEGY_VERSION[strategyRef.current] || 'v1';
    const cacheKey = `${backtestSchema}.${backtestTable}|${btVersion}|2024-01-01|${BACKTEST_ALLOWED_SYMBOLS.join(',')}`;
    const cached = backtestCacheRef.current.get(cacheKey);
    if (!force && cached) {
      setLiveError('');
      processData(cached.rows);
      setBacktestInsights(cached.insights);
      setLastUpdated(new Date());
      return;
    }

    const callRpc = async (fnName) => {
      const rpcUrl = `${supabaseUrl}/rest/v1/rpc/${fnName}`;
      const rpcRes = await fetch(rpcUrl, {
        method: 'POST',
        headers: {
          apikey: supabaseKey,
          Authorization: `Bearer ${supabaseKey}`,
          // RPC is a POST: PostgREST resolves the function schema from Content-Profile,
          // not Accept-Profile. Without it the call hits public.* and 404s (PGRST202).
          'Accept-Profile': backtestSchema,
          'Content-Profile': backtestSchema,
          'Content-Type': 'application/json'
        },
        // p_version selects the backtest stream (v1/v2) so analytics match the table.
        body: JSON.stringify({ p_version: btVersion })
      });

      if (!rpcRes.ok) {
        const rpcErr = await rpcRes.text();
        throw new Error(`RPC ${fnName} failed (${rpcRes.status}) ${rpcErr}`);
      }

      return rpcRes.json();
    };

    const fetchAllBacktestRows = async (url) => {
      const pageSize = 1000;
      let from = 0;
      const all = [];

      while (true) {
        const to = from + pageSize - 1;
        const pageRes = await fetch(url, {
          headers: {
            apikey: supabaseKey,
            Authorization: `Bearer ${supabaseKey}`,
            'Accept-Profile': backtestSchema,
            'Range-Unit': 'items',
            Range: `${from}-${to}`
          }
        });

        if (!pageRes.ok) {
          const errBody = await pageRes.text();
          throw new Error(`Backtest veri alınamadı (${pageRes.status}) ${errBody}`);
        }

        const pageRows = await pageRes.json();
        if (!Array.isArray(pageRows) || pageRows.length === 0) break;
        all.push(...pageRows);
        if (pageRows.length < pageSize) break;
        from += pageSize;
      }

      return all;
    };

    try {
      setLiveError('');

      const params = new URLSearchParams({
        select: 'id,symbol,trade_type,signal_time,real_entry_time,exit_time,entry_price,tp_price,sl_price,status,exit_price,pnl_r,version,created_at,strategy,quality,confluence_score,context',
        order: 'signal_time.desc'
      });
      params.append('version', `eq.${btVersion}`);
      params.append('signal_time', 'gte.2024-01-01T00:00:00Z');   // donchian multi-year history (2024+)
      params.append('symbol', `in.(${BACKTEST_ALLOWED_SYMBOLS.join(',')})`);

      const url = `${supabaseUrl}/rest/v1/${backtestTable}?${params.toString()}`;
      const rows = await fetchAllBacktestRows(url);
      // Backtest rows don't store the signal timeframe; tag it per-strategy so the UI shifts
      // signal_time (bar OPEN) to the real fire moment (bar CLOSE) by the CORRECT LTF
      // (donchian 1h; dch30_4h / dch30_4h6 / d30_4h_so are 30m + 4h confirm).
      const ltfTf = STRATEGY_LTF[strategyRef.current] ?? '1h';
      const htfTf = STRATEGY_HTF[strategyRef.current] ?? null;
      // Keep cancelled (no-fill) rows — shown as 0R 'no-fill' cards in the day drill.
      const filteredRows = rows
        .filter((row) => isAllowedBacktestHour(row.signal_time))
        .map((row) => ({ ...row, ltf_timeframe: row.ltf_timeframe ?? ltfTf,
                                 htf_timeframe: row.htf_timeframe ?? htfTf }));

      processData(filteredRows);

      // Server-side RPC analytics aggregate the static (v1) set.
      const metricCalls = [
        callRpc('backtest_summary_metrics'),
        callRpc('backtest_symbol_metrics'),
        callRpc('backtest_weekday_metrics'),
        callRpc('backtest_session_metrics')
      ];
      const [summaryRes, symbolRes, weekdayRes, sessionRes] = await Promise.allSettled(metricCalls);
      const nextInsights = {
        summary: summaryRes.status === 'fulfilled' ? (Array.isArray(summaryRes.value) ? summaryRes.value[0] || null : null) : null,
        symbols: symbolRes.status === 'fulfilled' ? (Array.isArray(symbolRes.value) ? symbolRes.value : []) : [],
        weekdays: weekdayRes.status === 'fulfilled' ? (Array.isArray(weekdayRes.value) ? weekdayRes.value : []) : [],
        sessions: sessionRes.status === 'fulfilled' ? (Array.isArray(sessionRes.value) ? sessionRes.value : []) : []
      };
      [summaryRes, symbolRes, weekdayRes, sessionRes]
        .filter((result) => result.status === 'rejected')
        .forEach((result) => console.error('Backtest analytics RPC error:', result.reason));

      setBacktestInsights(nextInsights);
      // Cache the raw rows + analytics so subsequent BACKTEST visits this
      // session reuse them instead of re-querying Supabase.
      backtestCacheRef.current.set(cacheKey, { rows: filteredRows, insights: nextInsights });
      if (backtestCacheRef.current.size > 16) {   // bounded LRU-ish: drop the oldest key
        backtestCacheRef.current.delete(backtestCacheRef.current.keys().next().value);
      }
      setLastUpdated(new Date());
    } catch (err) {
      setLiveError(`Backtest verisi alınamadı: ${err.message}`);
      setIsLoaded(true);
      console.error('Backtest fetch error:', err);
    }
  }, [isAllowedBacktestHour, processData, resolveSchemaAndTable]);

  const testDbConnection = useCallback(async () => {
    const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
    const supabaseKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_DEFAULT_KEY;

    if (!supabaseUrl || !supabaseKey) {
      setDbStatus('fail');
      setDbMessage('Supabase ayarları eksik.');
      return;
    }

    try {
      setDbStatus('testing');
      setDbMessage('Bağlanıyor...');
      const url = `${supabaseUrl}/rest/v1/signals?select=id&limit=1`;
      const res = await fetch(url, {
        headers: {
          apikey: supabaseKey,
          Authorization: `Bearer ${supabaseKey}`,
          'Accept-Profile': 'ict_trade'
        }
      });

      if (!res.ok) throw new Error('Bağlantı başarısız');

      setDbStatus('ok');
      setDbMessage('Bağlı');
    } catch (err) {
      setDbStatus('fail');
      setDbMessage('Bağlantı yok');
      console.error(err);
    }
  }, []);

  // Single data-load effect keyed on (strategy, mode) -> live or backtest loader,
  // both funneling into filteredSignals. strategyRef (read by loadBacktest) is already
  // updated synchronously by setStrategy before this re-runs.
  useEffect(() => {
    let intervalId;
    if (!strategy || !mode) return () => {};

    setDateStart(''); setDateEnd(''); setPendingDateStart(''); setPendingDateEnd('');
    setLiveStatuses({});
    liveStatusesRef.current = {};

    // 'demo' is self-contained (precomputed static JSON in DemoView) — it drives neither the
    // backtest nor the live fetch. The chart still opens (ChartModal reads strategy from context
    // + pulls klines straight from Binance), so we keep strategy/mode set but skip all I/O here.
    if (mode === 'demo') return () => {};

    if (mode === 'backtest') {
      // Insights restored-or-fetched inside loadBacktest (cache-aware); don't blank here.
      loadBacktest();
    } else {
      setBacktestInsights({ summary: null, symbols: [], weekdays: [], sessions: [] });
      loadLive();
      intervalId = setInterval(() => {
        const now = new Date();
        const minute = now.getMinutes();
        const second = now.getSeconds();
        const inWindow = (minute % 15 === 0) || (minute % 15 === 1);
        const aligned = second % 10 === 0;
        if (inWindow && aligned) loadLive();
      }, 1000);
    }

    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [strategy, mode, loadBacktest, loadLive]);

  // 'active' filter is live-only — reset it when leaving live.
  useEffect(() => {
    if (mode !== 'live' && statusFilter === 'active') setStatusFilter('all');
  }, [mode, statusFilter]);

  // Force a fresh backtest pull (bypasses the session cache) — e.g. a manual refresh.
  const reloadBacktest = useCallback(() => loadBacktest({ force: true }), [loadBacktest]);

  // Manual refresh for the current view (Topbar button) — live refetch or
  // forced backtest pull, with a spinner flag while in flight.
  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      if (mode === 'backtest') await loadBacktest({ force: true });
      else await loadLive();
    } finally {
      setRefreshing(false);
    }
  }, [mode, loadBacktest, loadLive]);

  const normalizeForBinance = useCallback((sym) => (sym ? sym.replace(/[^A-Za-z0-9]/g, '') : ''), []);

  const computeLiveStatusFromCandles = useCallback((sig, candles) => {
    if (!sig || !sig.entry || !sig.tp || !sig.sl || !sig.dir || !candles?.length) {
      return { status: 'Sinyal Bekliyor', lastPrice: null };
    }

    // The signal FIRES at its bar CLOSE (signal_time is the bar OPEN). Start the
    // entry-fill scan there — exactly like the backtest resolver (close_ts =
    // signal_ts + ltf). Otherwise an intrabar touch DURING the signal bar itself
    // (before the signal even exists) is wrongly read as a fill → SL/TP instead
    // of cancelled. This was the live-vs-backtest mismatch (live SL, backtest Cancelled).
    const entryTs = Math.floor((sig.dateObj.getTime()
      + ltfIntervalMs(sig.ltfTimeframe ?? STRATEGY_LTF[strategyRef.current])) / 1000);
    // Limit must be touched within the strategy's fill window (backtest parity;
    // main/impulse = 180 min).
    const expiryMin = STRATEGY_EXPIRY_MINUTES[strategyRef.current] ?? ENTRY_EXPIRY_MINUTES;
    const fillDeadlineSec = entryTs + expiryMin * 60;
    const lastPrice = candles[candles.length - 1]?.close ?? null;
    let entryHitTime = null;

    for (const c of candles) {
      if (c.time < entryTs) continue;
      // Fill window elapsed without the limit ever being touched → cancel.
      if (c.time > fillDeadlineSec) {
        return { status: 'İptal (Süre Doldu)', lastPrice };
      }
      const entryTouched = sig.dir === 'LONG' ? c.low <= sig.entry : c.high >= sig.entry;
      const tpHit = sig.dir === 'LONG' ? c.high >= sig.tp : c.low <= sig.tp;
      const slHit = sig.dir === 'LONG' ? c.low <= sig.sl : c.high >= sig.sl;

      if (!entryTouched && (tpHit || slHit)) {
        return { status: 'İptal (Entry Gelmeden TP/SL)', lastPrice };
      }

      if (entryTouched) {
        entryHitTime = c.time;
        break;
      }
    }

    if (entryHitTime === null) return { status: 'Sinyal Bekliyor', lastPrice };

    // Directional entry confirmation (mirror of backtest C.ENTRY_CONFIRM_BUF): only OPEN the
    // trade if the breakout confirms its direction — favourable buf*risk before adverse buf*risk
    // within the fill window. A reversal toward the stop (AVAX-short case) -> not opened. Until
    // it confirms, the card stays 'Sinyal Bekliyor'; if it goes adverse first -> 'İptal (Ters Yön)'.
    if (ENTRY_CONFIRM_BUF > 0) {
      const risk = Math.abs(sig.entry - sig.sl);
      if (risk > 0) {
        const favLvl = sig.dir === 'LONG' ? sig.entry + ENTRY_CONFIRM_BUF * risk : sig.entry - ENTRY_CONFIRM_BUF * risk;
        const advLvl = sig.dir === 'LONG' ? sig.entry - ENTRY_CONFIRM_BUF * risk : sig.entry + ENTRY_CONFIRM_BUF * risk;
        let conf = 'none';
        let scannedPastDeadline = false;
        for (const c of candles) {
          if (c.time < entryTs) continue;
          if (c.time > fillDeadlineSec) { scannedPastDeadline = true; break; }
          const adv = sig.dir === 'LONG' ? c.low <= advLvl : c.high >= advLvl;
          const fav = sig.dir === 'LONG' ? c.high >= favLvl : c.low <= favLvl;
          if (adv) { conf = 'adv'; break; }   // adverse first (ties -> adv) -> never open
          if (fav) { conf = 'fav'; break; }
        }
        if (conf === 'adv') return { status: 'İptal (Ters Yön)', lastPrice };
        if (conf === 'none') return { status: scannedPastDeadline ? 'İptal (Ters Yön)' : 'Sinyal Bekliyor', lastPrice };
      }
    }

    // Scale-out (d30_4h_so): after the fill, book 60% at +1R and pull the stop to breakeven; the
    // runner (40%) is CAPPED at +4R and time-boxed to 3 days. Live we catch the three intraday-
    // observable terminals: a -1R stop before +1R, the runner hitting its +4R cap (== the signal's
    // own TP, since RUNNER_CAP 4R == dch30_4h RR=4), or a breakeven close (runner back to entry).
    // The rare 3-day mark-to-market tail is resolved by the nightly sync — until then a still-riding
    // runner stays "+1R Alındı · Runner".
    // Matches the 30m+4h scale-out (d30_4h_so / d30so{N}c) AND the 1h scale-out (d1h_so{N}c), incl.
    // the realistic ·0.5R twins. The ·0.5R twins enter at the +0.5R confirmation level, so +1R / BE are
    // measured from that realistic entry (risk = 1.5×raw); the runner cap sits at the STRUCTURAL
    // +N*raw_risk from the breakout (== signal TP for 4R, higher for 6R/8R). Single source: both the
    // live LIST and the chart read this status.
    if (/^(d30_4h_so|d30so\d+|d1h_so\d+)c?$/.test(strategyRef.current)) {
      const conf = strategyRef.current.endsWith('c');                       // realistic +0.5R entry twin
      const rawRisk = Math.abs(sig.entry - sig.sl);
      const entryEff = conf ? (sig.dir === 'LONG' ? sig.entry + 0.5 * rawRisk : sig.entry - 0.5 * rawRisk) : sig.entry;
      const riskEff = Math.abs(entryEff - sig.sl);                          // 1.5×raw for the ·0.5R twin
      const r1 = sig.dir === 'LONG' ? entryEff + riskEff : entryEff - riskEff;   // +1R first target
      const capM = strategyRef.current.match(/so(\d+)c?$/);                 // d30so6c/d1h_so6c→6, d30so8c→8…
      const capR = capM ? Number(capM[1]) : 4;                              // bare d30_4h_so(c) → 4
      const cap = sig.dir === 'LONG' ? sig.entry + capR * rawRisk : sig.entry - capR * rawRisk;
      let partial = false;
      let stop = sig.sl;
      for (const c of candles) {
        if (c.time < entryHitTime) continue;
        const r1Hit = sig.dir === 'LONG' ? c.high >= r1 : c.low <= r1;
        const capHit = sig.dir === 'LONG' ? c.high >= cap : c.low <= cap;  // runner +NR cap
        const stopHit = sig.dir === 'LONG' ? c.low <= stop : c.high >= stop;
        if (!partial) {
          if (stopHit) return { status: 'SL Oldu', lastPrice };          // -1R before +1R (ties → stop)
          if (r1Hit) { partial = true; stop = entryEff; continue; }       // +1R booked (60%), arm BE at the real entry
        } else {
          if (stopHit) return { status: 'BE Oldu', lastPrice };          // runner back to breakeven (0R)
          if (capHit) return { status: 'TP Oldu', lastPrice };           // runner hit its +NR cap
        }
      }
      return { status: partial ? 'İşlem Aktif (+1R Alındı · Runner)' : 'İşlem Aktif (Entry Geldi)', lastPrice };
    }

    // ½TP modules: after the fill, run the partial-TP + breakeven lifecycle
    // (mirror of backtest _resolve_partial): at half the distance entry→TP close
    // 50% and pull the stop to entry; the rest rides to TP or stops at BE.
    // Same-bar TP+stop → worst case stop first; BE arms from the NEXT bar.
    // karma: the exit model is per SYMBOL (KARMA_MAP), not per module.
    if (isHalfFor(strategyRef.current, sig.symbol)) {
      const halfLevel = sig.entry + (sig.tp - sig.entry) / 2;   // long & short
      let partial = false;
      let stop = sig.sl;
      for (const c of candles) {
        if (c.time < entryHitTime) continue;
        const tpHit = sig.dir === 'LONG' ? c.high >= sig.tp : c.low <= sig.tp;
        const stopHit = sig.dir === 'LONG' ? c.low <= stop : c.high >= stop;
        const halfHit = sig.dir === 'LONG' ? c.high >= halfLevel : c.low <= halfLevel;
        if (!partial) {
          if (stopHit && !tpHit) return { status: 'SL Oldu', lastPrice };
          if (tpHit) return { status: stopHit ? 'SL Oldu' : 'TP Oldu', lastPrice }; // gap through
          if (halfHit) { partial = true; stop = sig.entry; continue; }
        } else {
          if (tpHit && !stopHit) return { status: 'TP Oldu', lastPrice };
          if (stopHit) return { status: 'BE Oldu', lastPrice };
        }
      }
      return { status: partial ? 'İşlem Aktif (Kısmi ½TP Alındı)' : 'İşlem Aktif (Entry Geldi)', lastPrice };
    }

    for (const c of candles) {
      if (c.time < entryHitTime) continue;
      const tpHit = sig.dir === 'LONG' ? c.high >= sig.tp : c.low <= sig.tp;
      const slHit = sig.dir === 'LONG' ? c.low <= sig.sl : c.high >= sig.sl;
      if (tpHit || slHit) {
        return { status: tpHit && slHit ? 'TP/SL Aynı Mum' : (tpHit ? 'TP Oldu' : 'SL Oldu'), lastPrice };
      }
    }

    return { status: 'İşlem Aktif (Entry Geldi)', lastPrice };
  }, []);

  const resolveLiveMeta = useCallback((status) => {
    if (!status) return { terminal: false };
    if (status === 'TP Oldu') return { terminal: true };
    if (status === 'SL Oldu') return { terminal: true };
    if (status === 'BE Oldu') return { terminal: true };   // ½TP breakeven close
    if (status === 'TP/SL Aynı Mum') return { terminal: true };
    if (status.startsWith('İptal')) return { terminal: true };
    return { terminal: false };
  }, []);

  useEffect(() => {
    // Poll live status for the loaded signal set so cards show TP/SL/Aktif/İptal.
    const pollSet = allSignals;
    if (mode !== 'live' || pollSet.length === 0) return () => {};

    let stopped = false;

    // Fetch 1m klines for ONE symbol covering from the earliest signal on that symbol to now.
    const fetchCandlesForSymbol = async (symbol, startMs) => {
      const baseSymbol = normalizeForBinance(symbol);
      // Window = earliest pending signal − 2h .. now. Binance caps at 1500 bars/request and returns
      // the FIRST 1500 from startTime, so a span >1500 bars would TRUNCATE the recent end and drop
      // a signal's [close, close+180m] gate window → wrong İptal/Bekliyor. So COARSEN the interval
      // (1m→5m→15m…) until the FULL span fits ≤1500 bars — same as the chart. This keeps every
      // signal's bars (signal/entry/confirm/runner) in view for ALL live strategies and ALL trade
      // ages (recent trades stay 1m for precise 0.5R confirmation; only >~24h-old ones coarsen).
      // (A hard 24h clamp was wrong: it dropped the bars of >24h trades — e.g. a 3-day scale-out
      // runner — making the gate falsely return 'İptal (Süre Doldu)'.)
      const fetchEndTime = Date.now();
      const fetchStartTime = startMs - (60 * 1000 * 120);
      const LADDER = [['1m', 60000], ['5m', 300000], ['15m', 900000], ['1h', 3600000], ['4h', 14400000]];
      let interval = '1m';
      for (const [iv, ms] of LADDER) { interval = iv; if ((fetchEndTime - fetchStartTime) / ms <= 1450) break; }
      const q = `symbol=${baseSymbol}&interval=${interval}&startTime=${fetchStartTime}&endTime=${fetchEndTime}&limit=1500`;
      let rawData = await (await fetch(`https://fapi.binance.com/fapi/v1/klines?${q}`)).json();
      if (!Array.isArray(rawData)) {
        rawData = await (await fetch(`https://api.binance.com/api/v3/klines?${q}`)).json();
      }
      if (!Array.isArray(rawData) || rawData.length === 0) return [];
      return rawData.map((d) => ({
        time: d[0] / 1000,
        open: parseFloat(d[1]), high: parseFloat(d[2]),
        low: parseFloat(d[3]), close: parseFloat(d[4])
      }));
    };

    const updateStatuses = async () => {
      // Only the still-open signals need a refresh; terminal ones are fixed.
      const pending = pollSet.filter((sig) => !resolveLiveMeta(liveStatusesRef.current[sig.id]?.status).terminal);
      if (pending.length === 0) return;

      // ONE 1m fetch per SYMBOL (many signals share a symbol), all symbols in PARALLEL —
      // instead of a serial fetch per signal. Earliest entry on the symbol sets the window.
      const bySym = new Map();
      for (const sig of pending) {
        const e = sig.dateObj.getTime();
        bySym.set(sig.symbol, Math.min(bySym.get(sig.symbol) ?? e, e));
      }
      const candlesBySym = {};
      await Promise.all([...bySym.entries()].map(async ([sym, startMs]) => {
        try { candlesBySym[sym] = await fetchCandlesForSymbol(sym, startMs); }
        catch { candlesBySym[sym] = []; }
      }));
      if (stopped) return;

      // Compute every status, then commit ONCE (no per-signal setState render storm).
      const updates = {};
      for (const sig of pending) {
        const candles = candlesBySym[sig.symbol];
        if (!candles || candles.length === 0) continue;
        const result = computeLiveStatusFromCandles(sig, candles);
        updates[sig.id] = { status: result.status, lastPrice: result.lastPrice };
      }
      if (Object.keys(updates).length === 0) return;
      setLiveStatuses((prev) => {
        const next = { ...prev, ...updates };
        liveStatusesRef.current = next;
        return next;
      });
    };

    updateStatuses();
    const intervalId = setInterval(updateStatuses, 30000);

    return () => {
      stopped = true;
      clearInterval(intervalId);
    };
  }, [mode, allSignals, normalizeForBinance, resolveLiveMeta, computeLiveStatusFromCandles]);

  const isInRange = useCallback((sig) => {
    if (mode === 'live') return true;
    if (!dateStart && !dateEnd) return true;

    const ts = sig.dateObj.getTime();
    const startTs = getBoundaryTimestamp(dateStart, 'start');
    const endTs = getBoundaryTimestamp(dateEnd, 'end');
    return ts >= startTs && ts <= endTs;
  }, [mode, dateStart, dateEnd]);

  useEffect(() => {
    if (allSignals.length === 0) {
      setFilteredSignals([]);
      return;
    }

    setFilteredSignals(allSignals.filter((s) => selectedSymbols.has(s.symbol) && isInRange(s)));
  }, [selectedSymbols, allSignals, isInRange]);

  const toggleSymbol = useCallback((symbol) => {
    setPendingSymbols((prev) => {
      const next = new Set(prev);
      if (next.has(symbol)) next.delete(symbol);
      else next.add(symbol);
      return next;
    });
  }, []);

  const applySymbols = useCallback(() => {
    setSelectedSymbols(new Set(pendingSymbols));
  }, [pendingSymbols]);

  // One-click apply: stage AND commit a symbol set in one go (used by the
  // market / best-worst quick-selects, which shouldn't need a separate Uygula).
  const applySymbolSet = useCallback((syms) => {
    const next = new Set(syms);
    setPendingSymbols(next);
    setSelectedSymbols(next);
  }, []);

  // Per-symbol performance over ALL loaded signals (not the current filter) so
  // the best/worst quick-selects rank the full universe. totalR/wins are only
  // meaningful in backtest (live rows carry no resolved pnlR yet).
  const symbolPerf = useMemo(() => {
    const m = {};
    for (const s of allSignals) {
      const e = m[s.symbol] || (m[s.symbol] = { n: 0, closed: 0, wins: 0, totalR: 0 });
      e.n += 1;
      if (s.status === 'TP' || s.status === 'SL') {
        e.closed += 1;
        if (s.status === 'TP') e.wins += 1;
        if (Number.isFinite(s.pnlR)) e.totalR += s.pnlR;
      }
    }
    return m;
  }, [allSignals]);

  const clearPendingSymbols = useCallback(() => {
    setPendingSymbols(new Set());
  }, []);

  const selectAllPendingSymbols = useCallback(() => {
    setPendingSymbols(new Set(allSignals.map((s) => s.symbol)));
  }, [allSignals]);

  const applyDates = useCallback(() => {
    setDateStart(pendingDateStart);
    setDateEnd(pendingDateEnd);
  }, [pendingDateStart, pendingDateEnd]);

  const contextValue = useMemo(() => ({
    allSignals,
    filteredSignals,
    selectedSymbols,
    pendingSymbols,
    isLoaded,
    processData,
    activeSignal,
    setActiveSignal,
    showStats,
    setShowStats,
    toggleSymbol,
    applySymbols,
    applySymbolSet,
    symbolPerf,
    clearPendingSymbols,
    selectAllPendingSymbols,
    chartView,
    setChartView,
    showSummary,
    setShowSummary,
    dateStart,
    setDateStart,
    dateEnd,
    setDateEnd,
    pendingDateStart,
    setPendingDateStart,
    pendingDateEnd,
    setPendingDateEnd,
    applyDates,
    strategy,
    setStrategy,
    mode,
    setMode,
    setView,
    statusFilter,
    setStatusFilter,
    sidebarHidden,
    toggleSidebar,
    liveError,
    liveStatuses,
    backtestInsights,
    reloadBacktest,
    refresh,
    refreshing,
    lastUpdated,
    dbStatus,
    dbMessage,
    testDbConnection
  }), [
    allSignals,
    filteredSignals,
    selectedSymbols,
    pendingSymbols,
    isLoaded,
    processData,
    activeSignal,
    showStats,
    toggleSymbol,
    applySymbols,
    applySymbolSet,
    symbolPerf,
    clearPendingSymbols,
    selectAllPendingSymbols,
    chartView,
    showSummary,
    dateStart,
    dateEnd,
    pendingDateStart,
    pendingDateEnd,
    applyDates,
    strategy,
    setStrategy,
    mode,
    setMode,
    setView,
    statusFilter,
    setStatusFilter,
    sidebarHidden,
    toggleSidebar,
    liveError,
    liveStatuses,
    backtestInsights,
    reloadBacktest,
    refresh,
    refreshing,
    lastUpdated,
    dbStatus,
    dbMessage,
    testDbConnection
  ]);

  return (
    <TradeContext.Provider value={contextValue}>
      {children}
    </TradeContext.Provider>
  );
};
