import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import Topbar from './Topbar';
import LiveTicker from '../LiveTicker';
import ChartModal from '../ChartModal';
import StatsModal from '../StatsModal';
import SummaryModal from '../SummaryModal';
import { useTradeContext } from '../../context/TradeContext';

const AppShell = () => {
  const { activeSignal, showStats, showSummary } = useTradeContext();
  return (
    <div className="app-shell">
      <Sidebar />
      <div className="app-main">
        <Topbar />
        <main className="app-content"><Outlet /></main>
      </div>

      {activeSignal && <ChartModal />}
      {showStats && <StatsModal />}
      {showSummary && <SummaryModal />}
      <LiveTicker />
    </div>
  );
};

export default AppShell;
