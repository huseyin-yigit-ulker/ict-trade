import { useLang } from '../context/LanguageContext';
import ApiKeysCard from '../components/trading/ApiKeysCard';
import StreamActivationCard from '../components/trading/StreamActivationCard';
import RiskCard from '../components/trading/RiskCard';
import SymbolPickerCard from '../components/trading/SymbolPickerCard';

// İşlem Merkezi — the per-user trading control room: Binance API keys (encrypted
// client-side), stream activation, risk limits and symbol selection. Signals are
// generated centrally by the VM; EXECUTION is per-user, on the user's own account.

const TradingSettingsPage = () => {
  const { t } = useLang();
  return (
    <div className="settings-page trading-page">
      <div className="settings-head">
        <div className="summary-kicker">PUSU</div>
        <h2>{t('İşlem Merkezi')}</h2>
        <p className="trading-intro">
          {t('Sinyaller merkezî olarak üretilir; emirler kendi Binance hesabınızda, kendi anahtarınızla çalışır.')}
        </p>
      </div>

      <div className="settings-grid">
        <ApiKeysCard />
        <StreamActivationCard />
        <RiskCard />
        <SymbolPickerCard />
      </div>
    </div>
  );
};

export default TradingSettingsPage;
