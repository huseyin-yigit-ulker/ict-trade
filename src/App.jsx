import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { LanguageProvider } from './context/LanguageContext';
import { ThemeProvider } from './context/ThemeContext';
import { AuthProvider, RequireAuth } from './context/AuthContext';
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
                  <Route path="/binance" element={<LivePositionsPage />} />
                  <Route path="/:strategy/:mode" element={<CommandCenterPage />} />
                  <Route path="/intelligence" element={<IntelligencePage />} />
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
