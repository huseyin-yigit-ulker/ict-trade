import { useState } from 'react';
import { useTradeContext } from '../context/TradeContext';

const Header = () => {
  const {
    selectedSymbols,
    pendingSymbols,
    allSignals,
    toggleSymbol,
    applySymbols,
    setShowStats,
    setShowSummary,
    dateStart,
    setDateStart,
    dateEnd,
    setDateEnd
  } = useTradeContext();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [dateOpen, setDateOpen] = useState(false);

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
                  checked={pendingSymbols.has(sym)}
                  onChange={() => toggleSymbol(sym)}
                />
                {sym}
              </label>
            ))}
            <button
              className="apply-btn"
              onClick={() => {
                applySymbols();
                setDropdownOpen(false);
              }}
            >
              Uygula
            </button>
          </div>
        </div>

        <div className="date-filters">
          <button
            className="date-picker-btn"
            onClick={() => setDateOpen(!dateOpen)}
          >
            Tarih Seçimi
          </button>
          {dateOpen && (
            <div className="date-popover" onClick={(e) => e.stopPropagation()}>
              <div className="date-field">
                <span>Başlangıç</span>
                <input
                  type="date"
                  value={dateStart}
                  onChange={(e) => setDateStart(e.target.value)}
                />
              </div>
              <div className="date-field">
                <span>Bitiş</span>
                <input
                  type="date"
                  value={dateEnd}
                  onChange={(e) => setDateEnd(e.target.value)}
                />
              </div>
              <div className="date-actions">
                <button
                  className="apply-btn"
                  onClick={() => setDateOpen(false)}
                >
                  Uygula
                </button>
                <button
                  className="apply-btn ghost"
                  onClick={() => {
                    setDateStart('');
                    setDateEnd('');
                    setDateOpen(false);
                  }}
                >
                  Temizle
                </button>
              </div>
            </div>
          )}
        </div>

        <button id="btn-stats" className="header-btn" onClick={() => setShowStats(true)}>📊 Özet</button>
        <button id="btn-summary" className="header-btn" onClick={() => setShowSummary(true)}>📈 Başarı</button>
      </div>

      <div className="status-badge">Mod: Backtest</div>

      {(dropdownOpen || dateOpen) && (
        <div
          className="header-overlay"
          onClick={() => {
            setDropdownOpen(false);
            setDateOpen(false);
          }}
        ></div>
      )}
    </div>
  );
};

export default Header;
