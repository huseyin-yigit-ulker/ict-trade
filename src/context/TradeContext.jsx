import { createContext, useState, useEffect, useContext } from 'react';
// MUST IMPORT DIRECTLY:
import defaultData from '../assets/data/trades.json';

const TradeContext = createContext();
export const useTradeContext = () => useContext(TradeContext);
export const TradeProvider = ({ children }) => {
  const [allSignals, setAllSignals] = useState([]);
  const [filteredSignals, setFilteredSignals] = useState([]);
  const [selectedSymbols, setSelectedSymbols] = useState(new Set());
  const [isLoaded, setIsLoaded] = useState(false);
  const [activeSignal, setActiveSignal] = useState(null);
  const [showStats, setShowStats] = useState(false);

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
    setIsLoaded(true);
  };

  // Başlangıçta veriyi yükle
  useEffect(() => {
    if (defaultData) {
      processData(defaultData);
    }
  }, []);

  // Filtreleme mantığı
  useEffect(() => {
    if (allSignals.length > 0) {
      setFilteredSignals(allSignals.filter(s => selectedSymbols.has(s.symbol)));
    }
  }, [selectedSymbols, allSignals]);

  const toggleSymbol = (symbol) => {
    const newSet = new Set(selectedSymbols);
    if (newSet.has(symbol)) newSet.delete(symbol);
    else newSet.add(symbol);
    setSelectedSymbols(newSet);
  };

  return (
    <TradeContext.Provider value={{
      allSignals, filteredSignals, selectedSymbols, isLoaded, processData,
      activeSignal, setActiveSignal, showStats, setShowStats, toggleSymbol
    }}>
      {children}
    </TradeContext.Provider>
  );
};
