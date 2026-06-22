import { useEffect } from 'react';
import { useParams, Navigate } from 'react-router-dom';
import { useTradeContext, isValidStrategy } from '../context/TradeContext';
import Dashboard from '../components/Dashboard';
import DemoView from './DemoView';

// The scale-out strategies that carry a precomputed demo-faithful backtest (sync/live_exec).
const DEMO_STRATEGIES = new Set(['d30_4h_soc', 'd30so6c', 'd30so8c']);

// Strategy × Mode view. The URL (/:strategy/:mode) is the source of truth: it syncs
// the route params into context (setView) so the single data-load effect fetches the
// right set. Live + Backtest for every module; the scale-out streams (4R/6R/8R) also have
// a 'demo' mode = the demo-faithful portfolio backtest (DemoView, static JSON, no fetch).
const CommandCenterPage = () => {
  const { strategy: pStrat, mode: pMode } = useParams();
  const { strategy, mode, setView } = useTradeContext();
  const validS = isValidStrategy(pStrat) ? pStrat : null;
  const isDemo = pMode === 'demo' && DEMO_STRATEGIES.has(pStrat);
  const validM = (pMode === 'backtest' || pMode === 'live') ? pMode : (isDemo ? 'demo' : null);

  useEffect(() => {
    // 'demo' is self-contained (static JSON) — don't drive the live/backtest data load.
    if (validS && validM && validM !== 'demo' && (validS !== strategy || validM !== mode)) {
      setView(validS, validM);
    }
  }, [validS, validM, strategy, mode, setView]);

  if (!validS || !validM) return <Navigate to="/main/live" replace />;
  if (validM === 'demo') return <DemoView strategyKey={validS} />;
  return <Dashboard />;
};

export default CommandCenterPage;
