import { useEffect, useMemo, useState } from 'react';
import { useTradeContext } from '../context/TradeContext';
import { useLang } from '../context/LanguageContext';
import PusuLogo from './PusuLogo';

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
  const { t, lang, setLang } = useLang();

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
          <PusuLogo size={26} className="brand-icon" />
          PUSU
          {mode === 'live' && (
            <span className="brand-live-pulse" title="Live mode active" />
          )}
        </div>
        <div className="brand-sub">{t('Likidite Avı')} • 1h MTF • {selectedSymbols.size} {t('Sembol')}</div>
      </div>

      <div className="header-controls">
        <div className="lang-toggle" role="group" aria-label="language">
          <button className={lang === 'tr' ? 'active' : ''} onClick={() => setLang('tr')}>TR</button>
          <button className={lang === 'en' ? 'active' : ''} onClick={() => setLang('en')}>EN</button>
        </div>

        {mode && (
          <button
            className="header-btn mode-toggle"
            onClick={() => setMode(mode === 'live' ? 'backtest' : 'live')}
          >
            {mode === 'live' ? `📂 ${t("Backtest'e Geç")}` : `🛰️ ${t("Live'a Geç")}`}
          </button>
        )}
        <div className="multi-select-container">
          <button
            id="multi-select-btn"
            className="coin-select"
            onClick={() => setDropdownOpen(!dropdownOpen)}
          >
            🪙 {t('Sembol Seçimi')} ({selectedSymbols.size})
          </button>

          <div className={`multi-select-content ${dropdownOpen ? 'show' : ''}`} id="multi-select-list">
            <input
              className="symbol-search"
              type="text"
              placeholder={t('Sembol ara...')}
              value={symbolQuery}
              onChange={(e) => setSymbolQuery(e.target.value)}
              onClick={(e) => e.stopPropagation()}
            />
            <div className="symbol-list" onClick={(e) => e.stopPropagation()}>
              {filteredSymbols.length === 0 && (
                <div className="symbol-empty">{t('Sonuç yok')}</div>
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
              ✅ {t('Uygula')}
            </button>
            <button
              className="apply-btn"
              onClick={() => selectAllPendingSymbols()}
            >
              ✅ {t('Tümünü Seç')}
            </button>
            <button
              className="apply-btn ghost"
              onClick={() => clearPendingSymbols()}
            >
              🧹 {t('Temizle')}
            </button>
          </div>
        </div>

        {mode !== 'live' && (
          <button id="btn-summary" className="header-btn" onClick={() => setShowSummary(true)}>
            📈 {t('Başarı Geçmişi')}
          </button>
        )}
      </div>

      <div className="status-badge">
        {t('Mod')}: {mode === 'live' ? t('Live') : mode === 'backtest' ? t('Backtest') : t('Seçilmedi')}
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
