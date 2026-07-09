import { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import {
  loadSession, saveSession, clearSession,
  signIn as gtSignIn, signUp as gtSignUp, signOut as gtSignOut, authConfigured,
} from '../utils/gotrue';
import { ensureFreshSession, getJSON } from '../utils/supa';
import { fetchPrefs, savePrefs } from '../utils/userPrefs';
import { useLang } from './LanguageContext';
import { useTheme } from './ThemeContext';

// REAL multi-user auth: Supabase Auth (GoTrue) sessions + an ict_trade.profiles row per
// user (role user|admin, status pending|active|disabled — signup lands PENDING until an
// admin approves it from /admin). RLS on the user tables is the actual security boundary;
// this context only orchestrates the session + profile state on the client.
//
// Kept from the old soft gate: the persistent client-side fail-lockout UX (GoTrue also
// rate-limits server-side) and the 'expired' login note.
const LOCK_KEY = 'pusu.lock';
const NOTE_KEY = 'pusu.authnote';
const MAX_FAILS = 5;
const LOCK_BASE_MS = 30_000;
const LOCK_MAX_MS = 15 * 60_000;

// Legacy export — the env-digest gate is gone; LoginScreen's warning banner keys off this.
export const usingDefaultCreds = false;

// --- persistent fail-lock state: { fails, strikes, until } in localStorage ---
const readLock = () => {
  try {
    const l = JSON.parse(localStorage.getItem(LOCK_KEY) || 'null');
    return l && typeof l === 'object' ? { fails: l.fails | 0, strikes: l.strikes | 0, until: Number(l.until) || 0 } : { fails: 0, strikes: 0, until: 0 };
  } catch { return { fails: 0, strikes: 0, until: 0 }; }
};
const writeLock = (l) => { try { localStorage.setItem(LOCK_KEY, JSON.stringify(l)); } catch { /* ignore */ } };
const clearLock = () => { try { localStorage.removeItem(LOCK_KEY); } catch { /* ignore */ } };

// One-shot read of the auth note ('expired') for the login screen.
export const consumeAuthNote = () => {
  try {
    const n = sessionStorage.getItem(NOTE_KEY);
    if (n) sessionStorage.removeItem(NOTE_KEY);
    return n;
  } catch { return null; }
};
const leaveNote = (n) => { try { sessionStorage.setItem(NOTE_KEY, n); } catch { /* ignore */ } };

const AuthContext = createContext();
export const useAuth = () => useContext(AuthContext);

// Yüzey varsayılanları. İSTİHBARAT/İŞLEM opt-out: satır yoksa açık, admin açıkça false
// yaparsa kapanır. BACKTEST ise opt-in: 18 araştırma varyantı ürün değil laboratuvardır,
// bu yüzden varsayılan KAPALI — yalnız admin (isAdmin) veya admin'in backtest yüzeyini
// açıkça =true yaptığı kullanıcı görür. (Canlı 3 akışın kendi backtest sekmesi bundan
// bağımsız: o CANLI MODÜL'de, araştırma bölümünde değil — isResearchStream=false.)
// intelligence: 2026-07-09 opt-in'e çevrildi (backtest gibi). Kurumsal quant tearsheet
// (Sharpe/Sortino/drawdown/aylık-ısı-haritası) son kullanıcı ürünü değil, analist
// yüzeyidir — normal kullanıcı SADECE gerekli/öz bilgiyi görsün. Yalnız admin, ya da
// admin'in açıkça =true yaptığı kullanıcı görür. trading opt-out kalır (default açık).
const DEFAULT_FEATURES = { backtest: false, intelligence: false, trading: true };

export const AuthProvider = ({ children }) => {
  const [session, setSession] = useState(loadSession);
  const [profile, setProfile] = useState(null);
  // Oturum diskten geri yükleniyorsa profil/features fetch'i KESİN çalışacak (aşağıdaki
  // mount efekti). O yüzden loading'i baştan true başlat — yoksa efekt-öncesi ilk render'da
  // features=DEFAULT_FEATURES olur ve RequireFeature, gerçek features gelmeden yanlış karar
  // verip fail-closed yüzeyleri (intelligence) '/'e atar. Oturum yoksa RequireAuth zaten login'e yollar.
  const [profileLoading, setProfileLoading] = useState(() => !!loadSession());
  const [features, setFeatures] = useState(null);   // null = yüklenmedi → DEFAULT_FEATURES
  const [prefs, setPrefs] = useState(null);
  const refreshTimer = useRef(null);
  const { setTheme } = useTheme();
  const { setLang } = useLang();

  const lockRemainingMs = useCallback(() => Math.max(0, readLock().until - Date.now()), []);

  // ---- profile: the app-level identity (role/status) behind the GoTrue session
  const loadProfile = useCallback(async (sess) => {
    const uid = sess?.user?.id;
    if (!uid) { setProfile(null); setFeatures(null); return null; }
    setProfileLoading(true);
    try {
      const rows = await getJSON(
        `profiles?select=user_id,email,display_name,role,status,is_canonical&user_id=eq.${uid}`,
      );
      const p = rows?.[0] || null;
      setProfile(p);
      // Admin'in bu kullanıcıya açtığı yüzeyler — satır yoksa hepsi açık.
      try {
        const f = await getJSON(
          `user_features?select=backtest,intelligence,trading&user_id=eq.${uid}`,
        );
        setFeatures(f?.[0] || DEFAULT_FEATURES);
      } catch { setFeatures(DEFAULT_FEATURES); }   // tablo yok / geçici hata → kısıtlama yok
      return p;
    } catch {
      // transient error: keep the session, profile stays unknown (RequireActive treats as pending)
      return null;
    } finally {
      setProfileLoading(false);
    }
  }, []);

  // ---- prefs: tema/dil/açılış sayfası + bildirim tercihleri (user_prefs).
  // apply=true (login + ilk mount) tema/dili sunucudaki değere çeker — persist:false
  // ile, ki uygulama DB'ye geri yankılanmasın.
  const loadPrefs = useCallback(async (apply = false) => {
    const pr = await fetchPrefs();
    setPrefs(pr);
    if (apply && pr) {
      if (pr.theme) setTheme(pr.theme, { persist: false });
      if (pr.lang) setLang(pr.lang, { persist: false });
    }
    return pr;
  }, [setTheme, setLang]);

  // Ayar yüzeylerinin tek yazma yolu: local state + best-effort DB upsert birlikte.
  const updatePrefs = useCallback((partial) => {
    setPrefs((p) => ({ ...(p || {}), ...partial }));
    savePrefs(partial);
  }, []);

  // ---- proactive refresh: timer at expiry−60s + on tab resume (PWA), + expiry event
  useEffect(() => {
    if (refreshTimer.current) clearTimeout(refreshTimer.current);
    if (!session) return undefined;
    const ms = Math.max(5_000, (session.expires_at || 0) * 1000 - Date.now() - 60_000);
    refreshTimer.current = setTimeout(async () => {
      const s = await ensureFreshSession();
      if (s) setSession(s);
    }, ms);
    return () => clearTimeout(refreshTimer.current);
  }, [session]);

  useEffect(() => {
    const onVisible = async () => {
      if (document.visibilityState !== 'visible') return;
      const s = await ensureFreshSession();
      if (s && s.access_token !== session?.access_token) setSession(s);
    };
    const onExpired = () => {
      leaveNote('expired');
      setSession(null);
      setProfile(null);
    };
    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('pusu:session-expired', onExpired);
    return () => {
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('pusu:session-expired', onExpired);
    };
  }, [session]);

  useEffect(() => {
    if (session) { loadProfile(session); loadPrefs(true); }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- actions
  const login = useCallback(async (email, password, remember = true) => {
    if (lockRemainingMs() > 0) return { ok: false, lockedMs: lockRemainingMs() };
    try {
      const s = await gtSignIn(email.trim(), password);
      clearLock();
      saveSession(s, remember);
      setSession(s);
      loadProfile(s);
      // Prefs beklenir (küçük tek satır): LoginScreen 'from' yoksa açılış sayfasına gider.
      let defaultPage = null;
      try { defaultPage = (await loadPrefs(true))?.default_page || null; } catch { /* ignore */ }
      return { ok: true, lockedMs: 0, defaultPage };
    } catch (e) {
      const lock = readLock();
      lock.fails += 1;
      if (lock.fails >= MAX_FAILS) {
        lock.fails = 0;
        lock.strikes += 1;
        const ms = Math.min(LOCK_MAX_MS, LOCK_BASE_MS * 2 ** (lock.strikes - 1));
        lock.until = Date.now() + ms;
        writeLock(lock);
        return { ok: false, lockedMs: ms, error: e?.message };
      }
      writeLock(lock);
      return { ok: false, lockedMs: 0, error: e?.message };
    }
  }, [lockRemainingMs, loadProfile, loadPrefs]);

  const signup = useCallback(async (email, password, displayName = '') => {
    try {
      const { session: s } = await gtSignUp(email.trim(), password, displayName);
      if (s) {
        saveSession(s, true);
        setSession(s);
        await loadProfile(s);
        return { ok: true, pending: true };
      }
      // confirm-email is ON in the dashboard (not the intended config) — no session yet
      return { ok: true, pending: true, needsConfirm: true };
    } catch (e) {
      return { ok: false, error: e?.message };
    }
  }, [loadProfile]);

  const logout = useCallback(() => {
    const tok = loadSession()?.access_token;
    clearSession();
    setSession(null);
    setProfile(null);
    setFeatures(null);
    setPrefs(null);
    if (tok) gtSignOut(tok);
  }, []);

  const refreshProfile = useCallback(() => loadProfile(loadSession()), [loadProfile]);

  // Back-compat shape: Sidebar/Settings read user.name.
  const user = session ? {
    name: profile?.display_name || session.user?.email?.split('@')[0] || 'PUSU',
    email: session.user?.email,
    id: session.user?.id,
  } : null;

  return (
    <AuthContext.Provider value={{
      user,
      session,
      profile,
      profileLoading,
      isAuthed: !!session,
      isActive: profile?.status === 'active',
      isAdmin: profile?.role === 'admin' && profile?.status === 'active',
      isCanonical: !!profile?.is_canonical,
      features: features || DEFAULT_FEATURES,
      prefs,
      updatePrefs,
      authConfigured: authConfigured(),
      login, signup, logout, refreshProfile, lockRemainingMs,
    }}>
      {children}
    </AuthContext.Provider>
  );
};

// Route guard: unauthenticated visitors are bounced to /login (remembering origin).
export const RequireAuth = ({ children }) => {
  const { isAuthed } = useAuth();
  const loc = useLocation();
  if (!isAuthed) return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  return children;
};

// Trading-surface guard: pending/disabled accounts see an approval notice instead.
export const RequireActive = ({ children }) => {
  const { isActive, profile, profileLoading } = useAuth();
  const { t } = useLang();
  if (isActive) return children;
  return (
    <div className="pending-gate">
      <div className="overview-card pending-gate__card">
        <div className="summary-kicker">PUSU</div>
        {profile?.status === 'disabled' ? (
          <>
            <h2>{t('Hesap devre dışı')}</h2>
            <p>{t('Hesabınız yönetici tarafından devre dışı bırakıldı. Erişim için sistem yöneticinize başvurun.')}</p>
          </>
        ) : (
          <>
            <h2>{t('Onay bekleniyor')}</h2>
            <p>{profileLoading
              ? t('Hesap durumu kontrol ediliyor…')
              : t('Hesabınız oluşturuldu ve yönetici onayı bekliyor. Onaylandığında canlı işlem özellikleri açılacak.')}</p>
          </>
        )}
      </div>
    </div>
  );
};

export const RequireAdmin = ({ children }) => {
  const { isAdmin, profileLoading } = useAuth();
  if (profileLoading) return null;
  if (!isAdmin) return <Navigate to="/" replace />;
  return children;
};

// Admin'in kullanıcı-başına aç/kapatabildiği yüzeyler (user_features). Admin her
// yüzeyi görür. Kullanıcı için: opt-out yüzeyler (trading, default açık) yalnız
// =false ise kapanır; opt-in yüzeyler (intelligence, DEFAULT_FEATURES'ta false)
// yalnız admin =true yaptıysa açılır. İki kural da tek satırla: =false ⇒ engelle.
export const RequireFeature = ({ k, children }) => {
  const { features, isAdmin, profileLoading } = useAuth();
  if (profileLoading) return null;
  if (isAdmin) return children;
  if (features?.[k] === false) return <Navigate to="/" replace />;
  return children;
};
