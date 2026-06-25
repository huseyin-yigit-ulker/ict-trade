import { createContext, useContext, useState, useCallback } from 'react';
import { Navigate, useLocation } from 'react-router-dom';

// Soft client-side gate (static frontend — NOT real security; everything here
// ships in the bundle, and the data layer must be protected by Supabase RLS).
// Hardened as far as a static site allows:
//  - credentials never appear as plaintext in the bundle. Override via .env:
//      VITE_LOGIN_PBKDF2       ("iterations:saltHex:hashHex", strongest — generate
//                               with `node scripts/gen-login-hash.mjs`)
//      VITE_LOGIN_USER_SHA256 / VITE_LOGIN_PASS_SHA256 (hex digests)
//      VITE_LOGIN_USER / VITE_LOGIN_PASS (plaintext, legacy fallback)
//  - sessions expire (7 days with "remember me", 12 hours otherwise); an expired
//    session surfaces a "session expired" note on the login screen
//  - failed attempts are throttled with a PERSISTENT exponential backoff
//    (5 fails → 30s, doubling per strike up to 15 min; survives refresh+tab close)
const LS = 'pusu.auth';
const LOCK_KEY = 'pusu.lock';
const NOTE_KEY = 'pusu.authnote';
const MAX_FAILS = 5;
const LOCK_BASE_MS = 30_000;
const LOCK_MAX_MS = 15 * 60_000;
const REMEMBER_TTL_MS = 7 * 24 * 60 * 60 * 1000;
const SESSION_TTL_MS = 12 * 60 * 60 * 1000;

const USER_PLAIN = import.meta.env.VITE_LOGIN_USER || null;
const PASS_PLAIN = import.meta.env.VITE_LOGIN_PASS || null;
const PASS_PBKDF2 = import.meta.env.VITE_LOGIN_PBKDF2 || null;
// Built-in fallback digests — ONLY for first-run convenience. They are public
// (in the bundle + repo history), so any deployment MUST override them via .env.
// `usingDefaultCreds` flags this state and the login screen shows a warning.
const USER_SHA = import.meta.env.VITE_LOGIN_USER_SHA256
  || 'd4822ddc3221d33dc53dab8616f2bd4d6039786ce432123a99a7571c50162b6c';
const PASS_SHA = import.meta.env.VITE_LOGIN_PASS_SHA256
  || '5e31e4ceb5a3c2ff647ec9e32fc8ec935d158da4d19ffd1f56be669ff47a9c26';   // sha256('pusu2001')

export const usingDefaultCreds = !(
  USER_PLAIN || PASS_PLAIN || PASS_PBKDF2
  || import.meta.env.VITE_LOGIN_USER_SHA256 || import.meta.env.VITE_LOGIN_PASS_SHA256
);
if (usingDefaultCreds && import.meta.env.PROD) {
  console.warn('[PUSU] Default login credentials are active. Set VITE_LOGIN_* in .env (see scripts/gen-login-hash.mjs).');
}

const toHex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');

const sha256Hex = async (text) => {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return toHex(buf);
};

// PBKDF2-SHA256 — makes offline brute-force of the bundled digest expensive
// (vs a single SHA-256 which a GPU rig guesses billions of times per second).
const pbkdf2Hex = async (password, saltHex, iterations) => {
  const salt = new Uint8Array((saltHex.match(/.{2}/g) || []).map((h) => parseInt(h, 16)));
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(password), 'PBKDF2', false, ['deriveBits']);
  const bits = await crypto.subtle.deriveBits(
    { name: 'PBKDF2', hash: 'SHA-256', salt, iterations },
    key, 256,
  );
  return toHex(bits);
};

