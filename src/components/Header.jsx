import { useState } from 'react';
import { useTradeContext } from '../context/TradeContext';

const Header = () => {
  const { selectedSymbols, allSignals, toggleSymbol, setShowStats } = useTradeContext();
  const [dropdownOpen, setDropdownOpen] = useState(false);

  const uniqueSymbols = [...new Set(allSignals.map(s => s.symbol))].sort();

  return (
    <div className="app-header">
      <div className="header-title">
        <div className="brand-mark">ICT NOTEBOOK</div>
        <div className="brand-sub">TradingView Webhook • 1m Journal</div>
      </div>

      <div className="header-controls">
        <div className="multi-select-container">
          <button
            id="multi-select-btn"
            className="coin-select"
            onClick={() => setDropdownOpen(!dropdownOpen)}
          >
            Sembol Seçimi ({selectedSymbols.size})
          </button>

          <div className={`multi-select-content ${dropdownOpen ? 'show' : ''}`} id="multi-select-list">
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
        </div>

        <button id="btn-stats" className="header-btn" onClick={() => setShowStats(true)}>📊 Özet</button>
      </div>

      <div className="status-badge">Mod: Backtest</div>

      {dropdownOpen && (
        <div
          className="header-overlay"
          onClick={() => setDropdownOpen(false)}
        ></div>
      )}
    </div>
  );
};

export default Header;
