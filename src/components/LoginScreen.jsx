import { useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useLang } from '../context/LanguageContext';
import PusuLogo from './PusuLogo';

const LoginScreen = () => {
  const { isAuthed, login } = useAuth();
  const { lang, setLang, t } = useLang();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [err, setErr] = useState('');

  if (isAuthed) return <Navigate to="/live" replace />;

  const submit = (e) => {
    e.preventDefault();
    if (login(username.trim(), password)) {
      navigate('/command', { replace: true });
    } else {
      setErr(t('Kullanıcı adı veya şifre hatalı.'));
    }
  };

  return (
    <div className="login-screen">
      <div className="boot-grid" aria-hidden="true" />
      <div className="boot-radar" aria-hidden="true" />

      <div className="boot-lang">
        <button className={lang === 'tr' ? 'active' : ''} onClick={() => setLang('tr')}>TR</button>
        <span className="boot-lang__sep">·</span>
        <button className={lang === 'en' ? 'active' : ''} onClick={() => setLang('en')}>EN</button>
      </div>

      <div className="login-card">
        <div className="boot-reticle"><PusuLogo size={88} animated /></div>
        <div className="boot-text">
          <div className="boot-title">PUSU</div>
          <div className="boot-sub">LIQUIDITY AMBUSH SYSTEM</div>
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
            <input
              type="password" autoComplete="current-password"
              value={password}
              onChange={(e) => { setPassword(e.target.value); if (err) setErr(''); }}
              placeholder={t('Şifre')}
            />
          </label>
          {err && <div className="login-err">{err}</div>}
          <button className="primary-btn login-submit" type="submit">{t('Giriş Yap')}</button>
        </form>

        <div className="boot-engine"><span className="boot-engine__dot" /> PUSU ENGINE · ONLINE</div>
      </div>

      <div className="boot-footer">© 2026 PUSU · {t('Likidite Avı')}</div>
    </div>
  );
};

export default LoginScreen;
