// Authenticated PostgREST fetch for user-scoped tables (profiles, user_api_keys_public,
// user_stream_settings, audit_log, live_positions, ...). Sends the user JWT as the
// Bearer (RLS row scoping) with the anon key as `apikey`, plus the ict_trade schema
// profile headers — including Content-Profile, the known POST/RPC pitfall.
//
// 401s trigger ONE single-flight refresh + retry; a failed refresh clears the session
// and fires 'pusu:session-expired' (AuthContext listens and bounces to /login).

import { loadSession, saveSession, clearSession, refreshSession } from './gotrue';

const URL = import.meta.env.VITE_SUPABASE_URL;
const KEY = import.meta.env.VITE_SUPABASE_PUBLISHABLE_DEFAULT_KEY;

let refreshing = null;   // single-flight: concurrent 401s share one refresh

function expireSession() {
  clearSession();
  try { window.dispatchEvent(new Event('pusu:session-expired')); } catch { /* ignore */ }
}

async function doRefresh(session) {
  if (!refreshing) {
    refreshing = refreshSession(session.refresh_token)
      .then((ns) => { saveSession(ns); return ns; })
      .catch((e) => { expireSession(); throw e; })
      .finally(() => { refreshing = null; });
  }
  return refreshing;
}

/** Refresh proactively when within 60s of expiry; returns the (possibly new) session. */
export async function ensureFreshSession() {
  const s = loadSession();
  if (!s) return null;
  if ((s.expires_at || 0) * 1000 - Date.now() > 60_000) return s;
  try { return await doRefresh(s); } catch { return null; }
}

/** Fetch `${URL}/rest/v1/<path>` with JWT + schema headers. Returns the raw Response. */
export async function authedFetch(path, opts = {}) {
  let session = await ensureFreshSession();
  const call = (token) => fetch(`${URL}/rest/v1/${path}`, {
    ...opts,
    headers: {
      apikey: KEY,
      Authorization: `Bearer ${token || KEY}`,
      'Accept-Profile': 'ict_trade',
      'Content-Profile': 'ict_trade',
      'Content-Type': 'application/json',
      ...(opts.headers || {}),
    },
  });
  let res = await call(session?.access_token);
  if (res.status === 401 && session) {
    try {
      session = await doRefresh(session);
      res = await call(session.access_token);
    } catch { /* expired — caller sees the 401 */ }
  }
  return res;
}

/** GET returning parsed JSON (throws on !ok with the PostgREST message). */
export async function getJSON(path, opts = {}) {
  const res = await authedFetch(path, opts);
  if (!res.ok) throw new Error(await postgrestError(res));
  return res.json();
}

/** POST /rest/v1/rpc/<name>. Returns parsed JSON (or null for void functions). */
export async function rpc(name, args = {}) {
  const res = await authedFetch(`rpc/${name}`, { method: 'POST', body: JSON.stringify(args) });
  if (!res.ok) throw new Error(await postgrestError(res));
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

/** Change the logged-in user's password (GoTrue PUT /auth/v1/user). Throws with the
    server's message on failure (e.g. weak password / same password). */
export async function changePassword(newPassword) {
  const s = await ensureFreshSession();
  if (!s) throw new Error('no session');
  const res = await fetch(`${URL}/auth/v1/user`, {
    method: 'PUT',
    headers: { apikey: KEY, Authorization: `Bearer ${s.access_token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ password: newPassword }),
  });
  if (!res.ok) {
    const b = await res.json().catch(() => null);
    throw new Error(b?.msg || b?.error_description || b?.message || `HTTP ${res.status}`);
  }
  return true;
}

/** Extract the human message from a PostgREST error body (e.g. a trigger's raise exception). */
async function postgrestError(res) {
  try {
    const body = await res.json();
    return body?.message || body?.hint || body?.details || `HTTP ${res.status}`;
  } catch {
    return `HTTP ${res.status}`;
  }
}
