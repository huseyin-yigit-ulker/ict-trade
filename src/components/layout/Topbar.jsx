import { useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { useTradeContext } from '../../context/TradeContext';
import { useLang } from '../../context/LanguageContext';

const STRAT_LABEL = { main: 'Main', impulse: 'Impulse', radar: 'Radar', squeeze: 'Squeeze' };
const MODE_LABEL = { live: 'Live', backtest: 'Backtest' };

// ICT killzones (UTC) — the windows the engine actually hunts in. The pill
// shows the active zone + time left, or the countdown to the next one.
const KILLZONES = [
  { label: 'ASIA KZ',   start: 0 * 60,  end: 4 * 60 },
  { label: 'LONDON KZ', start: 7 * 60,  end: 10 * 60 },
  { label: 'NY AM KZ',  start: 12 * 60, end: 15 * 60 },
  { label: 'LDN CLOSE', start: 15 * 60, end: 17 * 60 },
];

// Compact "time left" via the existing duration i18n keys ('{h} sa {m} dk').
const fmtLeft = (mins, t) => {
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return h > 0 ? t('{h} sa {m} dk', { h, m }) : t('{m} dk', { m });
};

const KillzoneClock = () => {
  const { t } = useLang();
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(id);
  }, []);

  const utcMin = now.getUTCHours() * 60 + now.getUTCMinutes();
  const active = KILLZONES.find((k) => utcMin >= k.start && utcMin < k.end);
  let body;
  if (active) {
    body = <><span className="kz-dot kz-dot--on" />{active.label} · {fmtLeft(active.end - utcMin, t)}</>;
  } else {
    const next = KILLZONES.find((k) => k.start > utcMin) || KILLZONES[0];
    const wait = next.start > utcMin ? next.start - utcMin : 24 * 60 - utcMin + next.start;
    body = <><span className="kz-dot" />{t('Sonraki')}: {next.label} · {fmtLeft(wait, t)}</>;
  }

  const clock = `${String(now.getUTCHours()).padStart(2, '0')}:${String(now.getUTCMinutes()).padStart(2, '0')}`;
  return (
    <span
      className={`kz-pill${active ? ' kz-pill--active' : ''}`}
      title={t('ICT killzone saati (UTC)')}
    >
      <span className="kz-clock">{clock} UTC</span>
      {body}
    </span>
  );
};

const Topbar = () => {
  const {
    sidebarHidden, toggleSidebar, dbStatus, dbMessage, strategy, mode,
    statusFilter, setStatusFilter,
    selectedSymbols, pendingSymbols, allSignals,
    toggleSymbol, applySymbols, clearPendingSymbols, selectAllPendingSymbols,
    refresh, refreshing, lastUpdated,
  } = useTradeContext();
  const { t, locale } = useLang();
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
        <KillzoneClock />
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

        {isView && (
          <button
            className={`icon-btn topbar__refresh${refreshing ? ' is-spinning' : ''}`}
            onClick={refresh}
            disabled={refreshing}
            title={lastUpdated
              ? `${t('Son güncelleme')}: ${lastUpdated.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' })}`
              : t('Yenile')}
            aria-label={t('Yenile')}
          >
            ⟳
          </button>
        )}
        {dbMessage && <span className={`db-pill ${dbStatus}`}>{dbMessage}</span>}
      </div>

      {symOpen && <div className="header-overlay" onClick={() => setSymOpen(false)} />}
    </header>
  );
};

export default Topbar;
