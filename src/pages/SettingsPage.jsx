import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTradeContext } from '../context/TradeContext';
import { useLang } from '../context/LanguageContext';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { pushSupported, pushState, enablePush, disablePush } from '../utils/push';

const SettingsPage = () => {
  const {
    allSignals, selectedSymbols, pendingSymbols, toggleSymbol, applySymbols,
    selectAllPendingSymbols, clearPendingSymbols, testDbConnection, dbStatus, dbMessage,
  } = useTradeContext();
  const { t, lang, setLang } = useLang();
  const { theme, setTheme } = useTheme();
  const { user, profile, isAdmin, logout } = useAuth();
  const [savedSymbols, setSavedSymbols] = useState(false);

  // Web Push (native phone notifications) — mirrors the Telegram alerts.
  const [push, setPush] = useState({ supported: pushSupported(), permission: 'default', subscribed: false });
  const [pushBusy, setPushBusy] = useState(false);
  const [pushErr, setPushErr] = useState('');
  useEffect(() => { pushState().then(setPush).catch(() => {}); }, []);
  const togglePush = async () => {
    setPushBusy(true); setPushErr('');
    try {
      if (push.subscribed) await disablePush();
      else await enablePush();
      setPush(await pushState());
    } catch (e) {
      setPushErr(e?.message === 'denied' ? t('Bildirim izni reddedildi.') : t('Bildirim ayarlanamadı.'));
    } finally { setPushBusy(false); }
  };

  const uniqueSymbols = useMemo(() => [...new Set(allSignals.map((s) => s.symbol))].sort(), [allSignals]);

  return (
    <div className="settings-page">
      <div className="settings-head">
        <div className="summary-kicker">PUSU</div>
        <h2>{t('Ayarlar')}</h2>
      </div>

      <div className="settings-grid">
        {/* Appearance */}
        <section className="overview-card settings-card">
          <div className="summary-title">{t('Görünüm')}</div>
          <div className="settings-row">
            <span>{t('Tema')}</span>
            <div className="seg">
              <button className={theme === 'dark' ? 'active' : ''} onClick={() => setTheme('dark')}>{t('Koyu')}</button>
              <button className={theme === 'light' ? 'active' : ''} onClick={() => setTheme('light')}>{t('Açık')}</button>
            </div>
          </div>
          <div className="settings-row">
            <span>{t('Dil')}</span>
            <div className="seg">
              <button className={lang === 'tr' ? 'active' : ''} onClick={() => setLang('tr')}>TR</button>
              <button className={lang === 'en' ? 'active' : ''} onClick={() => setLang('en')}>EN</button>
            </div>
          </div>
        </section>

        {/* Data & engine */}
        <section className="overview-card settings-card">
          <div className="summary-title">{t('Veri & Motor')}</div>
          <div className="settings-row">
            <span>PUSU Engine</span>
            <b className="win">● ONLINE</b>
          </div>
          <div className="settings-row">
            <span>{t('Kapsam')}</span>
            <b>17 {t('sembol')} · 4 {t('strateji')} · 1h MTF</b>
          </div>
          <div className="settings-row">
            <span>{t('Veritabanı')}</span>
            <b className={dbStatus === 'ok' ? 'win' : dbStatus === 'fail' ? 'loss' : ''}>{dbMessage || '—'}</b>
          </div>
          <button className="header-btn" onClick={testDbConnection}>{t('Bağlantıyı Test Et')}</button>
        </section>

        {/* Notifications (Web Push) */}
        <section className="overview-card settings-card">
          <div className="summary-title">{t('Bildirimler')}</div>
          <div className="settings-row">
            <span>{t('Telefon Bildirimi')}</span>
            <b className={push.subscribed ? 'win' : ''}>{push.subscribed ? '● ' + t('Açık') : t('Kapalı')}</b>
          </div>
          {!push.supported && (
            <div className="settings-row">
              <span className="loss" style={{ fontSize: 12 }}>
                {t('Bu cihaz/kurulum desteklemiyor. iOS’ta önce uygulamayı Ana Ekrana ekleyin.')}
              </span>
            </div>
          )}
          <button className="header-btn" disabled={!push.supported || pushBusy} onClick={togglePush}>
            {pushBusy ? '…' : push.subscribed ? '🔕 ' + t('Bildirimleri Kapat') : '🔔 ' + t('Bildirimleri Aç')}
          </button>
          {pushErr && (
            <div className="settings-row"><span className="loss" style={{ fontSize: 12 }}>{pushErr}</span></div>
          )}
        </section>

        {/* Symbols */}
        <section className="overview-card settings-card settings-card--wide">
          <div className="summary-title">{t('Semboller')} ({selectedSymbols.size})</div>
          {uniqueSymbols.length === 0 && <div className="summary-empty">{t('Kayıt yok')}</div>}
          <div className="settings-symbols">
            {uniqueSymbols.map((sym) => (
              <label key={sym} className={pendingSymbols.has(sym) ? 'on' : ''}>
                <input type="checkbox" checked={pendingSymbols.has(sym)} onChange={() => toggleSymbol(sym)} />
                {sym}
              </label>
            ))}
          </div>
          <div className="settings-symbol-actions">
            <button className="apply-btn" onClick={() => { applySymbols(); setSavedSymbols(true); setTimeout(() => setSavedSymbols(false), 1500); }}>
              ✅ {t('Uygula')}{savedSymbols ? ' ✓' : ''}
            </button>
            <button className="apply-btn" onClick={selectAllPendingSymbols}>{t('Tümünü Seç')}</button>
            <button className="apply-btn ghost" onClick={clearPendingSymbols}>{t('Temizle')}</button>
          </div>
        </section>

        {/* Account */}
        <section className="overview-card settings-card">
          <div className="summary-title">{t('Hesap')}</div>
          <div className="settings-row">
            <span>{t('Kullanıcı')}</span>
            <b>{user?.name || 'PUSU'}</b>
          </div>
          <div className="settings-row">
            <span>{t('E-posta')}</span>
            <b>{user?.email || '—'}</b>
          </div>
          <div className="settings-row">
            <span>{t('Durum')}</span>
            <span className={`chip ${profile?.status === 'active' ? 'chip--ok' : profile?.status === 'disabled' ? 'chip--err' : 'chip--warn'}`}>
              {profile?.status === 'active' ? t('Aktif')
                : profile?.status === 'disabled' ? t('Devre dışı')
                : t('Onay bekleniyor')}
            </span>
          </div>
          <Link className="header-btn" to="/trading">{t('İşlem Merkezi')} →</Link>
          {isAdmin && <Link className="header-btn" to="/admin">{t('Yönetim')} →</Link>}
          <button className="header-btn settings-logout" onClick={logout}>⏻ {t('Çıkış Yap')}</button>
        </section>

        {/* About */}
        <section className="overview-card settings-card">
          <div className="summary-title">{t('Hakkında')}</div>
          <div className="settings-row"><span>PUSU</span><b>Liquidity Ambush System</b></div>
          <div className="settings-row"><span>{t('Sürüm')}</span><b>v1.0</b></div>
          <div className="settings-about">WAIT · TRAP · EXECUTE</div>
        </section>
      </div>
    </div>
  );
};

export default SettingsPage;
