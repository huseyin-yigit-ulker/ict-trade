import { useEffect, useMemo, useState } from 'react';
import { useTradeContext } from '../context/TradeContext';

const Dashboard = () => {
  const {
    filteredSignals,
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

  const formatLivePrice = (value) => (typeof value === 'number' ? value.toFixed(5) : '--');

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
      const meta = resolveLiveMeta(liveStatuses[sig.id]?.status);
      if (meta.label === 'TP') tp += 1;
      else if (meta.label === 'SL' || meta.label === 'TP/SL') sl += 1;
    });
    return { tp, sl, rScore: (2 * tp) - sl };
  };

  const summarizeBacktestCounts = (list) => {
    let tp = 0;
    let sl = 0;
    list.forEach((sig) => {
      if (sig.status === 'TP') tp += 1;
      else if (sig.status === 'SL') sl += 1;
    });
    return { tp, sl, rScore: (2 * tp) - sl };
  };

  const getTotalR = (list) => list.reduce((sum, s) => sum + (Number.isFinite(s?.pnlR) ? s.pnlR : calculatePnL(s)), 0);

  const formatLocalIso = (date) => {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
  };

  const parseIsoDate = (isoString) => {
    const [year, month, day] = isoString.split('-').map(Number);
    return new Date(year, month - 1, day);
  };

  // Live görünümü için mevcut günlük grup
  const groupedLive = useMemo(() => {
    if (mode !== 'live') return {};
    return filteredSignals.reduce((acc, sig) => {
      const dateKey = sig.dateObj.toLocaleDateString('tr-TR', {
        year: 'numeric', month: 'long', day: 'numeric', weekday: 'long'
      });
      if (!acc[dateKey]) acc[dateKey] = [];
      acc[dateKey].push(sig);
      return acc;
    }, {});
  }, [filteredSignals, mode]);

  // Backtest hiyerarşik veri seti
  const backtestSignals = useMemo(() => {
    if (mode !== 'backtest') return [];
    return [...filteredSignals].sort((a, b) => b.dateObj - a.dateObj);
  }, [mode, filteredSignals]);

  const yearBuckets = useMemo(() => {
    const byYear = backtestSignals.reduce((acc, sig) => {
      const year = sig.dateObj.getFullYear();
      if (!acc[year]) acc[year] = [];
      acc[year].push(sig);
      return acc;
    }, {});

    return Object.entries(byYear)
      .map(([year, list]) => {
        const counts = summarizeBacktestCounts(list);
        const totalR = getTotalR(list);
        return {
          year: Number(year),
          list,
          count: list.length,
          tp: counts.tp,
          sl: counts.sl,
          totalR
        };
      })
      .sort((a, b) => b.year - a.year);
  }, [backtestSignals]);

  const [selectedYear, setSelectedYear] = useState(null);
  const [selectedMonth, setSelectedMonth] = useState('');
  const [selectedDay, setSelectedDay] = useState('');

  useEffect(() => {
    if (mode !== 'backtest') {
      setSelectedYear(null);
      setSelectedMonth('');
      setSelectedDay('');
      return;
    }
    if (selectedYear !== null && !yearBuckets.some((y) => y.year === selectedYear)) {
      setSelectedYear(null);
      setSelectedMonth('');
      setSelectedDay('');
    }
  }, [mode, selectedYear, yearBuckets]);

  const monthBuckets = useMemo(() => {
    if (!selectedYear) return [];
    const yearData = yearBuckets.find((y) => y.year === selectedYear);
    const list = yearData?.list || [];

    const byMonth = list.reduce((acc, sig) => {
      const monthKey = `${sig.dateObj.getFullYear()}-${String(sig.dateObj.getMonth() + 1).padStart(2, '0')}`;
      if (!acc[monthKey]) acc[monthKey] = [];
      acc[monthKey].push(sig);
      return acc;
    }, {});

    return Object.entries(byMonth)
      .map(([monthKey, monthList]) => {
        const counts = summarizeBacktestCounts(monthList);
        const totalR = getTotalR(monthList);
        const label = parseIsoDate(`${monthKey}-01`).toLocaleDateString('tr-TR', { month: 'long', year: 'numeric' });
        return {
          monthKey,
          label,
          list: monthList,
          count: monthList.length,
          tp: counts.tp,
          sl: counts.sl,
          totalR
        };
      })
      .sort((a, b) => b.monthKey.localeCompare(a.monthKey));
  }, [selectedYear, yearBuckets]);

  useEffect(() => {
    if (!selectedMonth) return;
    if (!monthBuckets.some((m) => m.monthKey === selectedMonth)) {
      setSelectedMonth('');
      setSelectedDay('');
    }
  }, [selectedMonth, monthBuckets]);

  const dayBuckets = useMemo(() => {
    if (!selectedMonth) return [];
    const monthData = monthBuckets.find((m) => m.monthKey === selectedMonth);
    const list = monthData?.list || [];

    const byDay = list.reduce((acc, sig) => {
      const dayKey = formatLocalIso(sig.dateObj);
      if (!acc[dayKey]) acc[dayKey] = [];
      acc[dayKey].push(sig);
      return acc;
    }, {});

    return Object.entries(byDay)
      .map(([dayKey, dayList]) => {
        const counts = summarizeBacktestCounts(dayList);
        const totalR = getTotalR(dayList);
        const label = parseIsoDate(dayKey).toLocaleDateString('tr-TR', { weekday: 'short', day: '2-digit', month: 'short' });
        return {
          dayKey,
          label,
          list: dayList,
          count: dayList.length,
          tp: counts.tp,
          sl: counts.sl,
          totalR
        };
      })
      .sort((a, b) => b.dayKey.localeCompare(a.dayKey));
  }, [selectedMonth, monthBuckets]);

  useEffect(() => {
    if (!selectedMonth) return;
    if (dayBuckets.length === 0) {
      setSelectedDay('');
      return;
    }
    if (!selectedDay || !dayBuckets.some((d) => d.dayKey === selectedDay)) {
      setSelectedDay(dayBuckets[0].dayKey);
    }
  }, [selectedMonth, selectedDay, dayBuckets]);

  const selectedDayTrades = useMemo(() => {
    if (!selectedDay) return [];
    return dayBuckets.find((d) => d.dayKey === selectedDay)?.list || [];
  }, [selectedDay, dayBuckets]);

  const selectedDayLabel = useMemo(() => {
    if (!selectedDay) return '';
    return parseIsoDate(selectedDay).toLocaleDateString('tr-TR', {
      weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
    });
  }, [selectedDay]);

  const renderTradeCards = (trades) => (
    <div className="trade-grid">
      {trades.map((sig) => {
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
                  <span className={`pnl-text ${pnlClass}`}>
                    {pnl !== 0 ? formatBacktestPnl(sig, pnl) : '--'}
                  </span>
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
              <div className={`chip ${pnlClass}`}>
                {mode === 'live' ? liveMeta.label : (pnlClass === 'waiting' ? 'BEKLEMEDE' : (pnl > 0 ? 'TP' : 'SL'))}
              </div>
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
  );

  if (mode === 'backtest') {
    return (
      <div id="dashboard" className="visible" style={{ opacity: 1, display: 'block' }}>
        <div className="backtest-flow">
          <div className="drill-header">
            <div className="drill-path">
              {!selectedYear && 'Yıllar'}
              {selectedYear && !selectedMonth && `${selectedYear} / Aylar`}
              {selectedYear && selectedMonth && `${selectedYear} / ${parseIsoDate(`${selectedMonth}-01`).toLocaleDateString('tr-TR', { month: 'long' })} / Günler`}
            </div>
            <div className="drill-actions">
              {selectedMonth && (
                <button className="drill-back-btn" onClick={() => { setSelectedMonth(''); setSelectedDay(''); }}>
                  Aylara Dön
                </button>
              )}
              {selectedYear && !selectedMonth && (
                <button className="drill-back-btn" onClick={() => { setSelectedYear(null); setSelectedMonth(''); setSelectedDay(''); }}>
                  Yıllara Dön
                </button>
              )}
            </div>
          </div>

          {!selectedYear && (
            <div className="drill-grid years">
              {yearBuckets.map((y) => (
                <button key={y.year} className="drill-card" onClick={() => setSelectedYear(y.year)}>
                  <div className="drill-title">{y.year}</div>
                  <div className="drill-meta">{y.count} işlem</div>
                  <div className="drill-meta">TP/SL: <span className="win">{y.tp}</span>/<span className="loss">{y.sl}</span></div>
                  <div className={`drill-r ${y.totalR >= 0 ? 'win' : 'loss'}`}>{y.totalR >= 0 ? '+' : ''}{y.totalR.toFixed(2)}R</div>
                </button>
              ))}
            </div>
          )}

          {selectedYear && !selectedMonth && (
            <div className="drill-grid months">
              {monthBuckets.map((m) => (
                <button key={m.monthKey} className="drill-card" onClick={() => setSelectedMonth(m.monthKey)}>
                  <div className="drill-title">{m.label}</div>
                  <div className="drill-meta">{m.count} işlem</div>
                  <div className="drill-meta">TP/SL: <span className="win">{m.tp}</span>/<span className="loss">{m.sl}</span></div>
                  <div className={`drill-r ${m.totalR >= 0 ? 'win' : 'loss'}`}>{m.totalR >= 0 ? '+' : ''}{m.totalR.toFixed(2)}R</div>
                </button>
              ))}
            </div>
          )}

          {selectedYear && selectedMonth && (
            <>
              <div className="drill-grid days">
                {dayBuckets.map((d) => (
                  <button
                    key={d.dayKey}
                    className={`drill-card ${selectedDay === d.dayKey ? 'active' : ''}`}
                    onClick={() => setSelectedDay(d.dayKey)}
                  >
                    <div className="drill-title">{d.label}</div>
                    <div className="drill-meta">{d.count} işlem</div>
                    <div className="drill-meta">TP/SL: <span className="win">{d.tp}</span>/<span className="loss">{d.sl}</span></div>
                    <div className={`drill-r ${d.totalR >= 0 ? 'win' : 'loss'}`}>{d.totalR >= 0 ? '+' : ''}{d.totalR.toFixed(2)}R</div>
                  </button>
                ))}
              </div>

              {selectedDayTrades.length > 0 && (
                <div className="day-notebook">
                  <div className="day-header">
                    <div className="day-title">{selectedDayLabel}</div>
                    <div className="day-summary">
                      <span>{selectedDayTrades.length} işlem</span>
                      <span className="tp-sl-ratio">
                        Toplam R:{' '}
                        <span className={getTotalR(selectedDayTrades) >= 0 ? 'win' : 'loss'}>
                          {getTotalR(selectedDayTrades) >= 0 ? '+' : ''}{getTotalR(selectedDayTrades).toFixed(2)}
                        </span>
                      </span>
                    </div>
                  </div>
                  {renderTradeCards(selectedDayTrades)}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    );
  }

  return (
    <div id="dashboard" className="visible" style={{ opacity: 1, display: 'block' }}>
      {Object.keys(groupedLive).map((dateKey) => {
        const trades = groupedLive[dateKey];
        const counts = summarizeLiveCounts(trades);

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
            {renderTradeCards(trades)}
          </div>
        );
      })}
    </div>
  );
};

export default Dashboard;
