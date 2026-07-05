// Raw Supabase Auth (GoTrue) REST client — no supabase-js, consistent with the
// hand-rolled PostgREST fetches everywhere else in PUSU.
//
// Session shape (stored at localStorage/sessionStorage 'pusu.session'):
//   { access_token, refresh_token, expires_at (unix s), user: {id, email, ...} }
//
// Signup lands the user in a PENDING profile (ict_trade.profiles trigger); an admin
// activates it from /admin. "Confirm email" is disabled in the Supabase dashboard —
// admin approval replaces it.

const URL = import.meta.env.VITE_SUPABASE_URL;
const KEY = import.meta.env.VITE_SUPABASE_PUBLISHABLE_DEFAULT_KEY;
const LS = 'pusu.session';

const HEADERS = { apikey: KEY, 'Content-Type': 'application/json' };

async function authPost(path, body, token) {
  const headers = { ...HEADERS };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${URL}/auth/v1/${path}`, {
    method: 'POST', headers, body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data = null;
  try { data = await res.json(); } catch { /* logout returns 204 */ }
  if (!res.ok) {
    const msg = data?.error_description || data?.msg || data?.message || data?.error || `auth ${res.status}`;
    const err = new Error(msg);
    err.status = res.status;
    err.code = data?.error_code || data?.code;
    throw err;
  }
  return data;
}

function normalize(data) {
  if (!data?.access_token) return null;
  return {
    access_token: data.access_token,
    refresh_token: data.refresh_token,
    // GoTrue returns expires_at (unix s) on recent versions; derive it otherwise.
    expires_at: data.expires_at || Math.floor(Date.now() / 1000) + (Number(data.expires_in) || 3600),
    user: data.user || null,
  };
}

// ---------------------------------------------------------------- session store
export function loadSession() {
  try {
    const raw = localStorage.getItem(LS) || sessionStorage.getItem(LS);
    const s = raw ? JSON.parse(raw) : null;
    return s?.access_token && s?.refresh_token ? s : null;
  } catch { return null; }
}

export function saveSession(session, remember = null) {
  try {
    // remember=null keeps the store the session already lives in (refresh path).
    const inLocal = remember === null ? !!localStorage.getItem(LS) || !sessionStorage.getItem(LS) : remember;
    const store = inLocal ? localStorage : sessionStorage;
    const other = inLocal ? sessionStorage : localStorage;
    store.setItem(LS, JSON.stringify(session));
    other.removeItem(LS);
  } catch { /* ignore */ }
}

export function clearSession() {
  try { localStorage.removeItem(LS); sessionStorage.removeItem(LS); } catch { /* ignore */ }
}

// ---------------------------------------------------------------- GoTrue calls
export async function signUp(email, password, displayName = '') {
  const data = await authPost('signup', {
    email, password, data: displayName ? { display_name: displayName } : undefined,
  });
  // With confirm-email OFF GoTrue returns a full session; with it ON only the user.
  return { session: normalize(data), user: data?.user || data || null };
}

export async function signIn(email, password) {
  const data = await authPost('token?grant_type=password', { email, password });
  const s = normalize(data);
  if (!s) throw new Error('no session in response');
  return s;
}

export async function refreshSession(refresh_token) {
  const data = await authPost('token?grant_type=refresh_token', { refresh_token });
  const s = normalize(data);
  if (!s) throw new Error('refresh failed');
  return s;
}

export async function signOut(access_token) {
  try { await authPost('logout', undefined, access_token); } catch { /* best-effort */ }
}

export function authConfigured() {
  return !!(URL && KEY);
}
