import { useEffect, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useLang } from '../../context/LanguageContext';
import { getJSON } from '../../utils/supa';
import { useStreamDisplay } from '../../utils/useStreamDisplay';
import { STREAM_ROWS, netLabel, SETTINGS_EVT } from '../../components/trading/streams';
import { useExecActivation } from '../../utils/execActivation';
import SetupGuideCard from '../../components/trading/SetupGuideCard';
import ApiKeysCard from '../../components/trading/ApiKeysCard';
import TemplatesCard from '../../components/trading/TemplatesCard';
import StreamActivationCard from '../../components/trading/StreamActivationCard';
import RiskCard from '../../components/trading/RiskCard';
import SymbolPickerCard from '../../components/trading/SymbolPickerCard';

// Bot — kullanıcı modunun kontrol odası. Üstte hero durum kartı (bot aktif/pasif +
// akış çipleri); altında MEVCUT İşlem Merkezi kartları AYNEN (GERÇEK PARA onayı,
// KILL/drain mantığı StreamActivationCard'ın içinde — oraya dokunulmaz). İnce Ayar
// katlanır bölümde. features.trading=false → tek bilgi kartı (sekme ölü hissetmesin).

const statusOfRow = (r, t) => {
  if (r.kill_requested) return { label: t('ACİL KAPAMA'), cls: 'st-sl' };
  if (r.enabled) return { label: t('ÇALIŞIYOR'), cls: 'st-active' };
  if (r.drain) return { label: t('BOŞALTILIYOR'), cls: 'st-wait' };
  return { label: t('DURDU'), cls: 'st-cancel' };
};

export default function BotPage() {
  const { t } = useLang();
  const { user, features } = useAuth();
  const sd = useStreamDisplay();
  const act = useExecActivation();
  const [rows, setRows] = useState([]);

  useEffect(() => {
    if (!user?.id) return undefined;
    let alive = true;
    const load = () => {
      getJSON(`user_stream_settings?select=stream,network,enabled,drain,kill_requested,symbols&user_id=eq.${user.id}`)
        .then((r) => { if (alive) setRows(r || []); })
        .catch(() => { if (alive) setRows([]); });
    };
    load();
    window.addEventListener(SETTINGS_EVT, load);
    return () => { alive = false; window.removeEventListener(SETTINGS_EVT, load); };
  }, [user?.id]);

  if (features?.trading === false) {
    return (
      <div className="ush-bot">
        <section className="ush-card ush-cta">
          <h3>{t('Bot erişimi kapalı')}</h3>
          <p>{t('Bot erişimi hesabınızda kapalı — yöneticinize başvurun.')}</p>
        </section>
      </div>
    );
  }

  const anyOn = rows.some((r) => r.enabled);
  const fresh = !act.loading && !act.mainnet && !act.testnet;
  // Kullanıcının satırı olan aktivasyon kombinasyonları; hiç satır yoksa hero sade kalır.
  const shownRows = STREAM_ROWS
    .map((d) => ({ d, r: rows.find((x) => x.stream === d.stream && x.network === d.network) }))
    .filter(({ r }) => !!r);

  return (
    <div className="ush-bot">
      {/* Hero durum kartı */}
      <section className={`ush-card ush-bothero${anyOn ? ' is-on' : ''}`}>
        <div className="ush-bothero__headline">
          <span className={`ush-bothero__dot${anyOn ? ' is-on' : ''}`} />
          <h2>{anyOn ? t('Bot aktif') : t('Bot pasif')}</h2>
        </div>
        <p className="ush-bothero__sub">
          {t('Sinyaller merkezî olarak üretilir; emirler kendi Binance hesabınızda, kendi anahtarınızla çalışır.')}
        </p>
        {shownRows.length > 0 && (
          <div className="ush-bothero__rows">
            {shownRows.map(({ d, r }) => {
              const st = statusOfRow(r, t);
              return (
                <div key={`${d.stream}:${d.network}`} className="ush-bothero__row">
                  <span className="ush-chip ush-chip--stream">{sd.name(d.maskKey)}</span>
                  <span className="ush-chip ush-chip--net">{netLabel(d.network)}</span>
                  <span className={`ush-badge ${st.cls}`}>● {st.label}</span>
                  <span className="ush-bothero__syms">{(r.symbols || []).length} {t('sembol')}</span>
                </div>
              );
            })}
          </div>
        )}
      </section>

      <div className="settings-grid ush-botgrid">
        {fresh && <SetupGuideCard />}
        <ApiKeysCard />
        <TemplatesCard />
        <StreamActivationCard />

        <details className="ush-finetune">
          <summary>
            <span>{t('İnce Ayar')}</span>
            <small>{t('İsteğe bağlı — şablonların ayarladığı risk ve sembolleri elle değiştirin.')}</small>
          </summary>
          <div className="settings-grid">
            <RiskCard />
            <SymbolPickerCard />
          </div>
        </details>

        {!fresh && <SetupGuideCard />}
      </div>
    </div>
  );
}
