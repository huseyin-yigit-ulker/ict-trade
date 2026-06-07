import { createContext, useState, useEffect, useContext, useRef, useCallback, useMemo } from 'react';

const TradeContext = createContext();

//const BACKTEST_ALLOWED_HOURS = new Set([5, 7, 8, 9, 12, 13, 14,15, 16, 20, 21]);
const BACKTEST_ALLOWED_HOURS = new Set([1,2,3,4,5, 6,7, 8, 9, 10,11,12, 13, 14, 15, 16, 17,18,19, 20, 21,22,23,24]);
// Production set — XRP, TON, 1000SHIB, LINK, OP excluded after negative
// 2025+2026 backtest performance. Old rows for these symbols stay in the
// database but the dashboard hides them.
const BACKTEST_ALLOWED_SYMBOLS = [
  'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'DOGEUSDT',
  '1000PEPEUSDT', 'WIFUSDT', 'SUIUSDT',
  'NEARUSDT', 'FETUSDT', 'ADAUSDT', 'SUSDT',
  'ARBUSDT', 'ORDIUSDT', 'ONDOUSDT',
  'XAUUSDT', 'XAGUSDT',
  // Stock-backed perps (underlying equities)
  'TSLAUSDT', 'NVDAUSDT', 'METAUSDT', 'GOOGLUSDT',
  'AMZNUSDT', 'COINUSDT', 'PLTRUSDT', 'MSTRUSDT'
];

