import { useCallback, useEffect, useState } from 'react';
import { useLang } from '../../context/LanguageContext';
import { getJSON } from '../../utils/supa';
import { SETTINGS_EVT } from './streams';

// Kurulum Rehberi — the new-user onboarding checklist for the İşlem Merkezi.
// Four steps (create key on Binance → add it here → pick a template → activate),
// each auto-checked from the user's own rows (user_api_keys_public /
// user_stream_settings). Collapses to a single "done" line once all 4 pass.
// Strategy-anonymization: the guide talks only about keys/risk/symbols — never
// about how any stream trades.

const VM_IP = import.meta.env.VITE_VM_EGRESS_IP;
const BINANCE_API_URL = 'https://www.binance.com/en/my/settings/api-management';

const IconCheck = () => (
  <svg viewBox="0 0 20 20" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
    <path d="M4 10.6 8.2 14.6 16 5.6" />
  </svg>
);

export default function SetupGuideCard() {
  const { t } = useLang();
  const [state, setState] = useState({ anyKey: false, validKey: false, pendingKey: false, symbols: false, enabled: false });
  const [loaded, setLoaded] = useState(false);
  const [howto, setHowto] = useState(false);
  const [forceOpen, setForceOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      const [keys, rows] = await Promise.all([
        getJSON('user_api_keys_public?select=network,status,created_at&order=created_at.desc'),
        getJSON('user_stream_settings?select=enabled,symbols'),
      ]);
      const live = (keys || []).filter((k) => k.status !== 'rotated');
      setState({
        anyKey: live.length > 0,
        validKey: live.some((k) => k.status === 'valid'),
        pendingKey: live.some((k) => k.status === 'pending_verify'),
        symbols: (rows || []).some((r) => (r.symbols || []).length > 0),
        enabled: (rows || []).some((r) => r.enabled),
      });
      setLoaded(true);
    } catch { /* checklist is advisory — stay silent on fetch errors */ }
  }, []);

  useEffect(() => {
    load();
    window.addEventListener(SETTINGS_EVT, load);
    return () => window.removeEventListener(SETTINGS_EVT, load);
  }, [load]);

  const steps = [
    {
      key: 'create',
      done: state.anyKey,
      title: t("Binance'te API anahtarı oluşturun"),
      body: (
        <>
          <p className="setup-step__desc">{t('Binance hesabınızda (Futures açık olmalı) yalnız işlem yetkili bir API anahtarı oluşturun.')}</p>
          <button className="header-btn" type="button" onClick={() => setHowto((o) => !o)} aria-expanded={howto}>
            {howto ? '▾' : '▸'} {t('Adım adım nasıl yapılır?')}
          </button>
          {howto && (
            <ol className="setup-howto">
              <li>
                {t('Binance’e girin →')}{' '}
                <a href={BINANCE_API_URL} target="_blank" rel="noreferrer">{t('Hesap → API Yönetimi')} ↗</a>
              </li>
              <li>{t('“Create API” → “System generated” seçin, bir isim verin (örn. PUSU).')}</li>
              <li>{t('Güvenlik doğrulamalarını (e-posta/SMS/2FA) tamamlayın.')}</li>
              <li><b>{t('“Enable Futures” iznini işaretleyin.')}</b></li>
              <li><b>{t('“Enable Withdrawals” (çekim) iznini ASLA vermeyin')}</b> — {t('çekim yetkili anahtar sistem tarafından reddedilir.')}</li>
              <li>
                {t('“Restrict access to trusted IPs only” seçin ve şu IP’yi ekleyin:')}
                {VM_IP ? <> <code className="setup-ip">{VM_IP}</code></> : ` (${t('IP adresi yöneticinizden')})`}
              </li>
              <li>{t('API Key ve Secret’ı kopyalayın — Secret yalnız BİR KEZ gösterilir.')}</li>
              <li>{t('Futures hesabınız “One-way” pozisyon modunda olmalı (Hedge modu desteklenmez): Futures → Ayarlar → Position Mode.')}</li>
            </ol>
          )}
        </>
      ),
    },
    {
      key: 'add',
      done: state.validKey,
      title: t("Anahtarı PUSU'ya ekleyin"),
      body: (
        <p className="setup-step__desc">
          {t('Aşağıdaki “API Anahtarı” kartından Key + Secret’ı gönderin. Anahtar tarayıcıda şifrelenir ve otomatik doğrulanır (≤1 dk).')}
          {state.pendingKey && !state.validKey && <b> · {t('Doğrulanıyor…')}</b>}
        </p>
      ),
    },
    {
      key: 'template',
      done: state.symbols,
      title: t('Hazır bir şablon seçin'),
      body: (
        <p className="setup-step__desc">
          {t('“Hazır Şablonlar” kartından risk profilinize uygun bir paket uygulayın — semboller ve risk limitleri tek tıkla ayarlanır. İsterseniz aşağıdaki İnce Ayar kartlarından elle değiştirin.')}
        </p>
      ),
    },
    {
      key: 'activate',
      done: state.enabled,
      title: t('Akışı etkinleştirin'),
      body: (
        <p className="setup-step__desc">
          {t('“Akış Aktivasyonu” kartından bir akışı açın. Paper (testnet) gerçek para riski taşımaz — önce onunla deneyin; GERÇEK PARA modu yazılı onay ister.')}
        </p>
      ),
    },
  ];

  const doneCount = steps.filter((s) => s.done).length;
  const allDone = loaded && doneCount === steps.length;

  if (allDone && !forceOpen) {
    return (
      <section className="overview-card settings-card settings-card--wide setup-guide setup-guide--done">
        <div className="setup-done-row">
          <span className="setup-step__num setup-step__num--done"><IconCheck /></span>
          <b>{t('Kurulum tamam — akışınız çalışıyor.')}</b>
          <button className="header-btn" type="button" onClick={() => setForceOpen(true)}>
            {t('Rehberi göster')}
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="overview-card settings-card settings-card--wide setup-guide">
      <div className="summary-title">
        {t('Kurulum Rehberi')}
        <span className="setup-progress">{doneCount}/{steps.length}</span>
      </div>
      <div className="setup-bar" role="progressbar" aria-valuenow={doneCount} aria-valuemin={0} aria-valuemax={steps.length}>
        <span style={{ width: `${(doneCount / steps.length) * 100}%` }} />
      </div>

      <div className="setup-steps">
        {steps.map((s, i) => (
          <div key={s.key} className={`setup-step${s.done ? ' setup-step--done' : ''}`}>
            <span className={`setup-step__num${s.done ? ' setup-step__num--done' : ''}`}>
              {s.done ? <IconCheck /> : i + 1}
            </span>
            <div className="setup-step__body">
              <div className="setup-step__title">{s.title}</div>
              {!s.done && s.body}
            </div>
          </div>
        ))}
      </div>

      {allDone && (
        <button className="header-btn" type="button" onClick={() => setForceOpen(false)}>
          {t('Gizle')}
        </button>
      )}
    </section>
  );
}
