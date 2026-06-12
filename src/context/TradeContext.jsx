import { createContext, useState, useEffect, useContext, useRef, useCallback, useMemo } from 'react';

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
const BACKTEST_ALLOWED_SYMBOLS = [
  'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT',
  '1000PEPEUSDT', 'WIFUSDT', 'SUIUSDT',
  'NEARUSDT', 'FETUSDT', 'ADAUSDT', 'SUSDT',
  'ARBUSDT', 'ORDIUSDT', 'ONDOUSDT',
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
const STRATEGY_EXPIRY_MINUTES = { main: 180, impulse: 180, main_half: 180, impulse_half: 180, karma: 180 };

// Strategy module -> backtest version tag. 'main' = original B/C/D/E set (v1);
// 'impulse' = refined v2 set (drop E + D disabled on ADA/XAU/ETH — see
// sync/backfill_v2_year.py). 'main_half'/'impulse_half' = the SAME main(v1)/impulse(v2)
// signals scored under the partial-TP + breakeven EXIT model (scale out half at half
// the distance to TP1, pull the stop to entry) — backtest-only streams tagged v3/v4
// (sync/backfill_v3_year.py / backfill_v4_year.py write them with PARTIAL_TP_ENABLED).
// 'karma' = per-symbol best cell of {main,impulse} x {tam,½TP} (sync/karma_map.py).
const STRATEGY_VERSION = { main: 'v1', impulse: 'v2', main_half: 'v3', impulse_half: 'v4', karma: 'karma' };
// Live signals table (ict_trade.signals) tag per module: main -> mode='live',
// impulse -> mode='impulse' (dag.py emits each hourly). The *_half streams read the
// SAME live signals as their parent (the ½TP exit model only changes what happens
// AFTER entry) — live status is then tracked under partial-TP + breakeven rules.
// 'karma' reads BOTH modes and keeps, per symbol, only the side KARMA_MAP picked.
const STRATEGY_LIVE_MODE = { main: 'live', impulse: 'impulse', main_half: 'live', impulse_half: 'impulse' };
// ½TP modules: scale out 50% at half the distance entry→TP, stop -> entry (BE).
const HALF_STRATEGIES = new Set(['main_half', 'impulse_half']);
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
};

// ½TP lifecycle applies to this signal? *_half modules: always. karma: per symbol.
export const isHalfFor = (strat, symbol) =>
  HALF_STRATEGIES.has(strat) || (strat === 'karma' && !!KARMA_MAP[symbol]?.half);

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
    try { const s = localStorage.getItem('pusu.strategy'); return VALID_STRATEGIES.has(s) ? s : 'main'; } catch { return 'main'; }
  });
  const strategyRef = useRef(strategy);
  const [mode, setModeState] = useState(() => {
    try { const m = localStorage.getItem('pusu.mode'); return (m === 'backtest' || m === 'live') ? m : 'live'; } catch { return 'live'; }
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
  // BACKTEST instead of re-hitting Supabase. { key, rows, insights }.
  const backtestCacheRef = useRef(null);

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
      const isKarma = strategyRef.current === 'karma';
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
        if (!isKarma) return true;
        // karma: keep only the per-symbol selected source (unmapped symbols don't trade)
        const sel = KARMA_MAP[r.symbol];
        if (!sel) return false;
        return r.mode === (sel.set === 'impulse' ? 'impulse' : 'live');
      });
      const mapped = filteredRows.map((r) => ({
        id: r.id,
        symbol: r.symbol,
        trade_type: r.direction === 'LONG' ? 'BUY' : 'SELL',
        entry_price: r.entry,
        tp_price: r.tp,
        sl_price: r.sl,
        signal_time: r.signal_time,
        status: 'WAITING',
        strategy: r.strategy,
        quality: r.quality,
        confluence_score: r.confluence_score,
        context: r.context,
      }));

      processData(mapped);
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
    const cacheKey = `${backtestSchema}.${backtestTable}|${btVersion}|2025-01-01|${BACKTEST_ALLOWED_SYMBOLS.join(',')}`;
    const cached = backtestCacheRef.current;
    if (!force && cached && cached.key === cacheKey) {
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
      params.append('signal_time', 'gte.2025-01-01T00:00:00Z');
      params.append('symbol', `in.(${BACKTEST_ALLOWED_SYMBOLS.join(',')})`);

      const url = `${supabaseUrl}/rest/v1/${backtestTable}?${params.toString()}`;
      const rows = await fetchAllBacktestRows(url);
      // Backtest rows don't store the signal timeframe; tag it from the pipeline so
      // the UI can shift signal_time (bar OPEN) to the real fire moment (bar CLOSE)
      // by the correct LTF (main = 1h).
      const ltfTf = '1h';
      // Keep cancelled (no-fill) rows — shown as 0R 'no-fill' cards in the day drill.
      const filteredRows = rows
        .filter((row) => isAllowedBacktestHour(row.signal_time))
        .map((row) => ({ ...row, ltf_timeframe: row.ltf_timeframe ?? ltfTf }));

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
      backtestCacheRef.current = { key: cacheKey, rows: filteredRows, insights: nextInsights };
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
    const entryTs = Math.floor((sig.dateObj.getTime() + ltfIntervalMs(sig.ltfTimeframe)) / 1000);
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

    const fetchCandles = async (sig) => {
      const baseSymbol = normalizeForBinance(sig.symbol);
      const entryTime = sig.dateObj.getTime();
      const fetchStartTime = entryTime - (60 * 1000 * 120);
      const fetchEndTime = Date.now();

      const urlFutures = `https://fapi.binance.com/fapi/v1/klines?symbol=${baseSymbol}&interval=1m&startTime=${fetchStartTime}&endTime=${fetchEndTime}&limit=1500`;
      const res = await fetch(urlFutures);
      let rawData = await res.json();

      if (!Array.isArray(rawData)) {
        const urlSpot = `https://api.binance.com/api/v3/klines?symbol=${baseSymbol}&interval=1m&startTime=${fetchStartTime}&endTime=${fetchEndTime}&limit=1500`;
        const resSpot = await fetch(urlSpot);
        rawData = await resSpot.json();
      }

      if (!Array.isArray(rawData) || rawData.length === 0) return [];

      return rawData.map((d) => ({
        time: d[0] / 1000,
        open: parseFloat(d[1]),
        high: parseFloat(d[2]),
        low: parseFloat(d[3]),
        close: parseFloat(d[4])
      }));
    };

    const updateStatuses = async () => {
      for (const sig of pollSet) {
        const existing = liveStatusesRef.current[sig.id];
        if (resolveLiveMeta(existing?.status).terminal) continue;

        try {
          const candles = await fetchCandles(sig);
          const result = computeLiveStatusFromCandles(sig, candles);
          if (stopped) return;

          setLiveStatuses((prev) => {
            const next = { ...prev, [sig.id]: { status: result.status, lastPrice: result.lastPrice } };
            liveStatusesRef.current = next;
            return next;
          });
        } catch {
          // no-op
        }
      }
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