// Entry-fill timeout — mirrors the backtest engine (ict/config.py EXPIRY_MINUTES = 180):
// a signal's limit must be touched within 3h of the signal, else it's cancelled.
const ENTRY_EXPIRY_MINUTES = 180;

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

  // --- View axes: strategy {default|radar} × mode {live|backtest}. The URL is the
  // source of truth (CommandCenterPage syncs route params -> setView). strategyRef
  // mirrors state so the data-load effect + loadBacktest read it synchronously.
  const [strategy, setStrategyState] = useState(() => {
    try { const s = localStorage.getItem('pusu.strategy'); return (s === 'radar' || s === 'main') ? s : 'main'; } catch { return 'main'; }
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
      const filteredRows = rows.filter((r) => isAllowedBacktestHour(r.signal_time));
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
    } catch (err) {
      setLiveError('Live veri alınamadı.');
      setIsLoaded(true);
      console.error(err);
    }
  }, [processData, isAllowedBacktestHour]);

  // Volume Radar: dynamic (mode='dynamic') volume-anomaly picks — symbols OUTSIDE
  // the static 17, so NO allow-list filter. Kept in its own state, separate from
  // the main live/backtest set.
  // Volume Radar LIVE (strategy='radar', mode='live'): mode='dynamic' picks, symbols
  // OUTSIDE the 17, no allow-list. Funnels into the SAME filteredSignals via processData.
  const loadRadarLive = useCallback(async () => {
    const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
    const supabaseKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_DEFAULT_KEY;
    if (!supabaseUrl || !supabaseKey) { setLiveError('Supabase ayarları eksik.'); setIsLoaded(true); return; }
    try {
      setLiveError('');
      const now = new Date();
      const start = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() - 7, 0, 0, 0));
      const params = new URLSearchParams({
        select: 'id,symbol,direction,entry,sl,tp,signal_time,created_at,mode,ltf_timeframe,htf_timeframe,strategy,quality,confluence_score,context',
        order: 'signal_time.desc'
      });
      params.append('mode', 'eq.dynamic');
      params.append('signal_time', `gte.${start.toISOString()}`);
      const url = `${supabaseUrl}/rest/v1/signals?${params.toString()}`;
      const res = await fetch(url, {
        headers: { apikey: supabaseKey, Authorization: `Bearer ${supabaseKey}`, 'Accept-Profile': 'ict_trade' }
      });
      if (!res.ok) throw new Error('Dinamik veri alınamadı');
      const rows = await res.json();
      const mapped = rows.map((r) => ({
        id: r.id, symbol: r.symbol,
        trade_type: r.direction === 'LONG' ? 'BUY' : 'SELL',
        entry_price: r.entry, tp_price: r.tp, sl_price: r.sl,
        signal_time: r.signal_time, status: 'WAITING',
        strategy: r.strategy, quality: r.quality, confluence_score: r.confluence_score,
        context: r.context,
      }));
      processData(mapped);
    } catch (err) {
      setLiveError('Dinamik veri alınamadı.');
      setIsLoaded(true);
      console.error(err);
    }
  }, [processData]);

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
    const source = strategyRef.current;                       // 'default' (17, v1) | 'radar' (v1-dyn)
    const btVersion = source === 'radar' ? 'v1-dyn' : 'v1';
    const cacheKey = `${backtestSchema}.${backtestTable}|${btVersion}|2025-01-01|${source === 'radar' ? 'ALL' : BACKTEST_ALLOWED_SYMBOLS.join(',')}`;
    const cached = backtestCacheRef.current;
    if (!force && cached && cached.key === cacheKey) {
      setLiveError('');
      processData(cached.rows);
      setBacktestInsights(cached.insights);
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
        body: '{}'
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
      if (source !== 'radar') params.append('symbol', `in.(${BACKTEST_ALLOWED_SYMBOLS.join(',')})`);

      const url = `${supabaseUrl}/rest/v1/${backtestTable}?${params.toString()}`;
      const rows = await fetchAllBacktestRows(url);
      // Keep cancelled (no-fill) rows — shown as 0R 'no-fill' cards in the day drill.
      const filteredRows = rows.filter((row) => isAllowedBacktestHour(row.signal_time));

      processData(filteredRows);

      // Server-side RPC analytics aggregate the static-17 (v1) set only; skip for radar.
      let nextInsights = { summary: null, symbols: [], weekdays: [], sessions: [] };
      if (source !== 'radar') {
        const metricCalls = [
          callRpc('backtest_summary_metrics'),
          callRpc('backtest_symbol_metrics'),
          callRpc('backtest_weekday_metrics'),
          callRpc('backtest_session_metrics')
        ];
        const [summaryRes, symbolRes, weekdayRes, sessionRes] = await Promise.allSettled(metricCalls);
        nextInsights = {
          summary: summaryRes.status === 'fulfilled' ? (Array.isArray(summaryRes.value) ? summaryRes.value[0] || null : null) : null,
          symbols: symbolRes.status === 'fulfilled' ? (Array.isArray(symbolRes.value) ? symbolRes.value : []) : [],
          weekdays: weekdayRes.status === 'fulfilled' ? (Array.isArray(weekdayRes.value) ? weekdayRes.value : []) : [],
          sessions: sessionRes.status === 'fulfilled' ? (Array.isArray(sessionRes.value) ? sessionRes.value : []) : []
        };
        [summaryRes, symbolRes, weekdayRes, sessionRes]
          .filter((result) => result.status === 'rejected')
          .forEach((result) => console.error('Backtest analytics RPC error:', result.reason));
      }

      setBacktestInsights(nextInsights);
      // Cache the raw rows + analytics so subsequent BACKTEST visits this
      // session reuse them instead of re-querying Supabase.
      backtestCacheRef.current = { key: cacheKey, rows: filteredRows, insights: nextInsights };
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

  // Single data-load effect keyed on (strategy, mode) -> one of the 4 loaders,
  // all funneling into filteredSignals. strategyRef (read by loadBacktest) is already
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
      const loadLiveForStrategy = strategy === 'radar' ? loadRadarLive : loadLive;
      loadLiveForStrategy();
      loadLiveForStrategy();
      intervalId = setInterval(() => {
        const now = new Date();
        const minute = now.getMinutes();
        const second = now.getSeconds();
        const inWindow = (minute % 15 === 0) || (minute % 15 === 1);
        const aligned = second % 10 === 0;
        if (inWindow && aligned) loadLiveForStrategy();
      }, 1000);
    }

    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [strategy, mode, loadBacktest, loadLive, loadRadarLive]);

  // 'active' filter is live-only — reset it when leaving live.
  useEffect(() => {
    if (mode !== 'live' && statusFilter === 'active') setStatusFilter('all');
  }, [mode, statusFilter]);

  // Force a fresh backtest pull (bypasses the session cache) — e.g. a manual refresh.
  const reloadBacktest = useCallback(() => loadBacktest({ force: true }), [loadBacktest]);

  const normalizeForBinance = useCallback((sym) => (sym ? sym.replace(/[^A-Za-z0-9]/g, '') : ''), []);

  const computeLiveStatusFromCandles = useCallback((sig, candles) => {
    if (!sig || !sig.entry || !sig.tp || !sig.sl || !sig.dir || !candles?.length) {
      return { status: 'Sinyal Bekliyor', lastPrice: null };
    }

    const entryTs = Math.floor(sig.dateObj.getTime() / 1000);
    // Limit must be touched within ENTRY_EXPIRY_MINUTES of the signal (backtest parity).
    const fillDeadlineSec = entryTs + ENTRY_EXPIRY_MINUTES * 60;
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
    if (status === 'TP/SL Aynı Mum') return { terminal: true };
    if (status.startsWith('İptal')) return { terminal: true };
    return { terminal: false };
  }, []);

  useEffect(() => {
    // Poll live status for the static set AND the Volume Radar (dynamic) picks,
    // so Radar cards show the same TP/SL/Aktif/İptal status as default cards.
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
