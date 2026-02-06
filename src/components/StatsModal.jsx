import { useTradeContext } from '../context/TradeContext';

const StatsModal = () => {
  const { allSignals, setShowStats } = useTradeContext();

  const calculatePnL = (sig) => {
    if (sig.status !== 'TP' && sig.status !== 'SL') return 0;
    const diff = sig.dir === 'LONG' ? (sig.exitPrice - sig.entry) : (sig.entry - sig.exitPrice);
    return (diff / sig.entry) * 100;
  };

  const stats = {};
  allSignals.forEach(s => {
    if (!stats[s.symbol]) stats[s.symbol] = { count: 0, wins: 0, pnl: 0 };
    stats[s.symbol].count++;
    const pnl = calculatePnL(s);
    stats[s.symbol].pnl += pnl;
    if (s.status === 'TP') stats[s.symbol].wins++;
  });

  return (
    <div id="stats-modal" className="modal-overlay" style={{display:'block'}}>
      <div className="stats-box">
        <div className="stats-header">
          <h2>PORTFÖY KARNESİ</h2>
          <button id="close-stats" onClick={() => setShowStats(false)}>X</button>
        </div>
        <div className="stats-content">
          <table className="stats-table">
            <thead>
              <tr>
                <th>Sembol</th>
                <th>İşlem</th>
                <th>Win Rate</th>
                <th>Toplam PnL</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(stats).sort((a,b) => b[1].pnl - a[1].pnl).map(([sym, data]) => {
                const wr = data.count > 0 ? ((data.wins / data.count) * 100).toFixed(0) : 0;
                return (
                  <tr key={sym}>
                    <td><b>{sym}</b></td>
                    <td>{data.count}</td>
                    <td className={wr >= 50 ? 'win' : 'loss'}>%{wr}</td>
                    <td className={data.pnl >= 0 ? 'win' : 'loss'}>%{data.pnl.toFixed(2)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default StatsModal;