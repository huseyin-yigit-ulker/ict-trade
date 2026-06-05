import { useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { useTradeContext } from '../../context/TradeContext';
import { useLang } from '../../context/LanguageContext';
import { useTheme } from '../../context/ThemeContext';

const TITLES = { '/command': 'Komuta Merkezi', '/intelligence': 'İstihbarat', '/settings': 'Ayarlar' };
const MODES = ['live', 'observe', 'backtest'];

const Topbar = () => {
  const {
    selectedSymbols, pendingSymbols, allSignals,
    toggleSymbol, applySymbols, clearPendingSymbols, selectAllPendingSymbols,
    appMode, setAppMode, dbStatus, dbMessage,
  } = useTradeContext();
  const { t, lang, setLang } = useLang();
  const { theme, toggle } = useTheme();
  const loc = useLocation();

  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [symbolQuery, setSymbolQuery] = useState('');

  const uniqueSymbols = [...new Set(allSignals.map((s) => s.symbol))].sort();
  const filteredSymbols = useMemo(() => {
    if (!symbolQuery) return uniqueSymbols;
    const q = symbolQuery.toLowerCase();
    return uniqueSymbols.filter((sym) => sym.toLowerCase().includes(q));
  }, [uniqueSymbols, symbolQuery]);

  useEffect(() => { if (!dropdownOpen) setSymbolQuery(''); }, [dropdownOpen]);

  const onSettings = loc.pathname === '/settings';
  const hideSymbols = onSettings || loc.pathname === '/intelligence';

  return (
    <header className="topbar">
      <div className="topbar__left">
        <div className="topbar__title">{t(TITLES[loc.pathname] || 'Komuta Merkezi')}</div>
        <div className="mode-switch" role="group" aria-label="system mode">
          {MODES.map((m) => (
            <button
              key={m}
              className={`mode-switch__btn mode-switch__btn--${m} ${appMode === m ? 'active' : ''}`}
              onClick={() => setAppMode(m)}
              title={m.toUpperCase()}
            >
              <span className="mode-switch__dot" />{m.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      <div className="topbar__controls">
        <button className="icon-btn" onClick={toggle} title={t('Tema')} aria-label={t('Tema')}>
          {theme === 'dark' ? '☾' : '☀'}
        </button>

        <div className="lang-toggle" role="group" aria-label="language">
          <button className={lang === 'tr' ? 'active' : ''} onClick={() => setLang('tr')}>TR</button>
          <button className={lang === 'en' ? 'active' : ''} onClick={() => setLang('en')}>EN</button>
        </div>

        {!hideSymbols && (
          <div className="multi-select-container">
            <button className="coin-select" onClick={() => setDropdownOpen(!dropdownOpen)}>
              🪙 {t('Sembol Seçimi')} ({selectedSymbols.size})
            </button>
            <div className={`multi-select-content ${dropdownOpen ? 'show' : ''}`}>
              <input
                className="symbol-search" type="text" placeholder={t('Sembol ara...')}
                value={symbolQuery}
                onChange={(e) => setSymbolQuery(e.target.value)}
                onClick={(e) => e.stopPropagation()}
              />
              <div className="symbol-list" onClick={(e) => e.stopPropagation()}>
                {filteredSymbols.length === 0 && <div className="symbol-empty">{t('Sonuç yok')}</div>}
                {filteredSymbols.map((sym) => (
                  <label key={sym}>
                    <input type="checkbox" checked={pendingSymbols.has(sym)} onChange={() => toggleSymbol(sym)} />
                    {sym}
                  </label>
                ))}
              </div>
              <button className="apply-btn" onClick={() => { applySymbols(); setDropdownOpen(false); }}>✅ {t('Uygula')}</button>
              <button className="apply-btn" onClick={() => selectAllPendingSymbols()}>✅ {t('Tümünü Seç')}</button>
              <button className="apply-btn ghost" onClick={() => clearPendingSymbols()}>🧹 {t('Temizle')}</button>
            </div>
          </div>
        )}

        {dbMessage && <span className={`db-pill ${dbStatus}`}>{dbMessage}</span>}
      </div>

      {dropdownOpen && <div className="header-overlay" onClick={() => setDropdownOpen(false)} />}
    </header>
  );
};

export default Topbar;
