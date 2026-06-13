import { useEffect, useState } from 'react';
import { useTradeContext, KARMA_MAP } from '../context/TradeContext';
import { useLang } from '../context/LanguageContext';
import { MARKETS, marketOf, marketLabel, strategyCellLabel } from '../utils/symbolMeta';

const StatsModal = () => {
  const { allSignals, setShowStats, strategy } = useTradeContext();
  const { t } = useLang();
  // Market (asset-class) filter for the table — 'all' or a MARKETS key.
  const [market, setMarket] = useState('all');

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') setShowStats(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [setShowStats]);

  const calculatePnL = (sig) => {
    if (Number.isFinite(sig?.pnlR)) return sig.pnlR;
    if (sig.status !== 'TP' && sig.status !== 'SL') return 0;
    const diff = sig.dir === 'LONG' ? (sig.exitPrice - sig.entry) : (sig.entry - sig.exitPrice);
    return (diff / sig.entry) * 100;
  };
  const hasDbPnl = allSignals.some(s => Number.isFinite(s?.pnlR));

  const stats = {};
  allSignals.forEach(s => {
    if (s.status === 'NOFILL') return;   // no-fill = no trade taken
    if (!stats[s.symbol]) stats[s.symbol] = { count: 0, wins: 0, pnl: 0 };
    stats[s.symbol].count++;
    const pnl = calculatePnL(s);
    stats[s.symbol].pnl += pnl;
    if (s.status === 'TP') stats[s.symbol].wins++;
  });

  // sorted best→worst, then apply the market filter
  const rows = Object.entries(stats)
    .sort((a, b) => b[1].pnl - a[1].pnl)
    .filter(([sym]) => market === 'all' || marketOf(sym) === market);

  // market breakdown over the (unfiltered) symbol set, for the summary chips
  const marketCounts = MARKETS.reduce((acc, mk) => {
    acc[mk.key] = Object.keys(stats).filter((s) => marketOf(s) === mk.key).length;
    return acc;
  }, {});

  // strategy-cell distribution ("strateji bazında semboller"): how many symbols
  // run under each cell. Only informative when the cell varies (i.e. karma).
  const cellDist = Object.entries(
    Object.keys(stats).reduce((acc, sym) => {
      const cell = strategyCellLabel(strategy, sym, KARMA_MAP);
      acc[cell] = (acc[cell] || 0) + 1;
      return acc;
    }, {})
  ).sort((a, b) => b[1] - a[1]);

  return (
    <div id="stats-modal" className="modal-overlay" style={{ display: 'block' }} onClick={() => setShowStats(false)}>
      <div className="stats-box" onClick={(e) => e.stopPropagation()}>
        <div className="stats-header">
          <h2>{t('PORTFÖY KARNESİ')}</h2>
          <button id="close-stats" onClick={() => setShowStats(false)}>{t('KAPAT')}</button>
        </div>

        {/* Market filter chips: Tümü + each asset class (with symbol counts). */}
        <div className="status-filter" role="group" aria-label="market filter" style={{ margin: '0 0 10px' }}>
          <button
            className={`status-filter__btn ${market === 'all' ? 'active' : ''}`}
            onClick={() => setMarket('all')}
          >
            {t('Tümü')} ({Object.keys(stats).length})
          </button>
          {MARKETS.map((mk) => (
            <button
              key={mk.key}
              className={`status-filter__btn ${market === mk.key ? 'active' : ''}`}
              onClick={() => setMarket(mk.key)}
            >
              {t(mk.label)} ({marketCounts[mk.key] || 0})
            </button>
          ))}
        </div>

        {/* Strategy-cell distribution — only shown when the cell varies (karma). */}
        {cellDist.length > 1 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, margin: '0 0 10px', fontSize: 12, opacity: 0.85 }}>
            <span style={{ opacity: 0.7 }}>{t('Strateji')}:</span>
            {cellDist.map(([cell, n]) => (
              <span key={cell} style={{ fontVariant: 'all-small-caps' }}>{cell} · <b>{n}</b></span>
            ))}
          </div>
        )}

        <div className="stats-content">
          <table className="stats-table">
            <thead>
              <tr>
                <th>{t('Sembol')}</th>
                <th>{t('Piyasa')}</th>
                <th>{t('Strateji')}</th>
                <th>{t('İşlem')}</th>
                <th>{t('Win Rate')}</th>
                <th>{t('Toplam PnL')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(([sym, data]) => {
                const wr = data.count > 0 ? ((data.wins / data.count) * 100).toFixed(0) : 0;
                return (
                  <tr key={sym}>
                    <td><b>{sym}</b></td>
                    <td style={{ opacity: 0.8 }}>{t(marketLabel(sym))}</td>
                    <td style={{ opacity: 0.85, fontVariant: 'all-small-caps' }}>
                      {strategyCellLabel(strategy, sym, KARMA_MAP)}
                    </td>
                    <td>{data.count}</td>
                    <td className={wr >= 50 ? 'win' : 'loss'}>%{wr}</td>
                    <td className={data.pnl >= 0 ? 'win' : 'loss'}>{data.pnl.toFixed(2)}{hasDbPnl ? 'R' : '%'}</td>
                  </tr>
                );
              })}
              {rows.length === 0 && (
                <tr><td colSpan={6} style={{ textAlign: 'center', opacity: 0.6 }}>{t('Sonuç yok')}</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default StatsModal;
