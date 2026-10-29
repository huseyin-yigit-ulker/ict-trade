import { useEffect, useRef, useState } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { useAuth, usingDefaultCreds, consumeAuthNote } from '../context/AuthContext';
import { useLang } from '../context/LanguageContext';
import { codenameFor, isResearchStream } from '../utils/streamMask';
import { STREAMS, fetchAllSummaries, getCachedStats, fmtR, fmtExp, fmtPct } from '../utils/streamStats';
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

// Ambient "liquidity sweep" curve behind the card — a price path that runs
// under a liquidity level, sweeps it (the ambush), then expands away.
const LiquidityCurve = () => (
  <svg className="boot-curve" viewBox="0 0 1440 320" preserveAspectRatio="none" aria-hidden="true">
    <defs>
      <linearGradient id="lx-curve-grad" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" stopColor="#F0B93A" stopOpacity="0" />
        <stop offset="0.45" stopColor="#F0B93A" stopOpacity="0.55" />
        <stop offset="1" stopColor="#0ECB81" stopOpacity="0.7" />
      </linearGradient>
    </defs>
    {/* the resting liquidity level (equal lows) */}
    <line className="boot-curve__level" x1="120" y1="208" x2="900" y2="208" />
    {/* price path: ranging → sweep below the level → displacement up */}
    <path
      className="boot-curve__path"
      d="M-20 190 L90 196 L150 178 L230 200 L300 184 L380 205 L460 188 L540 206 L620 192 L700 207 L760 196 L830 246 L880 252 L920 200 L980 158 L1040 170 L1110 118 L1180 132 L1260 84 L1340 96 L1460 40"
      pathLength="1"
      fill="none" stroke="url(#lx-curve-grad)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round"
    />
  </svg>
);

// Live market pulse on the login screen — three flagship perps, 10s poll.
// Public Binance endpoint, no auth; doubles as an "exchange API online" signal.
const PULSE_SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT'];
const MarketPulse = () => {
  const { t } = useLang();
  const [rows, setRows] = useState(null); // null = loading, [] = unreachable

  useEffect(() => {
    let stopped = false;
    // FAPI's 24hr ticker has no multi-symbol filter (the spot-style `symbols`
    // param is ignored and the FULL market dumps back) — fetch each one.
    const fetchOne = async (sym) => {
      try {
        const res = await fetch(`https://fapi.binance.com/fapi/v1/ticker/24hr?symbol=${sym}`);
        if (!res.ok) return null;
        const d = await res.json();
        const price = parseFloat(d?.lastPrice);
        const pct = parseFloat(d?.priceChangePercent);
        return Number.isFinite(price) ? { sym: sym.replace(/USDT$/, ''), price, pct } : null;
      } catch { return null; }
    };
    const poll = async () => {
      const rows = (await Promise.all(PULSE_SYMBOLS.map(fetchOne))).filter(Boolean);
      if (stopped) return;
      setRows((prev) => (rows.length ? rows : prev ?? []));
    };
    poll();
    const id = setInterval(poll, 10_000);
    return () => { stopped = true; clearInterval(id); };
  }, []);

  if (rows === null) return null;
  if (rows.length === 0) {
    return <div className="login-pulse login-pulse--off"><span className="login-pulse__dot" /> {t('bağlantı yok')}</div>;
  }
  return (
    <div className="login-pulse" aria-hidden="true">
      <span className="login-pulse__dot live" />
      {rows.map((r) => (
        <span key={r.sym} className="login-pulse__item">
          <b>{r.sym}</b>
          <span>{r.price >= 1000 ? r.price.toLocaleString('en-US', { maximumFractionDigits: 0 }) : r.price.toFixed(2)}</span>
          <i className={r.pct >= 0 ? 'up' : 'down'}>{r.pct >= 0 ? '▲' : '▼'}{Math.abs(r.pct).toFixed(2)}%</i>
        </span>
      ))}
    </div>
  );
};

