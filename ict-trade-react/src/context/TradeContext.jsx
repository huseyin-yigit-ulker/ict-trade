import { createContext, useState, useEffect, useContext } from 'react';

const TradeContext = createContext();

export const useTradeContext = () => useContext(TradeContext);

export const TradeProvider = ({ children }) => {
  const [allSignals, setAllSignals] = useState([]);
  const [filteredSignals, setFilteredSignals] = useState([]);
  const [selectedSymbols, setSelectedSymbols] = useState(new Set());
  const [isLoaded, setIsLoaded] = useState(false);
  const [activeSignal, setActiveSignal] = useState(null); // Grafik için seçili işlem
  const [showStats, setShowStats] = useState(false);

  // Status mapping ve veri işleme
  const processData = (data) => {
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

  // Otomatik yükleme (Local JSON)
  useEffect(() => {
    fetch('/src/assets/data/trades.json') // Vite'de public veya direct import da olabilir
      .then(res => res.json())
      .then(data => processData(data))
      .catch(err => console.log("Otomatik yükleme başarısız, manuel bekleniyor."));
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