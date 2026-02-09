import { createContext, useState, useEffect, useContext, useRef } from 'react';
// MUST IMPORT DIRECTLY:
import defaultData from '../assets/data/trades.json';

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
  const liveStatusesRef = useRef({});

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
      // Status Mapping
      let status = 'WAITING';
      if (item.status === 'TAKE PROFIT') status = 'TP';
      else if (item.status === 'STOP LOSS') status = 'SL';
      else if (item.status) status = item.status;

      const entry = parseFloat(item.entry_price);
      let exitPrice = item.current_price || entry;
      if (status === 'TP') exitPrice = parseFloat(item.tp_price);
      if (status === 'SL') exitPrice = parseFloat(item.sl_price);

      const signalTime = new Date(item.signal_time).getTime();
      const exitTime = item.exit_time 
        ? new Date(item.exit_time).getTime() 
        : signalTime + (2 * 60 * 60 * 1000);

      return {
        id: index,
        symbol: item.symbol,
        dir: item.trade_type === 'BUY' ? 'LONG' : 'SHORT',
        entry,
        tp: parseFloat(item.tp_price),
        sl: parseFloat(item.sl_price),
        dateObj: new Date(item.signal_time),
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
      const start = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), 0, 0, 0));
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
    if (mode === 'backtest') {
      if (defaultData) processData(defaultData);
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
      return 'Sinyal Bekliyor';
    }
    const entryTs = Math.floor(sig.dateObj.getTime() / 1000);
    let entryHitTime = null;
    for (const c of candles) {
      if (c.time < entryTs) continue;
      const entryTouched = sig.dir === 'LONG' ? c.low <= sig.entry : c.high >= sig.entry;
      const tpHit = sig.dir === 'LONG' ? c.high >= sig.tp : c.low <= sig.tp;
      const slHit = sig.dir === 'LONG' ? c.low <= sig.sl : c.high >= sig.sl;
      if (!entryTouched && (tpHit || slHit)) return 'İptal (Entry Gelmeden TP/SL)';
      if (entryTouched) {
        entryHitTime = c.time;
        break;
      }
    }
    if (entryHitTime === null) return 'Sinyal Bekliyor';
    for (const c of candles) {
      if (c.time < entryHitTime) continue;
      const tpHit = sig.dir === 'LONG' ? c.high >= sig.tp : c.low <= sig.tp;
      const slHit = sig.dir === 'LONG' ? c.low <= sig.sl : c.high >= sig.sl;
      if (tpHit || slHit) {
        return tpHit && slHit ? 'TP/SL Aynı Mum' : (tpHit ? 'TP Oldu' : 'SL Oldu');
      }
    }
    return 'İşlem Aktif (Entry Geldi)';
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
          const status = computeLiveStatusFromCandles(sig, candles);
          if (stopped) return;
          setLiveStatuses(prev => {
            const next = { ...prev, [sig.id]: { status } };
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
      dbStatus, dbMessage, testDbConnection
    }}>
      {children}
    </TradeContext.Provider>
  );
};
