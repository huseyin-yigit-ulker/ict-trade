import { useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { useTradeContext, KARMA_MAP } from '../../context/TradeContext';
import { useLang } from '../../context/LanguageContext';
import { MARKETS, marketOf, strategyBadge } from '../../utils/symbolMeta';
import { usSignalsActive } from '../../utils/sessions';
import SessionInfo from '../SessionInfo';

const STRAT_BASE_LABEL = { main: 'Main', range: 'Range', opus: 'Opus', midas: 'Midas' };
// light twins reuse the parent label + " · Light"
const STRAT_LABEL = { ...STRAT_BASE_LABEL };
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
    sidebarHidden, toggleSidebar, mobileNavOpen, toggleMobileNav,
    dbStatus, dbMessage, strategy, mode,
    statusFilter, setStatusFilter,
    selectedSymbols, pendingSymbols, allSignals,
    toggleSymbol, applySymbols, applySymbolSet, symbolPerf,
    clearPendingSymbols, selectAllPendingSymbols,
    refresh, refreshing, lastUpdated,
  } = useTradeContext();
  const { t, locale } = useLang();
  const loc = useLocation();

  // On phones the toggle opens the overlay drawer; on desktop it collapses the
  // persistent rail. Track the breakpoint reactively so the glyph/handler follow.
  const [isNarrow, setIsNarrow] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(max-width: 768px)').matches,
  );
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 768px)');
    const on = (e) => setIsNarrow(e.matches);
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, []);

  const [symOpen, setSymOpen] = useState(false);
  const [sessOpen, setSessOpen] = useState(false);
  const [symQuery, setSymQuery] = useState('');
  const uniqueSymbols = useMemo(() => [...new Set(allSignals.map((s) => s.symbol))].sort(), [allSignals]);
  const filteredSymbols = useMemo(() => {
    if (!symQuery) return uniqueSymbols;
    const q = symQuery.toLowerCase();
    return uniqueSymbols.filter((s) => s.toLowerCase().includes(q));
  }, [uniqueSymbols, symQuery]);
  useEffect(() => { if (!symOpen) setSymQuery(''); }, [symOpen]);

  // best/worst ranking is by resolved backtest R — only meaningful when loaded
  // signals carry pnlR (backtest mode). In live mode the chips are hidden.
  const hasPerf = useMemo(
    () => uniqueSymbols.some((s) => (symbolPerf?.[s]?.closed || 0) > 0),
    [uniqueSymbols, symbolPerf]
  );
  const rankedByR = useMemo(
    () => uniqueSymbols
      .filter((s) => (symbolPerf?.[s]?.closed || 0) > 0)
      .sort((a, b) => (symbolPerf[b].totalR || 0) - (symbolPerf[a].totalR || 0)),
    [uniqueSymbols, symbolPerf]
  );
  const TOP_N = 5;
  const applyMarket = (key) => { applySymbolSet(uniqueSymbols.filter((s) => marketOf(s) === key)); setSymOpen(false); };
  const applyBest = () => { applySymbolSet(rankedByR.slice(0, TOP_N)); setSymOpen(false); };
  const applyWorst = () => { applySymbolSet(rankedByR.slice(-TOP_N)); setSymOpen(false); };

  // Symbols + status filter are per-view controls — shown only on the 4 strategy×mode
  // views, on the RIGHT side of the bar. Hidden on Intelligence / Settings.
  const isView = loc.pathname !== '/settings' && loc.pathname !== '/intelligence'
    && loc.pathname !== '/' && loc.pathname !== '/trend';
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
          onClick={isNarrow ? toggleMobileNav : toggleSidebar}
          title={isNarrow
            ? (mobileNavOpen ? t('Menüyü Gizle') : t('Menüyü Göster'))
            : (sidebarHidden ? t('Menüyü Göster') : t('Menüyü Gizle'))}
          aria-label={isNarrow
            ? (mobileNavOpen ? t('Menüyü Gizle') : t('Menüyü Göster'))
            : (sidebarHidden ? t('Menüyü Göster') : t('Menüyü Gizle'))}
          aria-expanded={isNarrow ? mobileNavOpen : undefined}
        >
          {isNarrow ? (mobileNavOpen ? '✕' : '☰') : (sidebarHidden ? '☰' : '‹‹')}
        </button>
        <div className="topbar__title">
          {loc.pathname === '/' ? t('Genel Bakış')
            : loc.pathname === '/settings' ? t('Ayarlar')
            : loc.pathname === '/intelligence' ? t('İstihbarat')
            : loc.pathname === '/trend' ? t('Rejim Haritası')
            : `${t(STRAT_LABEL[strategy] || 'Main')} · ${t(MODE_LABEL[mode] || 'Live')}`}
        </div>
        <KillzoneClock />
        <button
          type="button"
          className={`kz-pill${usSignalsActive() ? ' kz-pill--active' : ''}`}
          onClick={() => setSessOpen(true)}
          title={t('Seans Durumu (Kripto / ABD Hisse / Metaller)')}
          style={{ cursor: 'pointer' }}
        >
          <span className={`kz-dot${usSignalsActive() ? ' kz-dot--on' : ''}`} />
          🕑 {t('Seanslar')}
        </button>
      </div>
      {sessOpen && <SessionInfo onClose={() => setSessOpen(false)} />}

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
                {/* Quick-selects: market category + best/worst — one click applies. */}
                <div
                  className="symbol-quickrow"
                  onClick={(e) => e.stopPropagation()}
                  style={{ display: 'flex', flexWrap: 'wrap', gap: 4, padding: '4px 2px 6px' }}
                >
                  {MARKETS.map((mk) => (
                    <button
                      key={mk.key} className="apply-btn ghost" onClick={() => applyMarket(mk.key)}
                      title={t('Sadece bu piyasayı seç')}
                      style={{ flex: '0 0 auto', padding: '3px 8px', fontSize: 11 }}
                    >
                      {t(mk.label)}
                    </button>
                  ))}
                  {hasPerf && (
                    <>
                      <button
                        className="apply-btn ghost" onClick={applyBest}
                        title={t('Backtest R’ye göre en iyi 5 sembol')}
                        style={{ flex: '0 0 auto', padding: '3px 8px', fontSize: 11 }}
                      >
                        🏆 {t('En İyi')} {TOP_N}
                      </button>
                      <button
                        className="apply-btn ghost" onClick={applyWorst}
                        title={t('Backtest R’ye göre en kötü 5 sembol')}
                        style={{ flex: '0 0 auto', padding: '3px 8px', fontSize: 11 }}
                      >
                        🔻 {t('En Kötü')} {TOP_N}
                      </button>
                    </>
                  )}
                </div>
                <div className="symbol-list" onClick={(e) => e.stopPropagation()}>
                  {filteredSymbols.length === 0 && <div className="symbol-empty">{t('Sonuç yok')}</div>}
                  {filteredSymbols.map((sym) => {
                    const badge = strategyBadge(strategy, sym, KARMA_MAP);
                    const r = symbolPerf?.[sym];
                    return (
                      <label key={sym} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <input type="checkbox" checked={pendingSymbols.has(sym)} onChange={() => toggleSymbol(sym)} />
                        <span style={{ flex: 1 }}>{sym}</span>
                        {badge && (
                          <span style={{ fontSize: 10, opacity: 0.7, fontVariant: 'all-small-caps', letterSpacing: 0.3 }}>{badge}</span>
                        )}
                        {hasPerf && r && r.closed > 0 && (
                          <span
                            className={r.totalR >= 0 ? 'win' : 'loss'}
                            style={{ fontSize: 10, minWidth: 38, textAlign: 'right' }}
                          >
                            {r.totalR >= 0 ? '+' : ''}{r.totalR.toFixed(1)}R
                          </span>
                        )}
                      </label>
                    );
                  })}
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
