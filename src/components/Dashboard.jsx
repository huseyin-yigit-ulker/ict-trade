import { useEffect, useMemo, useState } from 'react';
import { useTradeContext } from '../context/TradeContext';

const Dashboard = () => {
  const {
    filteredSignals,
    allSignals,
    selectedSymbols,
    setDateStart,
    setDateEnd,
    dateStart,
    dateEnd,
    setActiveSignal,
    setChartView,
    mode,
    liveStatuses
  } = useTradeContext();

  const calculatePnL = (sig) => {
    if (Number.isFinite(sig?.pnlR)) return sig.pnlR;
    if (sig.status !== 'TP' && sig.status !== 'SL') return 0;
    const diff = sig.dir === 'LONG' ? (sig.exitPrice - sig.entry) : (sig.entry - sig.exitPrice);
    return (diff / sig.entry) * 100;
  };

  const formatBacktestPnl = (sig, pnl) => (
    Number.isFinite(sig?.pnlR) ? `${pnl.toFixed(2)}R` : `${pnl.toFixed(2)}%`
  );

  const resolveLiveMeta = (status) => {
    if (!status) return { label: 'BEKLEMEDE', cls: 'waiting', terminal: false };
    if (status === 'TP Oldu') return { label: 'TP', cls: 'win', terminal: true };
    if (status === 'SL Oldu') return { label: 'SL', cls: 'loss', terminal: true };
    if (status === 'TP/SL Aynı Mum') return { label: 'TP/SL', cls: 'loss', terminal: true };
    if (status.startsWith('İptal')) return { label: 'İPTAL', cls: 'waiting', terminal: true };
    if (status.startsWith('İşlem Aktif')) return { label: 'AKTIF', cls: 'waiting', terminal: false };
    return { label: 'BEKLEMEDE', cls: 'waiting', terminal: false };
  };

  const formatLiveDelta = (sig, lastPrice) => {
    if (!sig?.entry || typeof lastPrice !== 'number') return '--';
    const diff = sig.dir === 'LONG' ? (lastPrice - sig.entry) : (sig.entry - lastPrice);
    const pct = (diff / sig.entry) * 100;
    return `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`;
  };

  const formatLivePrice = (value) => (
    typeof value === 'number' ? value.toFixed(5) : '--'
  );

  const getLiveRLabel = (status) => {
    if (!status) return { label: '--', cls: 'waiting' };
    if (status === 'TP Oldu') return { label: '2R', cls: 'win' };
    if (status === 'SL Oldu' || status === 'TP/SL Aynı Mum') return { label: '-R', cls: 'loss' };
    if (status.startsWith('İptal')) return { label: '0', cls: 'waiting' };
    return { label: '--', cls: 'waiting' };
  };

  const summarizeLiveCounts = (list) => {
    let tp = 0;
    let sl = 0;
    list.forEach((sig) => {
      const status = liveStatuses[sig.id]?.status;
      const meta = resolveLiveMeta(status);
      if (meta.label === 'TP') tp += 1;
      else if (meta.label === 'SL' || meta.label === 'TP/SL') sl += 1;
    });
    const rScore = (2 * tp) - sl;
    return { tp, sl, rScore };
  };

  const summarizeBacktestCounts = (list) => {
    let tp = 0;
    let sl = 0;
    list.forEach((sig) => {
      if (sig.status === 'TP') tp += 1;
      else if (sig.status === 'SL') sl += 1;
    });
    const rScore = (2 * tp) - sl;
    return { tp, sl, rScore };
  };

  const grouped = useMemo(() => {
    return filteredSignals.reduce((acc, sig) => {
      const dateKey = sig.dateObj.toLocaleDateString('tr-TR', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' });
      if (!acc[dateKey]) acc[dateKey] = [];
      acc[dateKey].push(sig);
      return acc;
    }, {});
  }, [filteredSignals]);

  const dayChips = useMemo(() => {
    if (mode !== 'backtest') return [];
    const scoped = allSignals.filter((s) => selectedSymbols.has(s.symbol));
    const byDay = scoped.reduce((acc, sig) => {
      const iso = sig.dateObj.toISOString().slice(0, 10);
      if (!acc[iso]) acc[iso] = [];
      acc[iso].push(sig);
      return acc;
    }, {});

    return Object.entries(byDay)
      .map(([iso, list]) => {
        const tp = list.filter((s) => s.status === 'TP').length;
        const sl = list.filter((s) => s.status === 'SL').length;
        const rTotal = list.reduce((sum, s) => {
          if (Number.isFinite(s?.pnlR)) return sum + s.pnlR;
          return sum + calculatePnL(s);
        }, 0);
        return {
          iso,
          list,
          tp,
          sl,
          rTotal,
          label: new Date(`${iso}T00:00:00`).toLocaleDateString('tr-TR', {
            day: '2-digit',
            month: 'short',
            weekday: 'short'
          })
        };
      })
      .sort((a, b) => b.iso.localeCompare(a.iso));
  }, [mode, allSignals, selectedSymbols]);

  const isSingleDayFilter = Boolean(dateStart && dateEnd && dateStart === dateEnd);
  const activeDayIso = isSingleDayFilter ? dateStart : '';
  const monthOptions = useMemo(() => {
    const monthSet = new Set(dayChips.map((d) => d.iso.slice(0, 7)));
    return [...monthSet].sort((a, b) => b.localeCompare(a));
  }, [dayChips]);
  const [selectedMonth, setSelectedMonth] = useState('');

  useEffect(() => {
    if (mode !== 'backtest') return;
    if (monthOptions.length === 0) {
      setSelectedMonth('');
      return;
    }
    if (!selectedMonth || !monthOptions.includes(selectedMonth)) {
      setSelectedMonth(monthOptions[0]);
    }
  }, [mode, monthOptions, selectedMonth]);

  const selectedMonthIndex = monthOptions.indexOf(selectedMonth);
  const visibleDayChips = selectedMonth
    ? dayChips.filter((d) => d.iso.startsWith(selectedMonth))
    : dayChips;
  const selectedMonthLabel = selectedMonth
    ? new Date(`${selectedMonth}-01T00:00:00`).toLocaleDateString('tr-TR', { month: 'long', year: 'numeric' })
    : 'Tüm Aylar';

  return (
    <div id="dashboard" className="visible" style={{ opacity: 1, display: 'block' }}>
      {mode === 'backtest' && (
        <>
          <div className="day-strip-head">
            <button
              className="month-nav-btn"
              disabled={selectedMonthIndex < 0 || selectedMonthIndex >= monthOptions.length - 1}
              onClick={() => {
                if (selectedMonthIndex < 0 || selectedMonthIndex >= monthOptions.length - 1) return;
                setSelectedMonth(monthOptions[selectedMonthIndex + 1]);
              }}
            >
              ‹
            </button>
            <div className="month-nav-title">{selectedMonthLabel}</div>
            <button
              className="month-nav-btn"
              disabled={selectedMonthIndex <= 0}
              onClick={() => {
                if (selectedMonthIndex <= 0) return;
                setSelectedMonth(monthOptions[selectedMonthIndex - 1]);
              }}
            >
              ›
            </button>
          </div>

          <div className="day-strip">
          <button
            className={`day-pill all ${!dateStart && !dateEnd ? 'active' : ''}`}
            onClick={() => {
              setDateStart('');
              setDateEnd('');
            }}
          >
            <div className="day-pill-title">Tümü</div>
            <div className="day-pill-meta">{visibleDayChips.length} gün</div>
          </button>

          {visibleDayChips.map((d) => (
            <button
              key={d.iso}
              className={`day-pill ${activeDayIso === d.iso ? 'active' : ''}`}
              onClick={() => {
                if (activeDayIso === d.iso) {
                  setDateStart('');
                  setDateEnd('');
                } else {
                  setDateStart(d.iso);
                  setDateEnd(d.iso);
                }
              }}
            >
              <div className="day-pill-title">{d.label}</div>
              <div className="day-pill-meta">{d.list.length} işlem</div>
              <div className="day-pill-meta">
                TP/SL: <span className="win">{d.tp}</span>/<span className="loss">{d.sl}</span> •{' '}
                <span className={d.rTotal >= 0 ? 'win' : 'loss'}>{d.rTotal >= 0 ? '+' : ''}{d.rTotal.toFixed(2)}R</span>
              </div>
            </button>
          ))}
          </div>
        </>
      )}

      {Object.keys(grouped).map(dateKey => {
        const trades = grouped[dateKey];
        const counts = mode === 'live' ? summarizeLiveCounts(trades) : summarizeBacktestCounts(trades);

        return (
          <div key={dateKey} className="day-notebook">
            <div className="day-header">
              <div className="day-title">{dateKey}</div>
              <div className="day-summary">
                <span>{trades.length} işlem</span>
                <span className="tp-sl-ratio">
                  TP/SL: {counts.tp}/{counts.sl} • R:{' '}
                  <span className={counts.rScore >= 0 ? 'win' : 'loss'}>
                    {counts.rScore >= 0 ? '+' : ''}{counts.rScore}
                  </span>
                </span>
              </div>
            </div>

            <div className="trade-grid">
              {trades.map(sig => {
                const pnl = calculatePnL(sig);
                const liveStatus = mode === 'live' ? liveStatuses[sig.id]?.status : '';
                const liveLastPrice = mode === 'live' ? liveStatuses[sig.id]?.lastPrice : null;
                const liveMeta = resolveLiveMeta(liveStatus);
                const pnlClass = mode === 'live'
                  ? liveMeta.cls
                  : (pnl > 0 ? 'win' : (pnl < 0 ? 'loss' : 'waiting'));
                const timeLabel = sig.dateObj.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });

                return (
                  <div
                    key={sig.id}
                    className="trade-card"
                    onClick={() => {
                      setChartView('journal');
                      setActiveSignal(sig);
                    }}
                  >
                    <div className="trade-head">
                      <span className="symbol-box">{sig.symbol}</span>
                      <span className={`dir-badge ${sig.dir.toLowerCase()}`}>{sig.dir}</span>
                      <span className="time-detail">{timeLabel}</span>
                    </div>
                    <div className="trade-body">
                      <div className="trade-metric">
                        <span className="metric-label">Durum</span>
                        <span className={`status-text ${pnlClass}`}>
                          {mode === 'live' ? (liveStatus || 'Beklemede') : sig.status}
                        </span>
                      </div>
                      <div className="trade-metric">
                        <span className="metric-label">P/L</span>
                        {mode === 'live' ? (
                          liveMeta.label === 'AKTIF' ? (
                            <span className="pnl-text live-pnl-stack">
                              <span className="live-price">{formatLivePrice(liveLastPrice)}</span>
                              <span className={formatLiveDelta(sig, liveLastPrice).startsWith('-') ? 'loss' : 'win'}>
                                {formatLiveDelta(sig, liveLastPrice)}
                              </span>
                            </span>
                          ) : (
                            <span className={`pnl-text ${getLiveRLabel(liveStatus).cls}`}>
                              {getLiveRLabel(liveStatus).label}
                            </span>
                          )
                        ) : (
                          <span className={`pnl-text ${pnlClass}`}>{pnl !== 0 ? formatBacktestPnl(sig, pnl) : '--'}</span>
                        )}
                      </div>
                      <div className="trade-metric">
                        <span className="metric-label">Entry</span>
                        <span className="metric-value">{sig.entry?.toFixed(4)}</span>
                      </div>
                      <div className="trade-metric">
                        <span className="metric-label">TP/SL</span>
                        <span className="metric-value">{sig.tp?.toFixed(4)} / {sig.sl?.toFixed(4)}</span>
                      </div>
                    </div>
                    <div className="trade-foot">
                      <div className={`chip ${pnlClass}`}>{mode === 'live' ? liveMeta.label : (pnlClass === 'waiting' ? 'BEKLEMEDE' : (pnl > 0 ? 'TP' : 'SL'))}</div>
                    </div>
                    <button
                      className="live-graph-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        setChartView('tv');
                        setActiveSignal(sig);
                      }}
                    >
                      Live <span className="live-graph-dot">•</span>
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default Dashboard;
