import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { LanguageProvider } from './context/LanguageContext';
import { ThemeProvider } from './context/ThemeContext';
import { AuthProvider, RequireAuth, RequireActive, RequireAdmin, RequireFeature } from './context/AuthContext';
import { TradeProvider } from './context/TradeContext';
import LoginScreen from './components/LoginScreen';
import AppShell from './components/layout/AppShell';
import IntroPage from './pages/IntroPage';
import CommandCenterPage from './pages/CommandCenterPage';
import IntelligencePage from './pages/IntelligencePage';
import SettingsPage from './pages/SettingsPage';
import TrendPage from './pages/TrendPage';
import MarketCapPage from './pages/MarketCapPage';
import LivePositionsPage from './pages/LivePositionsPage';
import MidasXLivePage from './pages/MidasXLivePage';
import TradingSettingsPage from './pages/TradingSettingsPage';
import AdminPage from './pages/AdminPage';
import ExecGate from './components/ExecGate';

function App() {
  return (
    <LanguageProvider>
      <ThemeProvider>
        <AuthProvider>
          <TradeProvider>
            <BrowserRouter>
              <Routes>
                <Route path="/login" element={<LoginScreen />} />
                <Route element={<RequireAuth><AppShell /></RequireAuth>}>
                  <Route index element={<IntroPage />} />
                  <Route path="/trend" element={<TrendPage />} />
                  <Route path="/total" element={<MarketCapPage />} />
                  <Route path="/binance" element={<RequireActive><ExecGate network="mainnet"><LivePositionsPage network="mainnet" /></ExecGate></RequireActive>} />
                  <Route path="/binance-paper" element={<RequireActive><ExecGate network="testnet"><LivePositionsPage network="testnet" /></ExecGate></RequireActive>} />
                  <Route path="/binance-altin" element={<RequireActive><ExecGate network="any"><MidasXLivePage /></ExecGate></RequireActive>} />
                  <Route path="/trading" element={<RequireActive><RequireFeature k="trading"><TradingSettingsPage /></RequireFeature></RequireActive>} />
                  <Route path="/admin" element={<RequireAdmin><AdminPage /></RequireAdmin>} />
                  <Route path="/:strategy/:mode" element={<CommandCenterPage />} />
                  {/* İstihbarat = kurumsal quant tearsheet → yalnız admin. Non-admin (eski
                      user_features.intelligence=true izni olsa bile) '/'e döner. */}
                  <Route path="/intelligence" element={<RequireAdmin><IntelligencePage /></RequireAdmin>} />
                  <Route path="/settings" element={<SettingsPage />} />
                </Route>
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </BrowserRouter>
          </TradeProvider>
        </AuthProvider>
      </ThemeProvider>
    </LanguageProvider>
  );
}

export default App;
