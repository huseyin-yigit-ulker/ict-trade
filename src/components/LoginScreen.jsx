import { useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useLang } from '../context/LanguageContext';
import PusuLogo from './PusuLogo';

const EyeIcon = ({ off }) => (
  <svg viewBox="0 0 20 20" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M1.8 10S4.7 4.8 10 4.8 18.2 10 18.2 10 15.3 15.2 10 15.2 1.8 10 1.8 10Z" />
    <circle cx="10" cy="10" r="2.4" />
    {off && <line x1="3" y1="3" x2="17" y2="17" />}
  </svg>
);
const LockIcon = () => (
  <svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="7" width="10" height="6.5" rx="1.4" /><path d="M5 7V5a3 3 0 0 1 6 0v2" />
  </svg>
);

const LoginScreen = () => {
  const { isAuthed, login } = useAuth();
  const { lang, setLang, t } = useLang();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPass, setShowPass] = useState(false);
  const [remember, setRemember] = useState(true);
  const [loading, setLoading] = useState(false);
  const [showForgot, setShowForgot] = useState(false);
  const [err, setErr] = useState('');

  if (isAuthed) return <Navigate to="/main/live" replace />;

  const submit = (e) => {
    e.preventDefault();
    if (loading) return;
    setLoading(true);
    setErr('');
    // Brief verification beat so the spinner reads as a real check (client-side gate).
    setTimeout(() => {
      if (login(username.trim(), password, remember)) {
        navigate('/main/live', { replace: true });
      } else {
        setErr(t('Kullanıcı adı veya şifre hatalı.'));
        setLoading(false);
      }
    }, 550);
  };

  return (
    <div className="login-screen login-screen--premium">
      <div className="boot-glow" aria-hidden="true" />
      <div className="boot-grid" aria-hidden="true" />
      <div className="boot-rings" aria-hidden="true"><span /><span /><span /></div>
      <div className="boot-radar" aria-hidden="true" />

      <div className="boot-lang">
        <button className={lang === 'tr' ? 'active' : ''} onClick={() => setLang('tr')}>TR</button>
        <span className="boot-lang__sep">·</span>
        <button className={lang === 'en' ? 'active' : ''} onClick={() => setLang('en')}>EN</button>
      </div>

      <div className="login-card">
        <div className="boot-reticle"><PusuLogo size={84} animated /></div>
        <div className="boot-text">
          <div className="boot-title">PUSU</div>
          <div className="boot-sub">Liquidity Ambush Intelligence</div>
        </div>

        <form className="login-form" onSubmit={submit}>
          <label className="login-field">
            <span>{t('Kullanıcı adı')}</span>
            <input
              type="text" autoFocus autoComplete="username"
              value={username}
              onChange={(e) => { setUsername(e.target.value); if (err) setErr(''); }}
              placeholder={t('Kullanıcı adı')}
            />
          </label>
          <label className="login-field">
            <span>{t('Şifre')}</span>
            <div className="login-pass-wrap">
              <input
                type={showPass ? 'text' : 'password'} autoComplete="current-password"
                value={password}
                onChange={(e) => { setPassword(e.target.value); if (err) setErr(''); }}
                placeholder={t('Şifre')}
              />
              <button
                type="button" className="login-pass-toggle"
                onClick={() => setShowPass((s) => !s)}
                title={showPass ? t('Şifreyi gizle') : t('Şifreyi göster')}
                aria-label={showPass ? t('Şifreyi gizle') : t('Şifreyi göster')}
                tabIndex={-1}
              >
                <EyeIcon off={showPass} />
              </button>
            </div>
          </label>

          <div className="login-aux">
            <label className="login-remember">
              <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
              <span>{t('Beni Hatırla')}</span>
            </label>
            <button type="button" className="login-forgot" onClick={() => setShowForgot((v) => !v)}>
              {t('Şifremi Unuttum')}
            </button>
          </div>
          {showForgot && <div className="login-forgot-note">{t('Erişim için sistem yöneticinize başvurun.')}</div>}

          {err && <div className="login-err">{err}</div>}
          <button className="primary-btn login-submit" type="submit" disabled={loading}>
            {loading
              ? <><span className="btn-spinner" aria-hidden="true" />{t('Doğrulanıyor…')}</>
              : t('Piyasaya Gir')}
          </button>
        </form>

        <div className="login-meta">
          <span className="login-badge"><LockIcon /> {t('Şifreli Oturum')}</span>
          <span className="login-ver">PUSU · v1.0</span>
        </div>
      </div>

      <div className="boot-footer">© 2026 PUSU · {t('Likidite Avı')}</div>
    </div>
  );
};

export default LoginScreen;
