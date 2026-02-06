import { useState } from 'react';
import { useTradeContext } from '../context/TradeContext';

const Header = () => {
  const { selectedSymbols, allSignals, toggleSymbol, setShowStats } = useTradeContext();
  const [dropdownOpen, setDropdownOpen] = useState(false);

  const uniqueSymbols = [...new Set(allSignals.map(s => s.symbol))].sort();

  return (
    <div className="app-header">
      <div className="header-title">
        ⚡ ICT TRADING JOURNAL
        <span className="source-badge">BINANCE F</span>
      </div>

      <div className="header-controls">
        <div className="multi-select-container">
          <button 
            id="multi-select-btn" 
            className="coin-select" 
            onClick={() => setDropdownOpen(!dropdownOpen)}
          >
            Coin Seçimi ({selectedSymbols.size})
          </button>
          
          <div id="multi-select-list" className={`multi-select-content ${dropdownOpen ? 'show' : ''}`}>
            {uniqueSymbols.map(sym => (
              <label key={sym} onClick={(e) => e.stopPropagation()}>
                <input 
                  type="checkbox" 
                  checked={selectedSymbols.has(sym)} 
                  onChange={() => toggleSymbol(sym)}
                /> 
                {sym}
              </label>
            ))}
          </div>
          {/* Dışarı tıklayınca kapanması için basit bir overlay eklenebilir veya useEffect kullanılabilir */}
        </div>

        <button id="btn-stats" className="header-btn" onClick={() => setShowStats(true)}>📊 ÖZET TABLO</button>
      </div>
      
      <div className="status-badge" style={{ fontSize: '12px', color: '#aaa' }}>Mod: Backtest</div>
    </div>
  );
};

export default Header;