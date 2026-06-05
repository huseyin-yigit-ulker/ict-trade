import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { LanguageProvider } from './context/LanguageContext';
import { ThemeProvider } from './context/ThemeContext';
import { AuthProvider, RequireAuth } from './context/AuthContext';
import { TradeProvider } from './context/TradeContext';
import LoginScreen from './components/LoginScreen';
import AppShell from './components/layout/AppShell';
import CommandCenterPage from './pages/CommandCenterPage';
import IntelligencePage from './pages/IntelligencePage';
import SettingsPage from './pages/SettingsPage';

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
                  <Route path="/command" element={<CommandCenterPage />} />
                  <Route path="/intelligence" element={<IntelligencePage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                </Route>
                <Route path="*" element={<Navigate to="/command" replace />} />
              </Routes>
            </BrowserRouter>
          </TradeProvider>
        </AuthProvider>
      </ThemeProvider>
    </LanguageProvider>
  );
}

export default App;
