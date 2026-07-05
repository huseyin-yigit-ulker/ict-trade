// Web Push subscription helper for PUSU.
//
// Talks to the SAME Supabase (live) project the dashboard already uses, storing
// subscriptions in ict_trade.push_subscriptions. The VM sender (sync/push_notify.py)
// reads that table and fans out notifications via VAPID. The service worker
// (src/sw.js) shows them.
//
// Requires VITE_VAPID_PUBLIC_KEY in the frontend env (from scripts/gen_vapid.py).
// Multi-user: rows are written with the USER JWT (authedFetch) and carry user_id,
// so RLS scopes each subscription to its owner and the sender can target per-user.

import { authedFetch } from './supa';
import { loadSession } from './gotrue';

const SUPA_URL = import.meta.env.VITE_SUPABASE_URL;
const SUPA_KEY = import.meta.env.VITE_SUPABASE_PUBLISHABLE_DEFAULT_KEY;
// VAPID application server key. This is a PUBLIC key (sent to every browser), so
// it is safe to ship in the bundle — committing it means no build-env var is
// needed. An env var, if set, overrides it (lets you rotate without a code change).
const VAPID_PUBLIC = import.meta.env.VITE_VAPID_PUBLIC_KEY
  || 'BFzG5WnCk8-TIuFmNwO0xn4nIxAVMFwv0L9RT_7awvEOK0DIF_k764jaKrMDi8b-NSWzL2KF3AZ8wp2iYj92Mxk';

// VAPID applicationServerKey must be a Uint8Array of the base64url public key.
function urlB64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(base64);
  const arr = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
  return arr;
}

function bufToB64Url(buf) {
  const bytes = new Uint8Array(buf);
  let s = '';
  for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
  return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export function pushSupported() {
  return (
    typeof window !== 'undefined' &&
    'serviceWorker' in navigator &&
    'PushManager' in window &&
    'Notification' in window &&
    !!VAPID_PUBLIC && !!SUPA_URL && !!SUPA_KEY
  );
}

export async function pushState() {
  if (!pushSupported()) return { supported: false, permission: 'unsupported', subscribed: false };
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.getSubscription();
  return { supported: true, permission: Notification.permission, subscribed: !!sub };
}

export async function enablePush() {
  if (!pushSupported()) throw new Error('unsupported');
  const userId = loadSession()?.user?.id;
  if (!userId) throw new Error('no session');   // button is hidden for logged-out anyway
  const perm = await Notification.requestPermission();
  if (perm !== 'granted') throw new Error('denied');
  const reg = await navigator.serviceWorker.ready;
  let sub = await reg.pushManager.getSubscription();
  if (!sub) {
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlB64ToUint8Array(VAPID_PUBLIC),
    });
  }
  const json = sub.toJSON();
  const body = {
    endpoint: sub.endpoint,
    p256dh: json.keys?.p256dh ?? bufToB64Url(sub.getKey('p256dh')),
    auth: json.keys?.auth ?? bufToB64Url(sub.getKey('auth')),
    label: navigator.userAgent.slice(0, 120),
    user_id: userId,
  };
  // Upsert on the unique endpoint so re-subscribing refreshes the keys/owner.
  const res = await authedFetch('push_subscriptions?on_conflict=endpoint', {
    method: 'POST',
    headers: { Prefer: 'resolution=merge-duplicates,return=minimal' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`db ${res.status}`);
  return true;
}

export async function disablePush() {
  if (!('serviceWorker' in navigator)) return;
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.getSubscription();
  if (!sub) return;
  const endpoint = sub.endpoint;
  try { await sub.unsubscribe(); } catch { /* ignore */ }
  if (SUPA_URL && SUPA_KEY) {
    await authedFetch(
      `push_subscriptions?endpoint=eq.${encodeURIComponent(endpoint)}`,
      { method: 'DELETE' },
    ).catch(() => {});
  }
}
