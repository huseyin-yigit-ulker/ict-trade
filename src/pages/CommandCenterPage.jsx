import Dashboard from '../components/Dashboard';

// The command center renders the live/backtest signal floor as Intelligence
// Reports. The data source follows the top-bar system mode (appMode → mode),
// so this page does not set the mode itself.
const CommandCenterPage = () => <Dashboard />;

export default CommandCenterPage;
