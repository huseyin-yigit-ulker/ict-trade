import { useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { useTradeContext } from '../../context/TradeContext';
import { useLang } from '../../context/LanguageContext';

const STRAT_LABEL = { main: 'Main', radar: 'Radar', pulse: 'Pulse' };
const MODE_LABEL = { live: 'Live', backtest: 'Backtest' };

const Topbar = () => {
  const {
    sidebarHidden, toggleSidebar, dbStatus, dbMessage, strategy, mode,
    statusFilter, setStatusFilter,
    selectedSymbols, pendingSymbols, allSignals,
    toggleSymbol, applySymbols, clearPendingSymbols, selectAllPendingSymbols,
  } = useTradeContext();
  const { t } = useLang();
  const loc = useLocation();

  const [symOpen, setSymOpen] = useState(false);
  const [symQuery, setSymQuery] = useState('');
  const uniqueSymbols = useMemo(() => [...new Set(allSignals.map((s) => s.symbol))].sort(), [allSignals]);
  const filteredSymbols = useMemo(() => {
    if (!symQuery) return uniqueSymbols;
    const q = symQuery.toLowerCase();
    return uniqueSymbols.filter((s) => s.toLowerCase().includes(q));
  }, [uniqueSymbols, symQuery]);
  useEffect(() => { if (!symOpen) setSymQuery(''); }, [symOpen]);

  // Symbols + status filter are per-view controls — shown only on the 4 strategy×mode
  // views, on the RIGHT side of the bar. Hidden on Intelligence / Settings.
  const isView = loc.pathname !== '/settings' && loc.pathname !== '/intelligence';
  const STATUS_FILTERS = [
    { key: 'all', label: t('Tümü') },
    { key: 'tp', label: 'TP' },
    { key: 'sl', label: 'SL' },
    ...(mode === 'live' ? [{ key: 'active', label: t('Aktif') }] : []),
    { key: 'cancelled', label: t('İptal') },
  ];

  return (
    <header className="topbar">
      <div className="topbar__left">
        <button
          className="icon-btn topbar__toggle"
          onClick={toggleSidebar}
          title={sidebarHidden ? t('Menüyü Göster') : t('Menüyü Gizle')}
          aria-label={sidebarHidden ? t('Menüyü Göster') : t('Menüyü Gizle')}
        >
          {sidebarHidden ? '☰' : '‹‹'}
        </button>
        <div className="topbar__title">
          {loc.pathname === '/settings' ? t('Ayarlar')
            : loc.pathname === '/intelligence' ? t('İstihbarat')
            : `${t(STRAT_LABEL[strategy] || 'Main')} · ${t(MODE_LABEL[mode] || 'Live')}`}
        </div>
      </div>

      <div className="topbar__controls">
        {isView && (
          <>
            <div className="status-filter" role="group" aria-label="status filter">
              {STATUS_FILTERS.map((f) => (
                <button
                  key={f.key}
                  className={`status-filter__btn status-filter__btn--${f.key} ${statusFilter === f.key ? 'active' : ''}`}
                  onClick={() => setStatusFilter(f.key)}
                >
                  {f.label}
                </button>
              ))}
            </div>

            <div className="multi-select-container">
              <button className="coin-select" onClick={() => setSymOpen((o) => !o)}>
                🪙 {t('Semboller')} ({selectedSymbols.size})
              </button>
              <div className={`multi-select-content ${symOpen ? 'show' : ''}`}>
                <input
                  className="symbol-search" type="text" placeholder={t('Sembol ara...')}
                  value={symQuery} onChange={(e) => setSymQuery(e.target.value)} onClick={(e) => e.stopPropagation()}
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
                <button className="apply-btn" onClick={() => { applySymbols(); setSymOpen(false); }}>✅ {t('Uygula')}</button>
                <button className="apply-btn" onClick={selectAllPendingSymbols}>{t('Tümünü Seç')}</button>
                <button className="apply-btn ghost" onClick={clearPendingSymbols}>🧹 {t('Temizle')}</button>
              </div>
            </div>
          </>
        )}

        {dbMessage && <span className={`db-pill ${dbStatus}`}>{dbMessage}</span>}
      </div>

      {symOpen && <div className="header-overlay" onClick={() => setSymOpen(false)} />}
    </header>
  );
};

export default Topbar;
