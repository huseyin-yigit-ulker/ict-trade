import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTradeContext } from '../context/TradeContext';
import { useLang } from '../context/LanguageContext';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { changePassword } from '../utils/supa';
import { pushSupported, pushState, enablePush, disablePush } from '../utils/push';
import { PAGE_CHOICES } from '../utils/userPrefs';

// Bildirim tercihi anahtarları — ict_trade.user_prefs kolonlarıyla birebir;
// VM tarafı push_user(kind=...) / send_push sinyal yayınlarında bunları uygular.
const NOTIF_ROWS = [
  { col: 'notify_entry', label: 'Pozisyon girişleri' },
  { col: 'notify_exit', label: 'Pozisyon kapanışları' },
  { col: 'notify_milestone', label: 'Ara hedef / iz süren stop' },
  { col: 'notify_signals', label: 'Sinyal yayınları' },
  { col: 'notify_system', label: 'Sistem uyarıları' },
];

const SettingsPage = () => {
  const {
    allSignals, selectedSymbols, pendingSymbols, toggleSymbol, applySymbols,
    selectAllPendingSymbols, clearPendingSymbols, testDbConnection, dbStatus, dbMessage,
  } = useTradeContext();
  const { t, lang, setLang } = useLang();
  const { theme, setTheme } = useTheme();
  const { user, profile, isAdmin, logout, prefs, updatePrefs, features } = useAuth();
  const [savedSymbols, setSavedSymbols] = useState(false);

  // Tercih kolonları default-true: yalnızca açıkça false kapalıdır.
  const notifOn = (col) => prefs?.[col] !== false;

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
      console.error('[push] toggle failed:', e);
      const m = e?.message || '';
      setPushErr(
        m === 'denied' ? t('Bildirim izni reddedildi (tarayıcı/telefon ayarından siteye izin verin).')
          : m === 'no session' ? t('Oturum bulunamadı — çıkıp tekrar giriş yapın.')
          : m === 'unsupported' || m === 'no service worker'
            ? t('Bu tarayıcı/ortam bildirimi desteklemiyor. HTTPS gerekir; iOS’ta önce uygulamayı Ana Ekrana ekleyin.')
            : `${t('Bildirim ayarlanamadı')}: ${m || t('bilinmeyen hata')}`,
      );
    } finally { setPushBusy(false); }
  };

  const uniqueSymbols = useMemo(() => [...new Set(allSignals.map((s) => s.symbol))].sort(), [allSignals]);

  // Şifre değiştir (GoTrue PUT /auth/v1/user) — geçici şifreyle açılan hesaplar için şart.
  const [pwOpen, setPwOpen] = useState(false);
  const [pw1, setPw1] = useState('');
  const [pw2, setPw2] = useState('');
  const [pwBusy, setPwBusy] = useState(false);
  const [pwMsg, setPwMsg] = useState(null);   // { ok: bool, text: string }
  const submitPassword = async (e) => {
    e.preventDefault();
    if (pwBusy) return;
    if (pw1.length < 10) { setPwMsg({ ok: false, text: t('Şifre en az 10 karakter olmalı.') }); return; }
    if (pw1 !== pw2) { setPwMsg({ ok: false, text: t('Şifreler eşleşmiyor.') }); return; }
    setPwBusy(true); setPwMsg(null);
    try {
      await changePassword(pw1);
      setPw1(''); setPw2(''); setPwOpen(false);
      setPwMsg({ ok: true, text: t('Şifre güncellendi.') });
    } catch (err) {
      setPwMsg({ ok: false, text: `${t('Şifre güncellenemedi')}: ${err?.message || ''}` });
    } finally { setPwBusy(false); }
  };

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
          <div className="settings-row">
            <span>{t('Açılış Sayfası')}</span>
            <select
              className="settings-select"
              value={prefs?.default_page || '/'}
              onChange={(e) => updatePrefs({ default_page: e.target.value })}
            >
              {PAGE_CHOICES
                .filter((c) => (c.path !== '/trading' || features?.trading !== false)
                  && (c.path !== '/intelligence' || features?.intelligence !== false))
                .map((c) => <option key={c.path} value={c.path}>{t(c.label)}</option>)}
            </select>
          </div>
          <div className="form-note">
            {t('Tema, dil ve açılış sayfası hesabınıza kaydedilir — tüm cihazlarınızda geçerlidir.')}
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
          {/* Hangi olaylarda bildirim gelsin — kullanıcı-başına, tüm cihazlar için. */}
          {push.subscribed && (
            <div className="notif-prefs">
              <div className="form-note">{t('Hangi olaylar bildirilsin?')}</div>
              {NOTIF_ROWS.map((r) => (
                <label key={r.col} className={`notif-pref${notifOn(r.col) ? ' on' : ''}`}>
                  <input
                    type="checkbox"
                    checked={notifOn(r.col)}
                    onChange={() => updatePrefs({ [r.col]: !notifOn(r.col) })}
                  />
                  <span>{t(r.label)}</span>
                </label>
              ))}
            </div>
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
          <button className="header-btn" onClick={() => { setPwOpen((v) => !v); setPwMsg(null); }}>
            🔑 {t('Şifre Değiştir')}
          </button>
          {pwOpen && (
            <form onSubmit={submitPassword} style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 8 }}>
              <input
                className="tinput" type="password" autoComplete="new-password"
                placeholder={t('Şifre (en az 10 karakter)')} maxLength={128}
                value={pw1} onChange={(e) => { setPw1(e.target.value); setPwMsg(null); }}
              />
              <input
                className="tinput" type="password" autoComplete="new-password"
                placeholder={t('Şifre (tekrar)')} maxLength={128}
                value={pw2} onChange={(e) => { setPw2(e.target.value); setPwMsg(null); }}
              />
              <button className="apply-btn" type="submit" disabled={pwBusy || !pw1 || !pw2}>
                {pwBusy ? '…' : t('Kaydet')}
              </button>
            </form>
          )}
          {pwMsg && (
            <div className="settings-row">
              <span className={pwMsg.ok ? 'win' : 'loss'} style={{ fontSize: 12 }}>{pwMsg.text}</span>
            </div>
          )}
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
