import { BrowserRouter } from 'react-router-dom';
import { LanguageProvider } from './context/LanguageContext';
import { ThemeProvider } from './context/ThemeContext';
import { AuthProvider } from './context/AuthContext';
import { TradeProvider } from './context/TradeContext';
import AppRoutes from './AppRoutes';

// Rota ağacı AppRoutes'ta: rol çatalı (admin = tam arayüz, kullanıcı = 4 sekmeli
// Binance-tarzı basit kabuk) profil yüklendikten sonra orada seçilir.
function App() {
  return (
    <LanguageProvider>
      <ThemeProvider>
        <AuthProvider>
          <TradeProvider>
            <BrowserRouter>
              <AppRoutes />
            </BrowserRouter>
          </TradeProvider>
        </AuthProvider>
      </ThemeProvider>
    </LanguageProvider>
  );
}

export default App;
