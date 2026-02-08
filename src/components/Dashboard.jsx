import { useMemo } from 'react';
import { useTradeContext } from '../context/TradeContext';

const Dashboard = () => {
  const { filteredSignals, setActiveSignal, setChartView, mode, liveStatuses } = useTradeContext();

  const calculatePnL = (sig) => {
    if (sig.status !== 'TP' && sig.status !== 'SL') return 0;
    const diff = sig.dir === 'LONG' ? (sig.exitPrice - sig.entry) : (sig.entry - sig.exitPrice);
    return (diff / sig.entry) * 100;
  };

  const resolveLiveMeta = (status) => {
    if (!status) return { label: 'BEKLEMEDE', cls: 'waiting', terminal: false };
    if (status === 'TP Oldu') return { label: 'TP', cls: 'win', terminal: true };
    if (status === 'SL Oldu') return { label: 'SL', cls: 'loss', terminal: true };
    if (status === 'TP/SL Aynı Mum') return { label: 'TP/SL', cls: 'loss', terminal: true };
    if (status.startsWith('İptal')) return { label: 'İPTAL', cls: 'loss', terminal: true };
    if (status.startsWith('İşlem Aktif')) return { label: 'AKTIF', cls: 'waiting', terminal: false };
    return { label: 'BEKLEMEDE', cls: 'waiting', terminal: false };
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

  const grouped = useMemo(() => {
    return filteredSignals.reduce((acc, sig) => {
      const dateKey = sig.dateObj.toLocaleDateString('tr-TR', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' });
      if (!acc[dateKey]) acc[dateKey] = [];
      acc[dateKey].push(sig);
      return acc;
    }, {});
  }, [filteredSignals]);

  return (
    <div id="dashboard" className="visible" style={{ opacity: 1, display: 'block' }}>
      {Object.keys(grouped).map(dateKey => {
        const trades = grouped[dateKey];
        const liveCounts = mode === 'live' ? summarizeLiveCounts(trades) : null;

        return (
          <div key={dateKey} className="day-notebook">
            <div className="day-header">
              <div className="day-title">{dateKey}</div>
              <div className="day-summary">
                <span>{trades.length} işlem</span>
                {mode === 'live' && (
                  <span className="tp-sl-ratio">
                    TP/SL: {liveCounts.tp}/{liveCounts.sl} • R:{' '}
                    <span className={liveCounts.rScore >= 0 ? 'win' : 'loss'}>
                      {liveCounts.rScore >= 0 ? '+' : ''}{liveCounts.rScore}
                    </span>
                  </span>
                )}
              </div>
            </div>

            <div className="trade-grid">
              {trades.map(sig => {
                const pnl = calculatePnL(sig);
                const liveStatus = mode === 'live' ? liveStatuses[sig.id]?.status : '';
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
                        <span className={`status-text ${pnlClass}`}>{mode === 'live' ? (liveStatus || 'Beklemede') : sig.status}</span>
                      </div>
                      <div className="trade-metric">
                        <span className="metric-label">P/L</span>
                        <span className={`pnl-text ${pnlClass}`}>{pnl !== 0 ? pnl.toFixed(2) + '%' : '--'}</span>
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
                      <button
                        className="chip outline"
                        onClick={(e) => {
                          e.stopPropagation();
                          setChartView('tv');
                          setActiveSignal(sig);
                        }}
                      >
                        Live Graph
                      </button>
                    </div>
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
