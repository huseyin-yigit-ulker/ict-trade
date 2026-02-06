import { createContext, useState, useEffect, useContext } from 'react';
// 1. JSON dosyasını direkt import ediyoruz
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

  // Veriyi işleyen fonksiyon
  const processData = (data) => {
    if (!data || !Array.isArray(data)) {
        console.error("Veri formatı hatalı veya boş!");
        return;
    }

    const processed = data.map((item, index) => {
      const status = item.status === 'TAKE PROFIT' ? 'TP' : item.status === 'STOP LOSS' ? 'SL' : item.status || 'WAITING';
      const entry = parseFloat(item.entry_price);
      let exitPrice = item.current_price || entry;
      if (status === 'TP') exitPrice = parseFloat(item.tp_price);
      if (status === 'SL') exitPrice = parseFloat(item.sl_price);

      return {
        id: index,
        symbol: item.symbol,
        dir: item.trade_type === 'BUY' ? 'LONG' : 'SHORT',
        entry,
        tp: parseFloat(item.tp_price),
        sl: parseFloat(item.sl_price),
        dateObj: new Date(item.signal_time),
        exitTs: item.exit_time ? new Date(item.exit_time).getTime() : new Date(item.signal_time).getTime() + (2 * 60 * 60 * 1000),
        status,
        exitPrice
      };
    }).sort((a, b) => b.dateObj - a.dateObj);

    setAllSignals(processed);
    
    // İlk yüklemede tüm sembolleri seç
    const symbols = new Set(processed.map(s => s.symbol));
    setSelectedSymbols(symbols);
    setIsLoaded(true);
  };

  // 2. useEffect içinde import edilen veriyi yüklüyoruz
  useEffect(() => {
    if (defaultData) {
        console.log("Veri başarıyla yüklendi:", defaultData.length, "adet işlem.");
        processData(defaultData);
    } else {
        console.error("JSON dosyası okunamadı!");
    }
  }, []);

  // Filtreleme Mantığı
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