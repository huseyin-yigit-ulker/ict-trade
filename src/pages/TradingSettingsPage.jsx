import { useLang } from '../context/LanguageContext';
import SetupGuideCard from '../components/trading/SetupGuideCard';
import ApiKeysCard from '../components/trading/ApiKeysCard';
import TemplatesCard from '../components/trading/TemplatesCard';
import StreamActivationCard from '../components/trading/StreamActivationCard';
import RiskCard from '../components/trading/RiskCard';
import SymbolPickerCard from '../components/trading/SymbolPickerCard';

// İşlem Merkezi — the per-user trading control room. Ordered as a new-user
// funnel (2026-07-07 simplification): Kurulum Rehberi (auto-checked onboarding
// steps incl. the Binance API-key how-to) → API keys → Hazır Şablonlar
// (one-click symbol+risk presets) → activation; the manual risk/symbol editors
// live below an "İnce Ayar" divider as optional fine-tuning. Signals are
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
        <p className="trading-intro trading-intro--risk">
          {t('Geçmiş ve backtest performansı gelecekteki getiriyi garanti etmez; canlı sonuçlar (kayma, komisyon, kısmi dolum) backtest’in altında kalır. Gerçek-para işlemleri tamamen kendi sorumluluğunuzdadır.')}
        </p>
      </div>

      <div className="settings-grid">
        <SetupGuideCard />
        <ApiKeysCard />
        <TemplatesCard />
        <StreamActivationCard />

        <div className="settings-sep">
          <span>{t('İnce Ayar')}</span>
          <small>{t('İsteğe bağlı — şablonların ayarladığı risk ve sembolleri elle değiştirin.')}</small>
        </div>

        <RiskCard />
        <SymbolPickerCard />
      </div>
    </div>
  );
};

export default TradingSettingsPage;
