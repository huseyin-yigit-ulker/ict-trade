import { useTradeContext } from '../context/TradeContext';

const Dashboard = () => {
  const { filteredSignals, setActiveSignal } = useTradeContext();

  const calculatePnL = (sig) => {
    if (sig.status !== 'TP' && sig.status !== 'SL') return 0;
    const diff = sig.dir === 'LONG' ? (sig.exitPrice - sig.entry) : (sig.entry - sig.exitPrice);
    return (diff / sig.entry) * 100;
  };

  const grouped = filteredSignals.reduce((acc, sig) => {
    const dateKey = sig.dateObj.toLocaleDateString('tr-TR', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' });
    if (!acc[dateKey]) acc[dateKey] = [];
    acc[dateKey].push(sig);
    return acc;
  }, {});

  return (
    <div id="dashboard" className="visible" style={{ opacity: 1, display: 'block' }}>
      {Object.keys(grouped).map(dateKey => {
        const trades = grouped[dateKey];
        const dailyPnL = trades.reduce((sum, t) => sum + calculatePnL(t), 0);
        
        return (
          <div key={dateKey}>
            <div className="date-header">
              <span>{dateKey}</span>
              <div className="daily-summary">
                <span style={{ color: '#aaa' }}>{trades.length} İşlem</span>
                <span className={dailyPnL >= 0 ? 'win' : 'loss'}>Net: {dailyPnL.toFixed(2)}%</span>
              </div>
            </div>
            
            <div className="date-group">
              {trades.map(sig => {
                const pnl = calculatePnL(sig);
                const pnlClass = pnl > 0 ? 'win' : (pnl < 0 ? 'loss' : 'waiting');
                
                return (
                  <div key={sig.id} className="trade-item" onClick={() => setActiveSignal(sig)}>
                    <div className="trade-info">
                      <span className="symbol-box">{sig.symbol}</span>
                      {/* DÜZELTİLEN SATIR BURASI: className eklendi */}
                      <span className={`dir-badge ${sig.dir.toLowerCase()}`}>{sig.dir}</span>
                      <span className="time-detail">{sig.dateObj.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' })}</span>
                    </div>
                    <div className="trade-result">
                      <span className={`status-text ${pnlClass}`}>{sig.status}</span>
                      <span className={`pnl-text ${pnlClass}`}>{pnl !== 0 ? pnl.toFixed(2) + '%' : '--'}</span>
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