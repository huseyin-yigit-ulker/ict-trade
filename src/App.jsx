import { TradeProvider, useTradeContext } from './context/TradeContext';
import FileLoader from './components/FileLoader';
import Header from './components/Header';
import Dashboard from './components/Dashboard';
import ChartModal from './components/ChartModal';
import StatsModal from './components/StatsModal';
import SummaryModal from './components/SummaryModal';
import LiveTicker from './components/LiveTicker';

const MainContent = () => {
  const { isLoaded, activeSignal, showStats, showSummary } = useTradeContext();

  if (!isLoaded) return <FileLoader />;

  return (
    <>
      <Header />
      <Dashboard />
      {activeSignal && <ChartModal />}
      {showStats && <StatsModal />}
      {showSummary && <SummaryModal />}
      <LiveTicker />
    </>
  );
};

function App() {
  return (
    <TradeProvider>
      <MainContent />
    </TradeProvider>
  );
}

export default App;
