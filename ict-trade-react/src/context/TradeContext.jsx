import { createContext, useState, useEffect, useContext } from 'react';
// 1. JSON dosyasını direkt import ediyoruz (En garanti yöntem)
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
        console.error("Veri hatalı veya boş!");
        return;
    }

    const processed = data.map((item, index) => {
      // Status mapping
      let status = item.status || 'WAITING';
      if (item.status === 'TAKE PROFIT') status = 'TP';
      if (item.status === 'STOP LOSS') status = 'SL';

      const entry = parseFloat(item.entry_price);
      let exitPrice = item.current_price || entry;
      
      if (status === 'TP') exitPrice = parseFloat(item.tp_price);
      if (status === 'SL') exitPrice = parseFloat(item.sl_price);

      // Tarih hesaplama (Eğer exit_time yoksa 2 saat ekle)
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
    
    // Tüm sembolleri seçili hale getir
    const symbols = new Set(processed.map(s => s.symbol));
    setSelectedSymbols(symbols);
    
    // Yükleme tamamlandı
    setIsLoaded(true);
  };

  // 2. useEffect içinde import edilen veriyi yüklüyoruz
  useEffect(() => {
    if (defaultData) {
        processData(defaultData);
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