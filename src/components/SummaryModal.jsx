import { useEffect, useMemo, useState } from 'react';
import { useTradeContext } from '../context/TradeContext';

const SummaryModal = () => {
  const { allSignals, selectedSymbols, setShowSummary, mode, liveStatuses } = useTradeContext();
  const [localSymbols, setLocalSymbols] = useState(new Set(selectedSymbols));
  const [filterOpen, setFilterOpen] = useState(false);
  const [statusFilterOpen, setStatusFilterOpen] = useState(false);
  const [statusFilters, setStatusFilters] = useState(new Set(['TP', 'SL', 'AKTIF', 'BEKLEMEDE', 'IPTAL']));

  const calculatePnL = (sig) => {
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

  const resolveLiveType = (status) => {
    if (!status) return 'BEKLEMEDE';
    if (status === 'TP Oldu') return 'TP';
    if (status === 'SL Oldu') return 'SL';
    if (status === 'TP/SL Aynı Mum') return 'SL';
    if (status.startsWith('İptal')) return 'IPTAL';
    if (status.startsWith('İşlem Aktif')) return 'AKTIF';
    return 'BEKLEMEDE';
  };

  const filtered = allSignals.filter(s => localSymbols.has(s.symbol)).filter(s => {
    if (mode !== 'live') return true;
    const status = liveStatuses[s.id]?.status;
    const type = resolveLiveType(status);
    return statusFilters.has(type);
  });
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

  return (
    <div id="summary-modal" className="summary-screen" style={{ display: 'block' }}>
      <div className="summary-hero">
        <div>
          <div className="summary-kicker">ICT TRADE BOT</div>
          <h2>Başarı Paneli</h2>
          <p>Günlük, haftalık, aylık ve yıllık performans analizi.</p>
        </div>
        <div className="summary-actions">
          <button className="date-picker-btn" onClick={() => setFilterOpen(!filterOpen)}>
            Sembol Filtre
          </button>
          {mode === 'live' && (
            <button className="date-picker-btn" onClick={() => setStatusFilterOpen(!statusFilterOpen)}>
              Durum Filtre
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
                  Tümü
                </button>
                <button
                  className="apply-btn ghost"
                  onClick={() => setLocalSymbols(new Set())}
                >
                  Temizle
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
                    {status}
                  </label>
                ))}
              </div>
              <div className="date-actions">
                <button
                  className="apply-btn"
                  onClick={() => setStatusFilters(new Set(['TP', 'SL', 'AKTIF', 'BEKLEMEDE', 'IPTAL']))}
                >
                  Tümü
                </button>
                <button
                  className="apply-btn ghost"
                  onClick={() => setStatusFilters(new Set())}
                >
                  Temizle
                </button>
              </div>
            </div>
          )}
          <button className="close-modern" onClick={() => setShowSummary(false)}>
            <span className="close-label">Kapat</span>
            <span className="esc-pill">ESC</span>
          </button>
        </div>
      </div>

      <div className="summary-overview">
        <div className="overview-card">
          <div className="summary-title">Genel Özet</div>
          <div className="summary-metric">
            <span>Toplam İşlem</span>
            <b>{overall.count}</b>
          </div>
          {mode === 'live' ? (
            <>
              <div className="summary-metric">
                <span>Başarı</span>
                <b className={overall.successRate >= 50 ? 'win' : 'loss'}>{overall.successRate.toFixed(1)}%</b>
              </div>
              <div className="summary-metric">
                <span>TP / SL</span>
                <b><span className="win">{overall.tp}</span> / <span className="loss">{overall.sl}</span></b>
              </div>
              <div className="summary-metric">
                <span>Aktif / İptal</span>
                <b>{overall.aktif} / {overall.iptal}</b>
              </div>
            </>
          ) : (
            <>
              <div className="summary-metric">
                <span>Win Rate</span>
                <b className={overall.winRate >= 50 ? 'win' : 'loss'}>{overall.winRate.toFixed(1)}%</b>
              </div>
              <div className="summary-metric">
                <span>Toplam PnL</span>
                <b className={overall.pnlSum >= 0 ? 'win' : 'loss'}>{overall.pnlSum.toFixed(2)}%</b>
              </div>
              <div className="summary-metric">
                <span>Ortalama PnL</span>
                <b className={overall.avgPnl >= 0 ? 'win' : 'loss'}>{overall.avgPnl.toFixed(2)}%</b>
              </div>
            </>
          )}
        </div>
        <div className="overview-card">
          <div className="summary-title">En İyi Semboller</div>
          {topSymbols.length === 0 && <div className="summary-empty">Kayıt yok</div>}
          {topSymbols.map(item => (
            <div key={item.sym} className="summary-metric">
              <span>{item.sym}</span>
              <b className={item.pnl >= 0 ? 'win' : 'loss'}>{item.pnl.toFixed(2)}%</b>
            </div>
          ))}
        </div>
      </div>

      <div className="summary-metrics">
        {cards.map((c) => (
          <div key={c.title} className="summary-card modern">
            <div className="summary-title">{c.title}</div>
            <div className="summary-metric">
              <span>İşlem</span>
              <b>{c.data.count}</b>
            </div>
            {mode === 'live' ? (
              <>
                <div className="summary-metric">
                  <span>Başarı</span>
                  <b className={c.data.successRate >= 50 ? 'win' : 'loss'}>{c.data.successRate.toFixed(1)}%</b>
                </div>
                <div className="summary-metric">
                  <span>TP / SL</span>
                  <b><span className="win">{c.data.tp}</span> / <span className="loss">{c.data.sl}</span></b>
                </div>
                <div className="summary-metric">
                  <span>Aktif / İptal</span>
                  <b>{c.data.aktif} / {c.data.iptal}</b>
                </div>
              </>
            ) : (
              <>
                <div className="summary-metric">
                  <span>Win Rate</span>
                  <b className={c.data.winRate >= 50 ? 'win' : 'loss'}>{c.data.winRate.toFixed(1)}%</b>
                </div>
                <div className="summary-metric">
                  <span>Toplam PnL</span>
                  <b className={c.data.pnlSum >= 0 ? 'win' : 'loss'}>{c.data.pnlSum.toFixed(2)}%</b>
                </div>
                <div className="summary-metric">
                  <span>Ortalama PnL</span>
                  <b className={c.data.avgPnl >= 0 ? 'win' : 'loss'}>{c.data.avgPnl.toFixed(2)}%</b>
                </div>
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

export default SummaryModal;
