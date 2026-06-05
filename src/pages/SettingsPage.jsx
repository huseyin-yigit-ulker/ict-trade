import { useMemo, useState } from 'react';
import { useTradeContext } from '../context/TradeContext';
import { useLang } from '../context/LanguageContext';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';

const SettingsPage = () => {
  const {
    allSignals, selectedSymbols, pendingSymbols, toggleSymbol, applySymbols,
    selectAllPendingSymbols, clearPendingSymbols, testDbConnection, dbStatus, dbMessage,
  } = useTradeContext();
  const { t, lang, setLang } = useLang();
  const { theme, setTheme } = useTheme();
  const { user, logout } = useAuth();
  const [savedSymbols, setSavedSymbols] = useState(false);

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
