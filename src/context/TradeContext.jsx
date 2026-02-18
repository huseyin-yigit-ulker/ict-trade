import { createContext, useState, useEffect, useContext, useRef } from 'react';

const TradeContext = createContext();
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
  const [mode, setMode] = useState(null); // backtest | live
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

  const toNumber = (value) => {
    const parsed = parseFloat(value);
    return Number.isFinite(parsed) ? parsed : null;
  };

  const normalizeDirection = (item) => {
    const raw = (item.trade_type || item.direction || '').toString().toUpperCase();
    if (raw === 'BUY' || raw === 'LONG') return 'LONG';
    if (raw === 'SELL' || raw === 'SHORT') return 'SHORT';
    return null;
  };

  const normalizeStatus = (item) => {
    const raw = (item.status || '').toString().toLowerCase();
    if (raw.includes('tp') || raw.includes('take profit')) return 'TP';
    if (raw.includes('sl') || raw.includes('stop loss')) return 'SL';
    return 'WAITING';
  };

  const cleanEnvValue = (value) => {
    if (typeof value !== 'string') return value;
    return value.trim().replace(/^["']|["']$/g, '');
  };

  const resolveSchemaAndTable = (rawTable, defaultSchema = 'ict_trade', defaultTable = 'backtesting_trades') => {
    const cleaned = cleanEnvValue(rawTable);
    if (!cleaned) return { schema: defaultSchema, table: defaultTable };
    const parts = cleaned.split('.');
    if (parts.length >= 2) {
      const schema = parts[0]?.trim() || defaultSchema;
      const table = parts[parts.length - 1]?.trim() || defaultTable;
      return { schema, table };
    }
    return { schema: defaultSchema, table: cleaned };
  };

  const processData = (data) => {
    const raw = Array.isArray(data)
      ? data
      : Array.isArray(data?.ict_signal)
        ? data.ict_signal
        : [];

    if (raw.length === 0) {
      setAllSignals([]);
      setFilteredSignals([]);
      setSelectedSymbols(new Set());
      setIsLoaded(true);
      return;
    }

    const processed = raw.map((item, index) => {
      const status = normalizeStatus(item);
      const entry = toNumber(item.entry_price ?? item.entry);
      const tp = toNumber(item.tp_price ?? item.tp);
      const sl = toNumber(item.sl_price ?? item.sl);
      const pnlR = toNumber(item.pnl_r);
      const signalDate = item.signal_time ? new Date(item.signal_time) : new Date(item.created_at);
      const signalTime = signalDate.getTime();

      let exitPrice = toNumber(item.exit_price ?? item.current_price ?? item.real_exit_price);
      if (exitPrice === null) {
        if (status === 'TP') exitPrice = tp;
        else if (status === 'SL') exitPrice = sl;
        else exitPrice = entry;
      }

      const exitTime = item.exit_time 
        ? new Date(item.exit_time).getTime() 
        : signalTime + (2 * 60 * 60 * 1000);

      return {
        id: item.id ?? index,
        symbol: item.symbol,
        dir: normalizeDirection(item) || 'SHORT',
        entry,
        tp,
        sl,
        pnlR,
        dateObj: signalDate,
        exitTs: exitTime,
        status,
        exitPrice
      };
    }).sort((a, b) => b.dateObj - a.dateObj);

    setAllSignals(processed);
    
    // Varsayılan olarak tüm sembolleri seç
    const symbols = new Set(processed.map(s => s.symbol));
    setSelectedSymbols(symbols);
    setPendingSymbols(symbols);
    setIsLoaded(true);
  };

  const loadLive = async () => {
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
      const start = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()-1, 0, 0, 0));
      const end = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1, 0, 0, 0));
      const params = new URLSearchParams({
        select: '*',
        order: 'signal_time.desc'
      });
      params.append('signal_time', `gte.${start.toISOString()}`);
      params.append('signal_time', `lt.${end.toISOString()}`);

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

      const mapped = rows.map((r) => ({
        symbol: r.symbol,
        trade_type: r.direction === 'LONG' ? 'BUY' : 'SELL',
        entry_price: r.entry,
        tp_price: r.tp,
        sl_price: r.sl,
        signal_time: r.signal_time,
        status: 'WAITING'
      }));

      processData(mapped);
    } catch (err) {
      setLiveError('Live veri alınamadı.');
      setIsLoaded(true);
      console.error(err);
    }
  };

  const loadBacktest = async () => {
    const supabaseUrl = import.meta.env.BACKTESTING_VITE_SUPABASE_URL;
    const supabaseKey = import.meta.env.BACKTESTING_VITE_SUPABASE_PUBLISHABLE_DEFAULT_KEY;
    const backtestTableRaw = import.meta.env.BACKTESTING_DB_TABLE;
    const { schema: backtestSchema, table: backtestTable } = resolveSchemaAndTable(backtestTableRaw);
    const dbConnectionString = import.meta.env.BACKTESTING_DB_CONNECTION_STRING;
    if (!supabaseUrl || !supabaseKey) {
      const hasConnStr = Boolean(dbConnectionString);
      setLiveError(hasConnStr
        ? 'Backtest için URL/KEY eksik. BACKTESTING_DB_CONNECTION_STRING frontend tarafında kullanılamaz.'
        : 'Backtest Supabase ayarları eksik.'
      );
      setIsLoaded(true);
      return;
    }

    try {
      setLiveError('');
      const callRpc = async (fnName) => {
        const rpcUrl = `${supabaseUrl}/rest/v1/rpc/${fnName}`;
        const rpcRes = await fetch(rpcUrl, {
          method: 'POST',
          headers: {
            apikey: supabaseKey,
            Authorization: `Bearer ${supabaseKey}`,
            'Accept-Profile': backtestSchema,
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

      const params = new URLSearchParams({
        select: 'id,symbol,trade_type,signal_time,real_entry_time,exit_time,entry_price,tp_price,sl_price,status,exit_price,pnl_r,created_at',
        order: 'signal_time.desc'
      });
      const url = `${supabaseUrl}/rest/v1/${backtestTable}?${params.toString()}`;
      const res = await fetch(url, {
        headers: {
          apikey: supabaseKey,
          Authorization: `Bearer ${supabaseKey}`,
          'Accept-Profile': backtestSchema
        }
      });
      if (!res.ok) {
        const errBody = await res.text();
        throw new Error(`Backtest veri alınamadı (${res.status}) ${errBody}`);
      }
      const rows = await res.json();
      const filteredRows = rows.filter((row) => {
        const rawStatus = (row?.status || '').toString().toLowerCase();
        return rawStatus !== 'cancelled' && rawStatus !== 'canceled';
      });
      processData(filteredRows);

      try {
        const [summaryRows, symbolRows, weekdayRows, sessionRows] = await Promise.all([
          callRpc('backtest_summary_metrics'),
          callRpc('backtest_symbol_metrics'),
          callRpc('backtest_weekday_metrics'),
          callRpc('backtest_session_metrics')
        ]);

        setBacktestInsights({
          summary: Array.isArray(summaryRows) ? (summaryRows[0] || null) : null,
          symbols: Array.isArray(symbolRows) ? symbolRows : [],
          weekdays: Array.isArray(weekdayRows) ? weekdayRows : [],
          sessions: Array.isArray(sessionRows) ? sessionRows : []
        });
      } catch (rpcErr) {
        setBacktestInsights({
          summary: null,
          symbols: [],
          weekdays: [],
          sessions: []
        });
        console.error('Backtest analytics RPC error:', rpcErr);
      }
    } catch (err) {
      // Hatayı direkt ekrana basarak ne olduğunu anlayalım
      setLiveError(`Backtest verisi alınamadı: ${err.message}`);
      setIsLoaded(true);
      console.error("Fetch Hatası Detayı:", err);
    }
  };

  const testDbConnection = async () => {
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
  };

  useEffect(() => {
    let intervalId;
    if (!mode) return () => {};
    setLiveStatuses({});
    liveStatusesRef.current = {};
    setBacktestInsights({
      summary: null,
      symbols: [],
      weekdays: [],
      sessions: []
    });
    if (mode === 'backtest') {
      loadBacktest();
    } else {
      loadLive();
      intervalId = setInterval(() => {
        const now = new Date();
        const minute = now.getMinutes();
        const second = now.getSeconds();
        const inWindow = (minute % 15 === 0) || (minute % 15 === 1);
        const aligned = second % 10 === 0;
        if (inWindow && aligned) {
          loadLive();
        }
      }, 1000);
    }

    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [mode]);

  const normalizeForBinance = (sym) => sym ? sym.replace(/[^A-Za-z0-9]/g, '') : '';

  const computeLiveStatusFromCandles = (sig, candles) => {
    if (!sig || !sig.entry || !sig.tp || !sig.sl || !sig.dir || !candles?.length) {
      return { status: 'Sinyal Bekliyor', lastPrice: null };
    }
    const entryTs = Math.floor(sig.dateObj.getTime() / 1000);
    const lastPrice = candles[candles.length - 1]?.close ?? null;
    let entryHitTime = null;
    for (const c of candles) {
      if (c.time < entryTs) continue;
      const entryTouched = sig.dir === 'LONG' ? c.low <= sig.entry : c.high >= sig.entry;
      const tpHit = sig.dir === 'LONG' ? c.high >= sig.tp : c.low <= sig.tp;
      const slHit = sig.dir === 'LONG' ? c.low <= sig.sl : c.high >= sig.sl;
      if (!entryTouched && (tpHit || slHit)) return { status: 'İptal (Entry Gelmeden TP/SL)', lastPrice };
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
  };

  const resolveLiveMeta = (status) => {
    if (!status) return { terminal: false };
    if (status === 'TP Oldu') return { terminal: true };
    if (status === 'SL Oldu') return { terminal: true };
    if (status === 'TP/SL Aynı Mum') return { terminal: true };
    if (status.startsWith('İptal')) return { terminal: true };
    return { terminal: false };
  };

  useEffect(() => {
    if (mode !== 'live' || allSignals.length === 0) return () => {};
    let stopped = false;

    const fetchCandles = async (sig) => {
      const baseSymbol = normalizeForBinance(sig.symbol);
      const entryTime = sig.dateObj.getTime();
      const now = Date.now();
      const fetchStartTime = entryTime - (60 * 1000 * 120);
      const fetchEndTime = now;
      const urlFutures = `https://fapi.binance.com/fapi/v1/klines?symbol=${baseSymbol}&interval=1m&startTime=${fetchStartTime}&endTime=${fetchEndTime}&limit=1500`;
      const res = await fetch(urlFutures);
      let rawData = await res.json();

      if (!Array.isArray(rawData)) {
        const urlSpot = `https://api.binance.com/api/v3/klines?symbol=${baseSymbol}&interval=1m&startTime=${fetchStartTime}&endTime=${fetchEndTime}&limit=1500`;
        const resSpot = await fetch(urlSpot);
        rawData = await resSpot.json();
      }

      if (!Array.isArray(rawData) || rawData.length === 0) return [];
      return rawData.map(d => ({
        time: d[0] / 1000,
        open: parseFloat(d[1]),
        high: parseFloat(d[2]),
        low: parseFloat(d[3]),
        close: parseFloat(d[4])
      }));
    };

    const updateStatuses = async () => {
      for (const sig of allSignals) {
        const existing = liveStatusesRef.current[sig.id];
        if (resolveLiveMeta(existing?.status).terminal) continue;
        try {
          const candles = await fetchCandles(sig);
          const result = computeLiveStatusFromCandles(sig, candles);
          if (stopped) return;
          setLiveStatuses(prev => {
            const next = { ...prev, [sig.id]: { status: result.status, lastPrice: result.lastPrice } };
            liveStatusesRef.current = next;
            return next;
          });
        } catch {
          // Sessizce geç
        }
      }
    };

    updateStatuses();
    const intervalId = setInterval(updateStatuses, 30000);

    return () => {
      stopped = true;
      clearInterval(intervalId);
    };
  }, [mode, allSignals]);

  // Filtreleme mantığı
  const isInRange = (sig) => {
    if (!dateStart && !dateEnd) return true;
    const ts = sig.dateObj.getTime();
    const startTs = dateStart ? new Date(`${dateStart}T00:00:00`).getTime() : -Infinity;
    const endTs = dateEnd ? new Date(`${dateEnd}T23:59:59`).getTime() : Infinity;
    return ts >= startTs && ts <= endTs;
  };

  useEffect(() => {
    if (allSignals.length > 0) {
      setFilteredSignals(
        allSignals.filter(s => selectedSymbols.has(s.symbol) && isInRange(s))
      );
    }
  }, [selectedSymbols, allSignals, dateStart, dateEnd]);

  const toggleSymbol = (symbol) => {
    const newSet = new Set(pendingSymbols);
    if (newSet.has(symbol)) newSet.delete(symbol);
    else newSet.add(symbol);
    setPendingSymbols(newSet);
  };

  const applySymbols = () => {
    setSelectedSymbols(new Set(pendingSymbols));
  };

  const clearPendingSymbols = () => {
    setPendingSymbols(new Set());
  };

  const selectAllPendingSymbols = () => {
    const symbols = new Set(allSignals.map(s => s.symbol));
    setPendingSymbols(symbols);
  };

  const applyDates = () => {
    setDateStart(pendingDateStart);
    setDateEnd(pendingDateEnd);
  };

  return (
    <TradeContext.Provider value={{
      allSignals, filteredSignals, selectedSymbols, pendingSymbols, isLoaded, processData,
      activeSignal, setActiveSignal, showStats, setShowStats, toggleSymbol, applySymbols,
      clearPendingSymbols, selectAllPendingSymbols,
      chartView, setChartView, showSummary, setShowSummary,
      dateStart, setDateStart, dateEnd, setDateEnd,
      pendingDateStart, setPendingDateStart, pendingDateEnd, setPendingDateEnd,
      applyDates,
      mode, setMode, liveError,
      liveStatuses,
      backtestInsights,
      dbStatus, dbMessage, testDbConnection
    }}>
      {children}
    </TradeContext.Provider>
  );
};