// Read-only track record on the login screen — the 2026 backtest result of every
// strategy stream, displayed as ranked bars. PURELY informational: no links, no
// detail, no navigation (the operator must sign in to reach any of it). Pulls the
// same public backtest RPC the dashboard uses; renders nothing until data lands.
const TrackRecord = () => {
  const { lang, t } = useLang();
  const [stats, setStats] = useState(getCachedStats());

  useEffect(() => {
    if (getCachedStats()) return undefined;
    let alive = true;
    fetchAllSummaries().then((d) => { if (alive) setStats(d); }).catch(() => { /* silent on the login */ });
    return () => { alive = false; };
  }, []);

  if (!stats) return null;
  // Public splash: yalnız CANLI (ürün) akımları — 18 backtest-only araştırma varyantı
  // anonim ziyaretçiye gösterilmez (cherry-pick optiği + mekanik sızıntısı olmasın).
  const rows = STREAMS
    .filter((s) => !isResearchStream(s.key))
    .map((s) => ({ s, m: stats[s.version] }))
    .filter((x) => x.m)
    .sort((a, b) => Number(b.m.total_r) - Number(a.m.total_r));
  if (!rows.length) return null;

  const nfmt = (n) => Number(n).toLocaleString(lang === 'en' ? 'en-US' : 'tr-TR');
  const maxAbsR = Math.max(1, ...rows.map((x) => Math.abs(Number(x.m.total_r) || 0)));
  const totalSignals = rows.reduce((sum, x) => sum + (Number(x.m.total_trades) || 0), 0);
  const top = rows[0];
  const bestExp = rows.reduce((a, b) => (Number(b.m.avg_r) > Number(a.m.avg_r) ? b : a));
  // Public screen — ALWAYS anonymized codenames (real names are admin-only, in-app).
  const head = (s) => ({ title: codenameFor(s.key), icon: '◆', accent: '#F0B90B' });

  return (
    <div className="login-track">
      <div className="login-track__title">
        <span>{t('Başarı Geçmişi')}</span>
        <span className="login-track__year">2026 · {t('örneklem içi')}</span>
      </div>

      <div className="login-track__leaders">
        <div className="login-track__lead">
          <b className="win">{fmtR(Number(top.m.total_r))}</b>
          <span>{head(top.s).title}</span>
        </div>
        <div className="login-track__lead">
          <b className="win">{fmtExp(Number(bestExp.m.avg_r))}</b>
          <span>{t('işlem başına')}</span>
        </div>
        <div className="login-track__lead">
          <b>{nfmt(totalSignals)}</b>
          <span>{t('sinyal')}</span>
        </div>
      </div>

      <div className="login-track__rows">
        {rows.map(({ s, m }) => {
          const r = Number(m.total_r);
          const info = head(s);
          return (
            <div key={s.key} className="login-track__row" style={{ '--acc': info.accent }}>
              <span className="login-track__icon" aria-hidden="true">{info.icon}</span>
              <span className="login-track__name">{info.title}</span>
              <span className="login-track__bar">
                <span className={`login-track__fill ${r >= 0 ? 'win' : 'loss'}`} style={{ width: `${Math.min(100, (Math.abs(r) / maxAbsR) * 100)}%` }} />
              </span>
              <span className={`login-track__r ${r >= 0 ? 'win' : 'loss'}`}>{fmtR(r)}</span>
              <span className="login-track__win">{fmtPct(Number(m.win_rate))}</span>
            </div>
          );
        })}
      </div>

      <div className="login-track__note">{t('Tüm sayılar 2026 backtest — örneklem içi. Forward beklenti daha düşüktür.')}</div>
    </div>
  );
};