const checkCredentials = async (username, password) => {
  // Plaintext env vars (legacy) win; otherwise hash-compare. crypto.subtle
  // needs a secure context (https / localhost) — both deploy + dev qualify.
  if (USER_PLAIN || PASS_PLAIN) {
    return username === (USER_PLAIN || 'pusu') && password === (PASS_PLAIN || '');
  }
  if (!globalThis.crypto?.subtle) return false;
  const uh = await sha256Hex(username);
  if (uh !== USER_SHA) return false;
  if (PASS_PBKDF2) {
    const [iterStr, saltHex, hashHex] = PASS_PBKDF2.split(':');
    const iterations = Number(iterStr);
    if (!Number.isFinite(iterations) || !saltHex || !hashHex) return false;
    try {
      return (await pbkdf2Hex(password, saltHex, iterations)) === hashHex.toLowerCase();
    } catch { return false; }
  }
  return (await sha256Hex(password)) === PASS_SHA;
};

// --- persistent fail-lock state: { fails, strikes, until } in localStorage ---
const readLock = () => {
  try {
    const l = JSON.parse(localStorage.getItem(LOCK_KEY) || 'null');
    return l && typeof l === 'object' ? { fails: l.fails | 0, strikes: l.strikes | 0, until: Number(l.until) || 0 } : { fails: 0, strikes: 0, until: 0 };
  } catch { return { fails: 0, strikes: 0, until: 0 }; }
};
const writeLock = (l) => { try { localStorage.setItem(LOCK_KEY, JSON.stringify(l)); } catch { /* ignore */ } };
const clearLock = () => { try { localStorage.removeItem(LOCK_KEY); } catch { /* ignore */ } };

const readStoredUser = () => {
  try {
    const u = JSON.parse(localStorage.getItem(LS) || sessionStorage.getItem(LS) || 'null');
    if (!u) return null;
    // Expired (or legacy entry without exp) → treat as signed out and leave a
    // note so the login screen can explain why the user was bounced.
    if (!Number.isFinite(u.exp) || u.exp < Date.now()) {
      localStorage.removeItem(LS); sessionStorage.removeItem(LS);
      try { sessionStorage.setItem(NOTE_KEY, 'expired'); } catch { /* ignore */ }
      return null;
    }
    return u;
  } catch { return null; }
};

// One-shot read of the auth note ('expired') left by readStoredUser.
export const consumeAuthNote = () => {
  try {
    const n = sessionStorage.getItem(NOTE_KEY);
    if (n) sessionStorage.removeItem(NOTE_KEY);
    return n;
  } catch { return null; }
};

const AuthContext = createContext();
export const useAuth = () => useContext(AuthContext);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(readStoredUser);

  // ms until the lockout ends (0 = not locked). Survives refresh AND tab close.
  const lockRemainingMs = useCallback(() => Math.max(0, readLock().until - Date.now()), []);

  const login = useCallback(async (username, password, remember = true) => {
    if (lockRemainingMs() > 0) return { ok: false, lockedMs: lockRemainingMs() };

    const ok = await checkCredentials(username, password);
    if (!ok) {
      const lock = readLock();
      lock.fails += 1;
      if (lock.fails >= MAX_FAILS) {
        // Exponential backoff: 30s → 1m → 2m → ... capped at 15 min.
        lock.fails = 0;
        lock.strikes += 1;
        const ms = Math.min(LOCK_MAX_MS, LOCK_BASE_MS * 2 ** (lock.strikes - 1));
        lock.until = Date.now() + ms;
        writeLock(lock);
        return { ok: false, lockedMs: ms };
      }
      writeLock(lock);
      return { ok: false, lockedMs: 0 };
    }

    clearLock();
    const ttl = remember ? REMEMBER_TTL_MS : SESSION_TTL_MS;
    const u = { name: username, at: Date.now(), exp: Date.now() + ttl };
    try {
      // "Remember me" → localStorage (survives close); otherwise sessionStorage (this tab only).
      const store = remember ? localStorage : sessionStorage;
      const other = remember ? sessionStorage : localStorage;
      store.setItem(LS, JSON.stringify(u));
      other.removeItem(LS);
    } catch { /* ignore */ }
    setUser(u);
    return { ok: true, lockedMs: 0 };
  }, [lockRemainingMs]);

  const logout = useCallback(() => {
    try { localStorage.removeItem(LS); sessionStorage.removeItem(LS); } catch { /* ignore */ }
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, isAuthed: !!user, login, logout, lockRemainingMs }}>
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
