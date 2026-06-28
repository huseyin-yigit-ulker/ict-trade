import { useEffect } from 'react';
import { useParams, Navigate } from 'react-router-dom';
import { useTradeContext, isValidStrategy } from '../context/TradeContext';
import Dashboard from '../components/Dashboard';

// Strategy × Mode view. The URL (/:strategy/:mode) is the source of truth: it syncs
// the route params into context (setView) so the single data-load effect fetches the
// right set. Live + Backtest for every module. (2026-06-28: 'demo' mode retired — the
// Backtest tab now IS the live-faithful portfolio walk, so the separate demo view is gone.)
const CommandCenterPage = () => {
  const { strategy: pStrat, mode: pMode } = useParams();
  const { strategy, mode, setView } = useTradeContext();
  const validS = isValidStrategy(pStrat) ? pStrat : null;
  const validM = (pMode === 'backtest' || pMode === 'live') ? pMode : null;

  useEffect(() => {
    if (validS && validM && (validS !== strategy || validM !== mode)) {
      setView(validS, validM);
    }
  }, [validS, validM, strategy, mode, setView]);

  if (!validS || !validM) return <Navigate to="/main/live" replace />;
  return <Dashboard />;
};

export default CommandCenterPage;
