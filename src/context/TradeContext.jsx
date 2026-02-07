import { createContext, useState, useEffect, useContext } from 'react';
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
  const [mode, setMode] = useState('backtest'); // backtest | live
  const [liveError, setLiveError] = useState('');

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
    const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;
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

      const res = await fetch(`${supabaseUrl}/rest/v1/signals?${params.toString()}`, {
        headers: {
          apikey: supabaseKey,
          Authorization: `Bearer ${supabaseKey}`
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

  useEffect(() => {
    let intervalId;
    if (mode === 'backtest') {
      if (defaultData) processData(defaultData);
    } else {
      loadLive();
      intervalId = setInterval(loadLive, 15 * 60 * 1000);
    }

    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [mode]);

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

  const applyDates = () => {
    setDateStart(pendingDateStart);
    setDateEnd(pendingDateEnd);
  };

  return (
    <TradeContext.Provider value={{
      allSignals, filteredSignals, selectedSymbols, pendingSymbols, isLoaded, processData,
      activeSignal, setActiveSignal, showStats, setShowStats, toggleSymbol, applySymbols,
      chartView, setChartView, showSummary, setShowSummary,
      dateStart, setDateStart, dateEnd, setDateEnd,
      pendingDateStart, setPendingDateStart, pendingDateEnd, setPendingDateEnd,
      applyDates,
      mode, setMode, liveError
    }}>
      {children}
    </TradeContext.Provider>
  );
};