const LoginScreen = () => {
  const { isAuthed, login, signup, lockRemainingMs } = useAuth();
  const { lang, setLang, t } = useLang();
  const navigate = useNavigate();
  const location = useLocation();
  const [mode, setMode] = useState('login'); // 'login' | 'signup'
  const [username, setUsername] = useState('');   // e-posta (legacy state adı korunuyor)
  const [password, setPassword] = useState('');
  const [password2, setPassword2] = useState('');
  const [showPass, setShowPass] = useState(false);
  const [remember, setRemember] = useState(true);
  const [loading, setLoading] = useState(false);
  const [showForgot, setShowForgot] = useState(false);
  const [err, setErr] = useState('');
  const [okNote, setOkNote] = useState('');
  const [note] = useState(() => consumeAuthNote()); // 'expired' | null
  const [shake, setShake] = useState(false);
  const [capsOn, setCapsOn] = useState(false);
  const [lockLeft, setLockLeft] = useState(0); // seconds remaining of the fail lockout
  const passRef = useRef(null);

  // Tick the lockout countdown once a second while it's active.
  useEffect(() => {
    const ms = lockRemainingMs();
    if (ms <= 0) return undefined;
    setLockLeft(Math.ceil(ms / 1000));
    const id = setInterval(() => {
      const left = Math.ceil(lockRemainingMs() / 1000);
      setLockLeft(left);
      if (left <= 0) { setErr(''); clearInterval(id); }
    }, 1000);
    return () => clearInterval(id);
  }, [lockRemainingMs, err]);

  if (isAuthed) {
    // Deep link respected: a guarded page bounced here with its origin in state.
    const from = location.state?.from;
    return <Navigate to={from && from !== '/login' ? from : '/'} replace />;
  }

  const failFeedback = (msg) => {
    setErr(msg);
    setShake(true);
    setPassword('');
    passRef.current?.focus();
    setTimeout(() => setShake(false), 500);
  };

  const submit = (e) => {
    e.preventDefault();
    if (loading || !username.trim() || !password) return;
    if (mode === 'signup') {
      if (password.length < 10) { failFeedback(t('Şifre en az 10 karakter olmalı.')); return; }
      if (password !== password2) { failFeedback(t('Şifreler eşleşmiyor.')); return; }
    }
    setLoading(true);
    setErr('');
    setOkNote('');
    setTimeout(async () => {
      if (mode === 'signup') {
        const res = await signup(username.trim(), password);
        setLoading(false);
        if (res.ok && !res.needsConfirm) {
          // Session açık — hesap 'onay bekliyor'; RequireActive canlı sayfaları kilitler.
          navigate('/', { replace: true });
          return;
        }
        if (res.ok && res.needsConfirm) {
          setOkNote(t('Hesap oluşturuldu. E-postanızı doğrulayıp giriş yapın.'));
          setMode('login');
          return;
        }
        failFeedback(res.error || t('Kayıt başarısız. Tekrar deneyin.'));
        return;
      }
      const res = await login(username.trim(), password, remember);
      if (res.ok) {
        // Öncelik: guard'ın bıraktığı deep-link → kullanıcının açılış sayfası tercihi → '/'.
        const from = location.state?.from;
        navigate(from && from !== '/login' ? from : (res.defaultPage || '/'), { replace: true });
        return;
      }
      setLoading(false);
      if (res.lockedMs > 0) {
        setLockLeft(Math.ceil(res.lockedMs / 1000));
        failFeedback(t('Çok fazla hatalı deneme. {s} sn bekleyin.', { s: Math.ceil(res.lockedMs / 1000) }));
      } else {
        failFeedback(t('E-posta veya şifre hatalı.'));
      }
    }, 550);
  };

  const trackCaps = (e) => {
    if (typeof e.getModifierState === 'function') setCapsOn(e.getModifierState('CapsLock'));
  };

  const locked = lockLeft > 0;
  const canSubmit = !loading && !locked && username.trim().length > 0 && password.length > 0;

  return (
    <div className="login-screen login-screen--premium login-screen--split">
      <div className="boot-glow" aria-hidden="true" />
      <div className="boot-grid" aria-hidden="true" />
      <div className="boot-rings" aria-hidden="true"><span /><span /><span /></div>
      <div className="boot-radar" aria-hidden="true" />
      <LiquidityCurve />

      <div className="boot-lang">
        <button className={lang === 'tr' ? 'active' : ''} onClick={() => setLang('tr')}>TR</button>
        <span className="boot-lang__sep">·</span>
        <button className={lang === 'en' ? 'active' : ''} onClick={() => setLang('en')}>EN</button>
      </div>

      <div className="login-split">
        <section className="login-hero">
          <div className="boot-reticle"><PusuLogo size={68} animated /></div>
          <div className="boot-text">
            <div className="boot-title">PUSU</div>
          </div>
          <TrackRecord />
        </section>

        <div className={`login-card login-card--auth${shake ? ' login-card--shake' : ''}`}>
          <div className="login-card__head">
            <span className="login-card__kicker">{mode === 'signup' ? t('Yeni Hesap') : t('Operatör Girişi')}</span>
            <span className="login-card__lock"><LockIcon /> {t('Şifreli Oturum')}</span>
          </div>

          <div className="login-tabs seg" role="tablist">
            <button type="button" className={mode === 'login' ? 'active' : ''} role="tab"
              onClick={() => { setMode('login'); setErr(''); setOkNote(''); }}>{t('Giriş Yap')}</button>
            <button type="button" className={mode === 'signup' ? 'active' : ''} role="tab"
              onClick={() => { setMode('signup'); setErr(''); setOkNote(''); }}>{t('Kayıt Ol')}</button>
          </div>

          {note === 'expired' && (
            <div className="login-note" role="status">{t('Oturum süresi doldu. Lütfen tekrar giriş yapın.')}</div>
          )}
          {okNote && <div className="login-note" role="status">{okNote}</div>}
          {mode === 'signup' && (
            <div className="login-note login-note--info" role="note">
              {t('Kayıt sonrası hesabınız yönetici onayına düşer; onaylanana kadar canlı işlem özellikleri kapalıdır.')}
            </div>
          )}

        <form className="login-form" onSubmit={submit}>
          <label className="login-field">
            <span>{t('E-posta')}</span>
            <input
              type="email" name="email" autoFocus autoComplete="email"
              autoCapitalize="none" autoCorrect="off" spellCheck={false} maxLength={120}
              value={username}
              onChange={(e) => { setUsername(e.target.value); if (err && !locked) setErr(''); }}
              placeholder={t('E-posta')}
            />
          </label>
          <label className="login-field">
            <span>{t('Şifre')}</span>
            <div className="login-pass-wrap">
              <input
                ref={passRef}
                type={showPass ? 'text' : 'password'} name="password"
                autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
                autoCapitalize="none" autoCorrect="off" spellCheck={false} maxLength={128}
                value={password}
                onChange={(e) => { setPassword(e.target.value); if (err && !locked) setErr(''); }}
                onKeyDown={trackCaps} onKeyUp={trackCaps} onBlur={() => setCapsOn(false)}
                placeholder={mode === 'signup' ? t('Şifre (en az 10 karakter)') : t('Şifre')}
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
            {capsOn && <span className="login-caps" role="status">⇪ {t('Caps Lock açık')}</span>}
          </label>
          {mode === 'signup' && (
            <label className="login-field">
              <span>{t('Şifre (tekrar)')}</span>
              <input
                type={showPass ? 'text' : 'password'} name="password2" autoComplete="new-password"
                autoCapitalize="none" autoCorrect="off" spellCheck={false} maxLength={128}
                value={password2}
                onChange={(e) => { setPassword2(e.target.value); if (err && !locked) setErr(''); }}
                placeholder={t('Şifre (tekrar)')}
              />
            </label>
          )}

          {mode === 'login' && (
            <div className="login-aux">
              <label className="login-remember">
                <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
                <span>{t('Beni Hatırla')}</span>
              </label>
              <button type="button" className="login-forgot" onClick={() => setShowForgot((v) => !v)}>
                {t('Şifremi Unuttum')}
              </button>
            </div>
          )}
          {showForgot && <div className="login-forgot-note">{t('Erişim için sistem yöneticinize başvurun.')}</div>}

          {locked && !loading
            ? <div className="login-err" role="alert">{t('Çok fazla hatalı deneme. {s} sn bekleyin.', { s: lockLeft })}</div>
            : err && <div className="login-err" role="alert">{err}</div>}
          <button className="primary-btn login-submit" type="submit" disabled={!canSubmit}>
            {loading
              ? <><span className="btn-spinner" aria-hidden="true" />{t('Doğrulanıyor…')}</>
              : locked ? `${t('Şifreli Oturum')} · ${lockLeft}s`
                : mode === 'signup' ? t('Hesap Oluştur') : t('Piyasaya Gir')}
          </button>
        </form>

        {usingDefaultCreds && (
          <div className="login-warn" role="note">
            ⚠ {t('Varsayılan giriş bilgileri aktif — .env ile özelleştirin.')}
          </div>
        )}

        {/* Halka Açık Canlı Sinyal Ekranı Kartı */}
        <div className="login-public-box">
          <div className="login-public-box__head">
            <span className="pub-badge-dot" />
            <span className="login-public-box__title">{t('Canlı Sinyal Takip Ekranı')}</span>
            <span className="login-public-box__badge">GİRİŞSİZ</span>
          </div>
          <p className="login-public-box__desc">
            {t('OPUS, TALOS-ICHI ve tüm stratejilerin anlık sinyallerini, TP/SL durumlarını ve mum grafiklerini şifresiz izleyin.')}
          </p>
          <Link to="/public" className="login-public-box__link">
            <span>{t('Genel Sinyalleri İncele (/public)')}</span>
            <span className="login-public-box__arrow">→</span>
          </Link>
        </div>

        <div className="login-meta">
          <span className="login-ver">PUSU · v1.1</span>
        </div>

        <MarketPulse />
        </div>
      </div>

      <div className="boot-footer">© 2026 PUSU · {t('Likidite Avı')}</div>
    </div>
  );
};

export default LoginScreen;
