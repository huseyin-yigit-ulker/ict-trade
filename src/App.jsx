import { TradeProvider, useTradeContext } from './context/TradeContext';
import FileLoader from './components/FileLoader';
import Header from './components/Header';
import Dashboard from './components/Dashboard';
import ChartModal from './components/ChartModal';
import StatsModal from './components/StatsModal';
import './assets/css/style.css'; // Mevcut CSS'ini import et

const MainContent = () => {
  const { isLoaded, activeSignal, showStats } = useTradeContext();

  if (!isLoaded) return <FileLoader />;

  return (
    <>
      <Header />
      <Dashboard />
      {activeSignal && <ChartModal />}
      {showStats && <StatsModal />}
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