import { useEffect, useMemo, useState } from 'react';
import { useTradeContext } from '../context/TradeContext';
import { useLang } from '../context/LanguageContext';
import EquityCurvePanel from './viz/EquityCurvePanel';

const SummaryModal = ({ asPage = false }) => {
  const { allSignals, selectedSymbols, setShowSummary, mode, liveStatuses, backtestInsights } = useTradeContext();
  const { t } = useLang();
  const [localSymbols, setLocalSymbols] = useState(new Set(selectedSymbols));
  const [filterOpen, setFilterOpen] = useState(false);
  const [statusFilterOpen, setStatusFilterOpen] = useState(false);
  const [statusFilters, setStatusFilters] = useState(new Set(['TP', 'SL', 'AKTIF', 'BEKLEMEDE', 'IPTAL']));

  const calculatePnL = (sig) => {
    if (Number.isFinite(sig?.pnlR)) return sig.pnlR;
    if (sig.status !== 'TP' && sig.status !== 'SL') return 0;
    const diff = sig.dir === 'LONG' ? (sig.exitPrice - sig.entry) : (sig.entry - sig.exitPrice);
    return (diff / sig.entry) * 100;
  };

  const uniqueSymbols = useMemo(
    () => [...new Set(allSignals.map(s => s.symbol))].sort(),
    [allSignals]
  );

  useEffect(() => {
    if (mode === 'live') {
      setStatusFilters(new Set(['TP', 'SL', 'AKTIF', 'BEKLEMEDE', 'IPTAL']));
    }
  }, [mode]);

  // Mirror the global symbol selection. Without this, mounting before the data
  // load finishes (e.g. deep-linking straight to /intelligence) froze an empty
  // initial set and the whole panel stayed blank.
  useEffect(() => {
    setLocalSymbols(new Set(selectedSymbols));
  }, [selectedSymbols]);

  // Modal variant advertises an ESC pill on its close button — honour it.
  useEffect(() => {
    if (asPage) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') setShowSummary(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [asPage, setShowSummary]);

  const resolveLiveType = (status) => {
    if (!status) return 'BEKLEMEDE';
    if (status === 'TP Oldu') return 'TP';
    if (status === 'SL Oldu') return 'SL';
    if (status === 'TP/SL Aynı Mum') return 'SL';
    if (status.startsWith('İptal')) return 'IPTAL';
    if (status.startsWith('İşlem Aktif')) return 'AKTIF';
    return 'BEKLEMEDE';
  };

  const filtered = allSignals.filter(s => s.status !== 'NOFILL' && localSymbols.has(s.symbol)).filter(s => {
    if (mode !== 'live') return true;
    const status = liveStatuses[s.id]?.status;
    const type = resolveLiveType(status);
    return statusFilters.has(type);
  });
  const hasDbPnl = filtered.some(s => Number.isFinite(s?.pnlR));
  const now = Date.now();
  const dayMs = 24 * 60 * 60 * 1000;

  const sliceByDays = (days) => filtered.filter(s => (now - s.dateObj.getTime()) <= days * dayMs);

  const summarize = (list) => {
    const count = list.length;
    const wins = list.filter(s => s.status === 'TP').length;
    const pnlSum = list.reduce((sum, s) => sum + calculatePnL(s), 0);
    const winRate = count > 0 ? (wins / count) * 100 : 0;
    const avgPnl = count > 0 ? pnlSum / count : 0;
    return { count, wins, pnlSum, winRate, avgPnl };
  };

  const summarizeLive = (list) => {
    let tp = 0;
    let sl = 0;
    let aktif = 0;
    let beklemede = 0;
    let iptal = 0;
    list.forEach((s) => {
      const type = resolveLiveType(liveStatuses[s.id]?.status);
      if (type === 'TP') tp += 1;
      else if (type === 'SL') sl += 1;
      else if (type === 'AKTIF') aktif += 1;
      else if (type === 'IPTAL') iptal += 1;
      else beklemede += 1;
    });
    const count = list.length;
    const denom = tp + sl;
    const successRate = denom > 0 ? (tp / denom) * 100 : 0;
    return { count, tp, sl, aktif, beklemede, iptal, successRate };
  };

  const daily = mode === 'live' ? summarizeLive(sliceByDays(1)) : summarize(sliceByDays(1));
  const weekly = mode === 'live' ? summarizeLive(sliceByDays(7)) : summarize(sliceByDays(7));
  const monthly = mode === 'live' ? summarizeLive(sliceByDays(30)) : summarize(sliceByDays(30));
  const yearly = mode === 'live' ? summarizeLive(sliceByDays(365)) : summarize(sliceByDays(365));

  const cards = [
    { title: 'Günlük', data: daily },
    { title: 'Haftalık', data: weekly },
    { title: 'Aylık', data: monthly },
    { title: 'Yıllık', data: yearly }
  ];

  const overall = mode === 'live' ? summarizeLive(filtered) : summarize(filtered);
  const bySymbol = filtered.reduce((acc, s) => {
    if (!acc[s.symbol]) acc[s.symbol] = { count: 0, wins: 0, pnl: 0 };
    acc[s.symbol].count++;
    acc[s.symbol].wins += s.status === 'TP' ? 1 : 0;
    acc[s.symbol].pnl += calculatePnL(s);
    return acc;
  }, {});
  const topSymbols = Object.entries(bySymbol)
    .map(([sym, data]) => ({
      sym,
      count: data.count,
      winRate: data.count ? (data.wins / data.count) * 100 : 0,
      pnl: data.pnl
    }))
    .sort((a, b) => b.pnl - a.pnl)
    .slice(0, 5);
  const sqlSummary = backtestInsights?.summary;
  const sqlSymbols = Array.isArray(backtestInsights?.symbols) ? backtestInsights.symbols.slice(0, 5) : [];
  const sqlWeekdays = Array.isArray(backtestInsights?.weekdays) ? backtestInsights.weekdays.slice(0, 7) : [];
  const sqlSessions = Array.isArray(backtestInsights?.sessions) ? backtestInsights.sessions.slice(0, 4) : [];

  // `filtered` is DESC by dateObj — equity needs ASC so the curve runs left→right.
  const curveSignals = mode === 'backtest'
    ? [...filtered].sort((a, b) => a.dateObj - b.dateObj)
    : [];

  // Per-TRADE biggest winners (not per-symbol) + how much of all profit the top 5 carry.
  const winnerStats = (() => {
    const pos = filtered
      .map((s) => ({ s, r: calculatePnL(s) }))
      .filter((x) => Number.isFinite(x.r) && x.r > 0)
      .sort((a, b) => b.r - a.r);
    const top5 = pos.slice(0, 5);
    const totalPos = pos.reduce((sum, x) => sum + x.r, 0);
    const top5Sum = top5.reduce((sum, x) => sum + x.r, 0);
    return { top5, share: totalPos > 0 ? (top5Sum / totalPos) * 100 : 0, topR: top5[0]?.r || 1 };
  })();

  return (
    <div id="summary-modal" className={asPage ? 'summary-page' : 'summary-screen'} style={asPage ? undefined : { display: 'block' }}>
      <div className="summary-hero">
        <div>
          <div className="summary-kicker">PUSU</div>
          <h2>{t('Başarı Paneli')}</h2>
          <p>{t('Günlük, haftalık, aylık ve yıllık performans analizi.')}</p>
        </div>
        <div className="summary-actions">
          <button className="date-picker-btn" onClick={() => setFilterOpen(!filterOpen)}>
            {t('Sembol Filtre')}
          </button>
          {mode === 'live' && (
            <button className="date-picker-btn" onClick={() => setStatusFilterOpen(!statusFilterOpen)}>
              {t('Durum Filtre')}
            </button>
          )}
          {filterOpen && (
            <div className="summary-filter">
              <div className="summary-filter-list">
                {uniqueSymbols.map(sym => (
                  <label key={sym}>
                    <input
                      type="checkbox"
                      checked={localSymbols.has(sym)}
                      onChange={() => {
                        const next = new Set(localSymbols);
                        if (next.has(sym)) next.delete(sym);
                        else next.add(sym);
                        setLocalSymbols(next);
                      }}
                    />
                    {sym}
                  </label>
                ))}
              </div>
              <div className="date-actions">
                <button
                  className="apply-btn"
                  onClick={() => setLocalSymbols(new Set(uniqueSymbols))}
                >
                  {t('Tümü')}
                </button>
                <button
                  className="apply-btn ghost"
                  onClick={() => setLocalSymbols(new Set())}
                >
                  {t('Temizle')}
                </button>
              </div>
            </div>
          )}
          {mode === 'live' && statusFilterOpen && (
            <div className="summary-filter">
              <div className="summary-filter-list">
                {['TP', 'SL', 'AKTIF', 'BEKLEMEDE', 'IPTAL'].map(status => (
                  <label key={status}>
                    <input
                      type="checkbox"
                      checked={statusFilters.has(status)}
                      onChange={() => {
                        const next = new Set(statusFilters);
                        if (next.has(status)) next.delete(status);
                        else next.add(status);
                        setStatusFilters(next);
                      }}
                    />
                    {t(status)}
                  </label>
                ))}
              </div>
              <div className="date-actions">
                <button
                  className="apply-btn"
                  onClick={() => setStatusFilters(new Set(['TP', 'SL', 'AKTIF', 'BEKLEMEDE', 'IPTAL']))}
                >
                  {t('Tümü')}
                </button>
                <button
                  className="apply-btn ghost"
                  onClick={() => setStatusFilters(new Set())}
                >
                  {t('Temizle')}
                </button>
              </div>
            </div>
          )}
          {!asPage && (
            <button className="close-modern" onClick={() => setShowSummary(false)}>
              <span className="close-label">{t('Kapat')}</span>
              <span className="esc-pill">ESC</span>
            </button>
          )}
        </div>
      </div>

      {mode === 'backtest' && curveSignals.length >= 2 && (
        <div className="summary-overview">
          <EquityCurvePanel
            signals={curveSignals}
            calculatePnL={calculatePnL}
            profitFactor={sqlSummary?.profit_factor}
          />
        </div>
      )}

      {mode === 'backtest' && (sqlSummary || winnerStats.top5.length > 0) && (
        <div className="summary-overview">
          <div className="overview-card asym-card">
            <div className="summary-title">{t('Asimetri')}</div>
            <div className="asym-headline">{t('DÜŞÜK İSABET · YÜKSEK GETİRİ')}</div>
            <div className="summary-metric">
              <span>{t('Kazanç (Win Rate)')}</span>
              <b className={Number(sqlSummary?.win_rate || 0) >= 50 ? 'win' : 'loss'}>
                {Number(sqlSummary?.win_rate || 0).toFixed(1)}%
              </b>
            </div>
            <div className="summary-metric">
              <span>{t('Beklenti')}</span>
              <b className={Number(sqlSummary?.expectancy_r || 0) >= 0 ? 'win' : 'loss'}>
                {Number(sqlSummary?.expectancy_r || 0) >= 0 ? '+' : ''}{Number(sqlSummary?.expectancy_r || 0).toFixed(2)}R
              </b>
            </div>
            <div className="asym-bar">
              <div className="asym-bar__fill" style={{ width: `${Math.min(100, winnerStats.share)}%` }} />
            </div>
            <div className="asym-note">
              {t("En iyi 5 işlem toplam brüt kârın %{share}'ini taşıyor — az kazanır, büyük kazanır; sistem böyle tasarlandı.", { share: winnerStats.share.toFixed(0) })}
            </div>
          </div>

          <div className="overview-card">
            <div className="summary-title">{t('En Büyük Kazançlar')}</div>
            {winnerStats.top5.length === 0 && <div className="summary-empty">{t('Kayıt yok')}</div>}
            <div className="big-win-list">
              {winnerStats.top5.map((w, i) => (
                <div key={w.s.id} className="big-win-row">
                  <span className="big-win-rank">{i === 0 ? '⭐' : i + 1}</span>
                  <span className="symbol-box">{w.s.symbol}</span>
                  <span className={`big-win-dir ${w.s.dir === 'LONG' ? 'win' : 'loss'}`}>
                    {w.s.dir === 'LONG' ? '↗' : '↘'}
                  </span>
                  <span className="big-win-date">
                    {w.s.dateObj.toLocaleDateString('tr-TR', { day: '2-digit', month: 'short' })}
                  </span>
                  <span className="big-win-bar">
                    <span className="big-win-bar__fill" style={{ width: `${(w.r / winnerStats.topR) * 100}%` }} />
                  </span>
                  <b className="big-win-r">+{w.r.toFixed(1)}R</b>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="summary-overview">
        <div className="overview-card">
          <div className="summary-title">{t('Genel Özet')}</div>
          <div className="summary-metric">
            <span>{t('Toplam İşlem')}</span>
            <b>{overall.count}</b>
          </div>
          {mode === 'live' ? (
            <>
              <div className="summary-metric">
                <span>{t('Başarı')}</span>
                <b className={overall.successRate >= 50 ? 'win' : 'loss'}>{overall.successRate.toFixed(1)}%</b>
              </div>
              <div className="summary-metric">
                <span>{t('TP / SL')}</span>
                <b><span className="win">{overall.tp}</span> / <span className="loss">{overall.sl}</span></b>
              </div>
              <div className="summary-metric">
                <span>{t('Aktif / İptal')}</span>
                <b>{overall.aktif} / {overall.iptal}</b>
              </div>
            </>
          ) : (
            <>
              <div className="summary-metric">
                <span>{t('Win Rate')}</span>
                <b className={overall.winRate >= 50 ? 'win' : 'loss'}>{overall.winRate.toFixed(1)}%</b>
              </div>
              <div className="summary-metric">
                <span>{t('Toplam PnL')}</span>
                <b className={overall.pnlSum >= 0 ? 'win' : 'loss'}>{overall.pnlSum.toFixed(2)}{hasDbPnl ? 'R' : '%'}</b>
              </div>
              <div className="summary-metric">
                <span>{t('Ortalama PnL')}</span>
                <b className={overall.avgPnl >= 0 ? 'win' : 'loss'}>{overall.avgPnl.toFixed(2)}{hasDbPnl ? 'R' : '%'}</b>
              </div>
            </>
          )}
        </div>
        <div className="overview-card">
          <div className="summary-title">{t('En İyi Semboller')}</div>
          {topSymbols.length === 0 && <div className="summary-empty">{t('Kayıt yok')}</div>}
          {topSymbols.map(item => (
            <div key={item.sym} className="summary-metric">
              <span>{item.sym}</span>
              <b className={item.pnl >= 0 ? 'win' : 'loss'}>{item.pnl.toFixed(2)}{hasDbPnl ? 'R' : '%'}</b>
            </div>
          ))}
        </div>
      </div>

      <div className="summary-metrics">
        {cards.map((c) => (
          <div key={c.title} className="summary-card modern">
            <div className="summary-title">{t(c.title)}</div>
            <div className="summary-metric">
              <span>{t('İşlem')}</span>
              <b>{c.data.count}</b>
            </div>
            {mode === 'live' ? (
              <>
                <div className="summary-metric">
                  <span>{t('Başarı')}</span>
                  <b className={c.data.successRate >= 50 ? 'win' : 'loss'}>{c.data.successRate.toFixed(1)}%</b>
                </div>
                <div className="summary-metric">
                  <span>{t('TP / SL')}</span>
                  <b><span className="win">{c.data.tp}</span> / <span className="loss">{c.data.sl}</span></b>
                </div>
                <div className="summary-metric">
                  <span>{t('Aktif / İptal')}</span>
                  <b>{c.data.aktif} / {c.data.iptal}</b>
                </div>
              </>
            ) : (
              <>
                <div className="summary-metric">
                  <span>{t('Win Rate')}</span>
                  <b className={c.data.winRate >= 50 ? 'win' : 'loss'}>{c.data.winRate.toFixed(1)}%</b>
                </div>
                <div className="summary-metric">
                  <span>{t('Toplam PnL')}</span>
                  <b className={c.data.pnlSum >= 0 ? 'win' : 'loss'}>{c.data.pnlSum.toFixed(2)}{hasDbPnl ? 'R' : '%'}</b>
                </div>
                <div className="summary-metric">
                  <span>{t('Ortalama PnL')}</span>
                  <b className={c.data.avgPnl >= 0 ? 'win' : 'loss'}>{c.data.avgPnl.toFixed(2)}{hasDbPnl ? 'R' : '%'}</b>
                </div>
              </>
            )}
          </div>
        ))}
      </div>

      {mode === 'backtest' && sqlSummary && (
        <div className="summary-overview">
          <div className="overview-card">
            <div className="summary-title">{t('SQL Analiz Özeti')}</div>
            <div className="summary-metric">
              <span>{t('Profit Factor')}</span>
              <b>{Number(sqlSummary.profit_factor || 0).toFixed(2)}</b>
            </div>
            <div className="summary-metric">
              <span>{t('Expectancy')}</span>
              <b className={Number(sqlSummary.expectancy_r || 0) >= 0 ? 'win' : 'loss'}>
                {Number(sqlSummary.expectancy_r || 0).toFixed(2)}R
              </b>
            </div>
            <div className="summary-metric">
              <span>{t('Ortalama Süre')}</span>
              <b>{Number(sqlSummary.avg_minutes || 0).toFixed(1)}{t(' dk')}</b>
            </div>
            <div className="summary-metric">
              <span>{t('TP / SL / Cancel')}</span>
              <b>
                <span className="win">{sqlSummary.tp_count || 0}</span> / <span className="loss">{sqlSummary.sl_count || 0}</span> / {sqlSummary.cancelled_count || 0}
              </b>
            </div>
          </div>

          <div className="overview-card">
            <div className="summary-title">{t('SQL Sembol Analizi')}</div>
            {sqlSymbols.length === 0 && <div className="summary-empty">{t('Kayıt yok')}</div>}
            {sqlSymbols.map((row) => (
              <div key={row.symbol} className="summary-metric">
                <span>{row.symbol} ({row.total_trades})</span>
                <b className={Number(row.total_r || 0) >= 0 ? 'win' : 'loss'}>{Number(row.total_r || 0).toFixed(2)}R</b>
              </div>
            ))}
          </div>

          <div className="overview-card">
            <div className="summary-title">{t('SQL Zaman Analizi')}</div>
            {sqlWeekdays.map((row) => (
              <div key={row.weekday_name} className="summary-metric">
                <span>{t(row.weekday_name)}</span>
                <b className={Number(row.total_r || 0) >= 0 ? 'win' : 'loss'}>{Number(row.total_r || 0).toFixed(2)}R</b>
              </div>
            ))}
            {sqlSessions.map((row) => (
              <div key={row.session_name} className="summary-metric">
                <span>{t(row.session_name)}</span>
                <b className={Number(row.total_r || 0) >= 0 ? 'win' : 'loss'}>{Number(row.total_r || 0).toFixed(2)}R</b>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default SummaryModal;
