import { useEffect } from 'react';
import { useParams, Navigate } from 'react-router-dom';
import { useTradeContext, isValidStrategy } from '../context/TradeContext';
import { useAuth } from '../context/AuthContext';
import { slugToKey, slugFor } from '../utils/streamMask';
import Dashboard from '../components/Dashboard';

// Strategy × Mode view. The URL (/:strategy/:mode) is the source of truth: it syncs
// the route params into context (setView) so the single data-load effect fetches the
// right set. Live + Backtest for every module.
// PRIVACY (2026-07-04): URLs carry the anonymized codename slug (…/atlas/live) so raw
// version keys never appear in the address bar; legacy raw-key bookmarks still resolve.
const CommandCenterPage = () => {
  const { strategy: pStrat, mode: pMode } = useParams();
  const { strategy, mode, setView } = useTradeContext();
  const { features } = useAuth();
  const keyFromSlug = slugToKey(pStrat);
  const validS = isValidStrategy(keyFromSlug) ? keyFromSlug : null;
  const validM = (pMode === 'backtest' || pMode === 'live') ? pMode : null;

  useEffect(() => {
    if (validS && validM && (validS !== strategy || validM !== mode)) {
      setView(validS, validM);
    }
  }, [validS, validM, strategy, mode, setView]);

  if (!validS || !validM) return <Navigate to={`/${slugFor('d30so8f3h7')}/live`} replace />;
  // Admin bu kullanıcıya backtest yüzeyini kapattıysa deep-link de çalışmaz (nav zaten gizli).
  if (validM === 'backtest' && features?.backtest === false) return <Navigate to="/" replace />;
  return <Dashboard />;
};

export default CommandCenterPage;
