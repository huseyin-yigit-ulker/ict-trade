import { useEffect, useMemo, useState } from 'react';
import { useTradeContext } from '../context/TradeContext';

const Header = () => {
  const {
    selectedSymbols,
    pendingSymbols,
    allSignals,
    toggleSymbol,
    applySymbols,
    clearPendingSymbols,
    selectAllPendingSymbols,
    setShowSummary,
    mode,
    setMode,
    liveError,
    dbStatus,
    dbMessage,
  } = useTradeContext();

  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [symbolQuery, setSymbolQuery] = useState('');

  const uniqueSymbols = [...new Set(allSignals.map((s) => s.symbol))].sort();

  const filteredSymbols = useMemo(() => {
    if (!symbolQuery) return uniqueSymbols;
    const q = symbolQuery.toLowerCase();
    return uniqueSymbols.filter((sym) => sym.toLowerCase().includes(q));
  }, [uniqueSymbols, symbolQuery]);

  useEffect(() => {
    if (!dropdownOpen) setSymbolQuery('');
  }, [dropdownOpen]);

  return (
    <div className="app-header">
      <div className="header-title">
        <div className="brand-mark">
          <svg className="brand-icon" viewBox="0 0 18 18" aria-hidden="true">
            <polyline points="2,13 6,9 9,11 13,5 16,3"
              stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"
              strokeLinejoin="round" fill="none" />
            <circle cx="16" cy="3" r="1.6" fill="currentColor" />
          </svg>
          ICT NOTEBOOK
          {mode === 'live' && (
            <span className="brand-live-pulse" title="Live mode active" />
          )}
        </div>
        <div className="brand-sub">ICT Engine • 1h MTF • {selectedSymbols.size} Sembol</div>
      </div>

      <div className="header-controls">
        {mode && (
          <button
            className="header-btn mode-toggle"
            onClick={() => setMode(mode === 'live' ? 'backtest' : 'live')}
          >
            {mode === 'live' ? '📂 Backtest\'e Geç' : '🛰️ Live\'a Geç'}
          </button>
        )}
        <div className="multi-select-container">
          <button
            id="multi-select-btn"
            className="coin-select"
            onClick={() => setDropdownOpen(!dropdownOpen)}
          >
            🪙 Sembol Seçimi ({selectedSymbols.size})
          </button>

          <div className={`multi-select-content ${dropdownOpen ? 'show' : ''}`} id="multi-select-list">
            <input
              className="symbol-search"
              type="text"
              placeholder="Sembol ara..."
              value={symbolQuery}
              onChange={(e) => setSymbolQuery(e.target.value)}
              onClick={(e) => e.stopPropagation()}
            />
            <div className="symbol-list" onClick={(e) => e.stopPropagation()}>
              {filteredSymbols.length === 0 && (
                <div className="symbol-empty">Sonuç yok</div>
              )}
              {filteredSymbols.map((sym) => (
                <label key={sym}>
                  <input
                    type="checkbox"
                    checked={pendingSymbols.has(sym)}
                    onChange={() => toggleSymbol(sym)}
                  />
                  {sym}
                </label>
              ))}
            </div>
            <button
              className="apply-btn"
              onClick={() => {
                applySymbols();
                setDropdownOpen(false);
              }}
            >
              ✅ Uygula
            </button>
            <button
              className="apply-btn"
              onClick={() => selectAllPendingSymbols()}
            >
              ✅ Tümünü Seç
            </button>
            <button
              className="apply-btn ghost"
              onClick={() => clearPendingSymbols()}
            >
              🧹 Temizle
            </button>
          </div>
        </div>

        {mode !== 'live' && (
          <button id="btn-summary" className="header-btn" onClick={() => setShowSummary(true)}>
            📈 Başarı Geçmişi
          </button>
        )}
      </div>

      <div className="status-badge">
        Mod: {mode === 'live' ? 'Live' : mode === 'backtest' ? 'Backtest' : 'Seçilmedi'}
        {liveError && <span className="status-error"> • {liveError}</span>}
        {dbMessage && <span className={`db-pill ${dbStatus}`}> • {dbMessage}</span>}
      </div>

      {dropdownOpen && (
        <div
          className="header-overlay"
          onClick={() => setDropdownOpen(false)}
        />
      )}
    </div>
  );
};

export default Header;
