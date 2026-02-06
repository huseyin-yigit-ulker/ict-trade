import { useMemo } from 'react';
import { useTradeContext } from '../context/TradeContext';

const Dashboard = () => {
  const { filteredSignals, setActiveSignal } = useTradeContext();

  const calculatePnL = (sig) => {
    if (sig.status !== 'TP' && sig.status !== 'SL') return 0;
    const diff = sig.dir === 'LONG' ? (sig.exitPrice - sig.entry) : (sig.entry - sig.exitPrice);
    return (diff / sig.entry) * 100;
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
        const dailyPnL = trades.reduce((sum, t) => sum + calculatePnL(t), 0);

        return (
          <div key={dateKey} className="day-notebook">
            <div className="day-header">
              <div className="day-title">{dateKey}</div>
              <div className="day-summary">
                <span>{trades.length} işlem</span>
                <span className={dailyPnL >= 0 ? 'win' : 'loss'}>{dailyPnL.toFixed(2)}%</span>
              </div>
            </div>

            <div className="trade-grid">
              {trades.map(sig => {
                const pnl = calculatePnL(sig);
                const pnlClass = pnl > 0 ? 'win' : (pnl < 0 ? 'loss' : 'waiting');
                const timeLabel = sig.dateObj.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });

                return (
                  <div key={sig.id} className="trade-card" onClick={() => setActiveSignal(sig)}>
                    <div className="trade-head">
                      <span className="symbol-box">{sig.symbol}</span>
                      <span className={`dir-badge ${sig.dir.toLowerCase()}`}>{sig.dir}</span>
                      <span className="time-detail">{timeLabel}</span>
                    </div>
                    <div className="trade-body">
                      <div className="trade-metric">
                        <span className="metric-label">Durum</span>
                        <span className={`status-text ${pnlClass}`}>{sig.status}</span>
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
                      <div className={`chip ${pnlClass}`}>{pnlClass === 'waiting' ? 'BEKLEMEDE' : (pnl > 0 ? 'TP' : 'SL')}</div>
                      <div className="chip outline">Detaylı Grafik</div>
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
